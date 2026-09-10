#!/usr/bin/env python3
"""
关节姿态标定工具

连接已校准的 SO101 机械臂，禁用扭矩让你手动操作。
实时显示所有关节数值（原地刷新）。

按 Enter 键可以保存当前姿态到文件，供 eval_with_grasp_detect.py 使用。

用法（在仓库根目录执行）：
  python tools/grasp/grasp_debug.py

操作：
  1. 手动把机械臂摆到"放球位置"
  2. 按 Enter 保存该姿态
  3. 按 Ctrl+C 退出

保存的姿态文件：与本脚本同目录的 place_pose.json
"""

import json
import time
import signal
import sys
import os
import logging
import threading
from pathlib import Path

from lerobot.cameras.opencv.configuration_opencv import OpenCVCameraConfig
from lerobot.robots.so101_follower import SO101Follower, SO101FollowerConfig

# ========== 配置 ==========
ROBOT_PORT = "/dev/follower_arm"
ROBOT_ID = "my_awesome_follower_arm"
CAMERAS = {
    "handeye": OpenCVCameraConfig(index_or_path=2, width=640, height=480, fps=30),
    "front": OpenCVCameraConfig(index_or_path=0, width=640, height=480, fps=30),
}
# 姿态文件固定保存在本脚本所在目录，无论从哪个工作目录运行都能正确读写
POSE_FILE = str(Path(__file__).resolve().parent / "place_pose.json")
# ==========================

logging.basicConfig(level=logging.WARNING)


def main():
    robot = None
    enter_pressed = threading.Event()
    should_exit = threading.Event()

    def signal_handler(sig, frame):
        print("\033[?25h")  # 恢复光标
        should_exit.set()

    signal.signal(signal.SIGINT, signal_handler)

    # 后台线程监听键盘输入
    def input_listener():
        while not should_exit.is_set():
            try:
                input()  # 阻塞等待 Enter
                enter_pressed.set()
            except EOFError:
                break

    input_thread = threading.Thread(target=input_listener, daemon=True)
    input_thread.start()

    config = SO101FollowerConfig(port=ROBOT_PORT, id=ROBOT_ID, cameras=CAMERAS)
    robot = SO101Follower(config)

    print("正在连接机械臂...")
    robot.connect()

    print("禁用扭矩，你可以手动移动机械臂...")
    robot.bus.disable_torque()

    # 获取关节名
    obs = robot.get_observation()
    joint_names = [k for k in obs.keys() if k.endswith(".pos")]

    # 隐藏光标
    print("\033[?25l", end="")

    saved_pose = None
    start_time = time.time()

    try:
        while not should_exit.is_set():
            elapsed = time.time() - start_time
            obs = robot.get_observation()

            # 检查是否按了 Enter
            if enter_pressed.is_set():
                enter_pressed.clear()
                saved_pose = {k: obs[k] for k in joint_names}
                # 保存到文件
                with open(POSE_FILE, "w") as f:
                    json.dump(saved_pose, f, indent=2)

            # 构建显示
            lines = []
            lines.append(f"  关节姿态标定工具  |  {elapsed:.0f}s  |  Enter=保存姿态  Ctrl+C=退出")
            lines.append("=" * 55)
            lines.append(f"  {'关节':<20s}  {'当前值':>10s}  {'已保存':>10s}")
            lines.append("-" * 55)
            for name in joint_names:
                val = obs.get(name, 0.0)
                short = name.replace(".pos", "")
                saved_str = f"{saved_pose[name]:.2f}" if saved_pose and name in saved_pose else "-"
                lines.append(f"  {short:<20s}  {val:>10.2f}  {saved_str:>10s}")
            lines.append("-" * 55)

            if saved_pose:
                lines.append(f"  ✅ 姿态已保存到 {POSE_FILE}")
                lines.append(f"     可以继续调整后再按 Enter 覆盖保存")
            else:
                lines.append(f"  ⏳ 把机械臂摆到放球位置，然后按 Enter 保存")

            lines.append("=" * 55)

            output = "\033[H\033[J" + "\n".join(lines)
            sys.stdout.write(output)
            sys.stdout.flush()

            time.sleep(0.2)

    except KeyboardInterrupt:
        pass
    finally:
        print("\033[?25h")  # 恢复光标
        print("\n\n断开连接...")
        if robot and robot.is_connected:
            robot.disconnect()
        if saved_pose:
            print(f"姿态已保存到: {POSE_FILE}")
            print("内容:")
            for k, v in saved_pose.items():
                print(f"  {k}: {v:.2f}")
        print("完成。")


if __name__ == "__main__":
    main()
