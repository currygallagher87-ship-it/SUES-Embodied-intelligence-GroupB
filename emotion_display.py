#!/usr/bin/env python3
"""
表情显示服务 - 独立运行

监听状态文件 /tmp/robot_emotion.txt，根据内容播放对应的表情 GIF。
使用 OpenCV 窗口显示。

状态对应：
  search  → search.gif  （搜索/寻找球）
  success → success.gif （放球成功）
  sleep   → sleep.gif   （空闲/结束）

用法：
  在一个终端运行此脚本：
    python emotion_display.py

  在另一个终端运行评估脚本：
    python eval_with_grasp_detect.py

按 Q 或 Ctrl+C 退出。
"""

import os
import sys
import time
import cv2
import numpy as np
from PIL import Image

# ========== 配置 ==========
# GIF 文件所在目录
GIF_DIR = "/home/lip/桌面/Sequence needle (2)/Sequence needle"

# 状态文件路径（eval 脚本写入，本脚本读取）
STATE_FILE = "/tmp/robot_emotion.txt"

# 表情名 → GIF 文件名 的映射
EMOTION_MAP = {
    "search":  "search.gif",
    "success": "success.gif",
    "sleep":   "sleep.gif",
    "grab":    "grab.gif",
    "fail":    "fail.gif",
    "avoid":   "avoid.gif",
}

# 默认表情（启动时 / 状态文件不存在时）
DEFAULT_EMOTION = "sleep"

# 窗口显示缩放倍数（1.0 = 原始大小，2.0 = 放大两倍）
DISPLAY_SCALE = 1.5

# GIF 帧间隔（毫秒），越小播放越快
FRAME_DELAY_MS = 80
# ===========================


def load_gif_frames(gif_path: str) -> list[np.ndarray]:
    """用 PIL 读取 GIF 所有帧，转为 OpenCV BGR 格式"""
    pil_img = Image.open(gif_path)
    frames = []
    try:
        while True:
            # 转为 RGBA 确保一致性
            frame = pil_img.convert("RGBA")
            arr = np.array(frame)
            # RGBA → BGR（丢弃 alpha，或者你可以处理透明）
            bgr = cv2.cvtColor(arr, cv2.COLOR_RGBA2BGR)
            frames.append(bgr)
            pil_img.seek(pil_img.tell() + 1)
    except EOFError:
        pass
    return frames


def read_emotion() -> str:
    """读取状态文件中的表情名"""
    try:
        with open(STATE_FILE, "r") as f:
            emotion = f.read().strip()
        if emotion in EMOTION_MAP:
            return emotion
    except FileNotFoundError:
        pass
    return DEFAULT_EMOTION


def main():
    # 预加载所有 GIF
    print("正在加载表情动画...")
    emotion_frames: dict[str, list[np.ndarray]] = {}
    for emotion, gif_name in EMOTION_MAP.items():
        gif_path = os.path.join(GIF_DIR, gif_name)
        if os.path.exists(gif_path):
            frames = load_gif_frames(gif_path)
            emotion_frames[emotion] = frames
            print(f"  ✅ {emotion}: {len(frames)} 帧")
        else:
            print(f"  ⚠️ {emotion}: {gif_path} 不存在，跳过")

    if not emotion_frames:
        print("❌ 没有加载到任何表情动画！")
        sys.exit(1)

    # 写入默认状态
    with open(STATE_FILE, "w") as f:
        f.write(DEFAULT_EMOTION)

    print(f"\n🎭 表情显示已启动！监听: {STATE_FILE}")
    print(f"   当前: {DEFAULT_EMOTION}")
    print("   按 Q 退出\n")

    cv2.namedWindow("Robot Emotion", cv2.WINDOW_NORMAL)

    current_emotion = DEFAULT_EMOTION
    frame_idx = 0
    last_check_time = 0

    try:
        while True:
            # 每 0.5 秒检查一次状态文件（不需要太频繁）
            now = time.time()
            if now - last_check_time > 0.5:
                new_emotion = read_emotion()
                if new_emotion != current_emotion and new_emotion in emotion_frames:
                    current_emotion = new_emotion
                    frame_idx = 0  # 切换表情时从头播放
                    print(f"🔄 表情切换: {current_emotion}")
                last_check_time = now

            # 播放当前表情的帧
            if current_emotion in emotion_frames:
                frames = emotion_frames[current_emotion]
                frame = frames[frame_idx % len(frames)]

                # 缩放
                if DISPLAY_SCALE != 1.0:
                    h, w = frame.shape[:2]
                    new_w = int(w * DISPLAY_SCALE)
                    new_h = int(h * DISPLAY_SCALE)
                    frame = cv2.resize(frame, (new_w, new_h), interpolation=cv2.INTER_LINEAR)

                cv2.imshow("Robot Emotion", frame)
                frame_idx += 1

            # 等待 & 检测按键
            key = cv2.waitKey(FRAME_DELAY_MS) & 0xFF
            if key == ord('q') or key == ord('Q'):
                break

    except KeyboardInterrupt:
        pass
    finally:
        cv2.destroyAllWindows()
        # 清理状态文件
        try:
            os.remove(STATE_FILE)
        except FileNotFoundError:
            pass
        print("表情显示已关闭。")


if __name__ == "__main__":
    main()
