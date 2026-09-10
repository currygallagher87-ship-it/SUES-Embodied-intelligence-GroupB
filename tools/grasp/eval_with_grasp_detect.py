#!/usr/bin/env python3
"""
带任务完成检测的策略评估脚本

检测原理：
  当机械臂的 6 个关节同时接近预设的"放球姿态"时，
  判定机器人即将/正在放球，等待几秒后自动退出。

  "放球姿态"通过 tools/grasp/grasp_debug.py 标定并保存在同目录的 place_pose.json 中。

  新增功能：
  - 开始执行时发布 grab 表情指令。
  - 检测到放球完成后发布 success 表情指令，联动 K10 行空板与 LED 灯带。

用法（在仓库根目录执行）：
  1. 先运行 python tools/grasp/grasp_debug.py 标定放球姿态
  2. 再运行 python tools/grasp/eval_with_grasp_detect.py
"""

import json
import logging
import subprocess
import time
import signal
from copy import copy
from contextlib import nullcontext
from pathlib import Path

import numpy as np
import torch

from lerobot.cameras.opencv.configuration_opencv import OpenCVCameraConfig
from lerobot.configs.policies import PreTrainedConfig
from lerobot.datasets.lerobot_dataset import LeRobotDataset
from lerobot.datasets.utils import build_dataset_frame, hw_to_dataset_features
from lerobot.datasets.image_writer import safe_stop_image_writer
from lerobot.datasets.video_utils import VideoEncodingManager
from lerobot.policies.factory import make_policy
from lerobot.robots.so101_follower import SO101Follower, SO101FollowerConfig
from lerobot.utils.utils import get_safe_torch_device, init_logging


# ======================================================================
#                          配置区域（按需修改）
# ======================================================================

# --- 机械臂配置 ---
ROBOT_PORT = "/dev/follower_arm"
ROBOT_ID = "my_awesome_follower_arm"
CAMERAS = {
    "handeye": OpenCVCameraConfig(index_or_path=2, width=640, height=480, fps=30),
    "front": OpenCVCameraConfig(index_or_path=0, width=640, height=480, fps=30),
}

# --- 策略模型配置 ---
POLICY_PATH = "outputs/train/act_so101_bs64_lr1e-4_data_all_ver6_1/pretrained_model/"
POLICY_CHUNK_SIZE = 100
POLICY_N_ACTION_STEPS = 40

# --- 数据集配置 ---
DATASET_REPO_ID = "lip/eval_so101"
SINGLE_TASK = "Grab the screwdriver"
FPS = 30
EPISODE_TIME_S = 300  # 最大运行时间（秒）

# --- 任务完成检测配置 ---
TASK_DETECT_ENABLED = True

# 放球姿态文件（由 grasp_debug.py 生成，固定在本脚本同目录）
PLACE_POSE_FILE = str(Path(__file__).resolve().parent / "place_pose.json")

# 各关节位置与放球姿态的最大允许偏差
# 所有关节同时在此容差范围内 → 判定到达放球位置
POSE_TOLERANCE = 20.0

# 需要连续匹配的帧数（30fps 下 15帧 = 0.5秒）
POSE_MATCH_FRAMES = 15

# 检测到放球姿态后，额外等待的秒数（让放球+回位动作完成）
AFTER_PLACE_WAIT_S = 3.7

# --- ROS2 表情控制指令发布 ---
EMOJI_COMMAND_TOPIC = "/emoji_controller/emoji_command"

# ======================================================================
#                          配置区域结束
# ======================================================================

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)


def publish_emoji_command(cmd: str):
    """通过 ros2 topic pub 发送表情指令 (grab / success)"""
    try:
        subprocess.run(
            ["ros2", "topic", "pub", "-1",
             EMOJI_COMMAND_TOPIC,
             "std_msgs/msg/String",
             f"data: '{cmd}'"],
            timeout=2.0,
            check=False
        )
        logger.info(f"已发送表情指令: {cmd}")
    except Exception as e:
        logger.warning(f"发送表情指令 {cmd} 失败: {e}")


class PlacePoseDetector:
    """
    检测机械臂是否到达预设的放球姿态。
    当所有关节同时在容差范围内且持续一定帧数时，判定到达。
    """

    def __init__(
        self,
        target_pose: dict[str, float],
        tolerance: float = POSE_TOLERANCE,
        match_frames: int = POSE_MATCH_FRAMES,
    ):
        self.target_pose = target_pose
        self.tolerance = tolerance
        self.match_frames = match_frames
        self.consecutive_count = 0
        self.detected = False

    def update(self, current_joints: dict[str, float]) -> bool:
        """
        每帧调用。返回是否检测到放球姿态。

        Args:
            current_joints: 当前所有关节位置 {"xxx.pos": value, ...}
        Returns:
            True if place pose detected
        """
        if self.detected:
            return True

        # 检查每个关节是否在容差内
        all_match = True
        max_deviation = 0.0
        for joint_name, target_val in self.target_pose.items():
            current_val = current_joints.get(joint_name, 0.0)
            deviation = abs(current_val - target_val)
            max_deviation = max(max_deviation, deviation)
            if deviation > self.tolerance:
                all_match = False
                break

        if all_match:
            self.consecutive_count += 1
        else:
            self.consecutive_count = 0

        if self.consecutive_count >= self.match_frames:
            self.detected = True
            logger.info(
                f"📦 检测到放球姿态！"
                f"（连续 {self.consecutive_count} 帧匹配，"
                f"最大偏差={max_deviation:.1f}）"
            )
            return True

        return False


def predict_action(observation, policy, device, use_amp, task=None, robot_type=None):
    """从策略模型预测动作"""
    observation = copy(observation)
    with (
        torch.inference_mode(),
        torch.autocast(device_type=device.type) if device.type == "cuda" and use_amp else nullcontext(),
    ):
        for name in observation:
            observation[name] = torch.from_numpy(observation[name])
            if "image" in name:
                observation[name] = observation[name].type(torch.float32) / 255
                observation[name] = observation[name].permute(2, 0, 1).contiguous()
            observation[name] = observation[name].unsqueeze(0)
            observation[name] = observation[name].to(device)

        observation["task"] = task if task else ""
        observation["robot_type"] = robot_type if robot_type else ""

        action = policy.select_action(observation)
        action = action.squeeze(0)
        action = action.to("cpu")

    return action


def busy_wait(dt_s):
    if dt_s <= 0:
        return
    end = time.perf_counter() + dt_s
    while time.perf_counter() < end:
        pass


def load_place_pose(filepath: str) -> dict[str, float]:
    """加载放球姿态文件"""
    path = Path(filepath)
    if not path.exists():
        raise FileNotFoundError(
            f"找不到放球姿态文件: {filepath}\n"
            f"请先运行 python tools/grasp/grasp_debug.py 标定放球姿态。"
        )
    with open(path) as f:
        pose = json.load(f)
    logger.info(f"已加载放球姿态 ({len(pose)} 个关节):")
    for k, v in pose.items():
        logger.info(f"  {k}: {v:.2f}")
    return pose


def main():
    init_logging()

    should_exit = False

    def signal_handler(sig, frame):
        nonlocal should_exit
        logger.info("收到中断信号，准备退出...")
        should_exit = True

    signal.signal(signal.SIGINT, signal_handler)

    # ===== 1. 加载放球姿态 =====
    if TASK_DETECT_ENABLED:
        place_pose = load_place_pose(PLACE_POSE_FILE)

    # ===== 2. 创建并连接机械臂 =====
    logger.info("正在初始化机械臂...")
    robot_config = SO101FollowerConfig(
        port=ROBOT_PORT,
        id=ROBOT_ID,
        cameras=CAMERAS,
    )
    robot = SO101Follower(robot_config)

    # ===== 3. 构建数据集 =====
    logger.info("正在创建数据集...")
    action_features = hw_to_dataset_features(robot.action_features, "action", True)
    obs_features = hw_to_dataset_features(robot.observation_features, "observation", True)
    dataset_features = {**action_features, **obs_features}

    dataset = LeRobotDataset.create(
        DATASET_REPO_ID,
        FPS,
        robot_type=robot.name,
        features=dataset_features,
        use_videos=True,
        image_writer_processes=0,
        image_writer_threads=4 * len(CAMERAS),
    )

    # ===== 4. 加载策略模型 =====
    logger.info(f"正在加载策略模型: {POLICY_PATH}")
    overrides = []
    if POLICY_CHUNK_SIZE is not None:
        overrides.extend(["--chunk_size", str(POLICY_CHUNK_SIZE)])
    if POLICY_N_ACTION_STEPS is not None:
        overrides.extend(["--n_action_steps", str(POLICY_N_ACTION_STEPS)])

    policy_config = PreTrainedConfig.from_pretrained(POLICY_PATH, cli_overrides=overrides)
    policy_config.pretrained_path = POLICY_PATH
    policy = make_policy(policy_config, ds_meta=dataset.meta)
    policy.reset()

    device = get_safe_torch_device(policy.config.device)
    use_amp = policy.config.use_amp

    # ===== 5. 连接机械臂 =====
    logger.info("正在连接机械臂...")
    robot.connect()

    # ===== 6. 初始化检测器 =====
    detector = PlacePoseDetector(place_pose) if TASK_DETECT_ENABLED else None

    # ===== 7. 开始抓取，通知表情系统 =====
    logger.info("通知表情系统：进入抓取状态")
    publish_emoji_command("grab")

    # ===== 8. 主控制循环 =====
    logger.info(f"开始评估！最大时间={EPISODE_TIME_S}s")
    if detector:
        logger.info(f"放球检测已开启：容差={POSE_TOLERANCE}, 确认帧数={POSE_MATCH_FRAMES}")
        logger.info(f"检测到放球后将等待 {AFTER_PLACE_WAIT_S}s 再退出")

    place_detected = False
    place_detect_time = None
    timestamp = 0
    start_episode_t = time.perf_counter()
    frame_count = 0

    try:
        with VideoEncodingManager(dataset):
            while timestamp < EPISODE_TIME_S and not should_exit:
                start_loop_t = time.perf_counter()

                # --- 获取观测 ---
                observation = robot.get_observation()
                observation_frame = build_dataset_frame(
                    dataset.features, observation, prefix="observation"
                )

                # --- 策略推理 ---
                action_values = predict_action(
                    observation_frame, policy, device, use_amp,
                    task=SINGLE_TASK, robot_type=robot.robot_type,
                )
                action = {
                    key: action_values[i].item()
                    for i, key in enumerate(robot.action_features)
                }

                # --- 发送动作 ---
                sent_action = robot.send_action(action)

                # --- 保存数据帧 ---
                action_frame = build_dataset_frame(
                    dataset.features, sent_action, prefix="action"
                )
                frame = {**observation_frame, **action_frame}
                dataset.add_frame(frame, task=SINGLE_TASK)
                frame_count += 1

                # --- 放球姿态检测 ---
                if detector and not place_detected:
                    joint_positions = {
                        k: v for k, v in observation.items() if k.endswith(".pos")
                    }
                    if detector.update(joint_positions):
                        place_detected = True
                        place_detect_time = time.time()
                        logger.info(
                            f"✅ 检测到放球动作！将继续运行 {AFTER_PLACE_WAIT_S}s "
                            f"等待放球和回位完成后退出..."
                        )

                # --- 放球后等待 ---
                if place_detected and place_detect_time is not None:
                    wait_elapsed = time.time() - place_detect_time
                    if wait_elapsed >= AFTER_PLACE_WAIT_S:
                        logger.info("🎉 夹取成功，发送 success 指令...")
                        publish_emoji_command("success")
                        logger.info("等待结束，退出。")
                        break

                # --- 帧率控制 ---
                dt_s = time.perf_counter() - start_loop_t
                busy_wait(1 / FPS - dt_s)
                timestamp = time.perf_counter() - start_episode_t

                # --- 定期状态打印（每3秒） ---
                if frame_count % (FPS * 3) == 0:
                    joints = {k: v for k, v in observation.items() if k.endswith(".pos")}
                    # 计算与放球姿态的最大偏差
                    max_dev = 0.0
                    if detector:
                        for k, tv in detector.target_pose.items():
                            dev = abs(joints.get(k, 0) - tv)
                            max_dev = max(max_dev, dev)

                    status = "📦 等待放球后退出" if place_detected else "⏳ 运行中"
                    logger.info(
                        f"[{timestamp:.1f}s] {status} | "
                        f"与放球姿态最大偏差={max_dev:.1f} (阈值={POSE_TOLERANCE})"
                    )

            # --- 循环结束 ---
            if not place_detected and not should_exit:
                logger.info(f"⏰ 达到最大时间 {EPISODE_TIME_S}s")

            dataset.save_episode()
            logger.info(f"数据已保存（共 {frame_count} 帧）。")

    except Exception as e:
        logger.error(f"运行出错: {e}", exc_info=True)
    finally:
        logger.info("正在断开机械臂...")
        try:
            robot.disconnect()
        except Exception:
            pass

        if place_detected:
            logger.info("✅ 评估结果：任务完成（检测到放球动作）！")
        elif should_exit:
            logger.info("⚠️ 评估中断：用户手动退出。")
        else:
            logger.info("❌ 评估结果：超时，未检测到放球动作。")


if __name__ == "__main__":
    main()
