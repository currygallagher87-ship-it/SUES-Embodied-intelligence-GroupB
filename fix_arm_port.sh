#!/bin/bash

# 确保以 root 权限运行，因为修改 udev 规则需要系统权限
if [ "$EUID" -ne 0 ]; then
  echo "请使用 sudo 运行此脚本 (例如: sudo ./fix_arm_port.sh)"
  exit 1
fi

echo "=== LeRobot 机械臂端口绑定脚本 ==="

# 1. 获取当前设备路径
read -p "请输入机械臂当前的端口路径 (例如 /dev/ttyCH343USB0 或 /dev/ttyUSB0): " DEVICE_PATH

if [ ! -e "$DEVICE_PATH" ]; then
    echo "错误: 找不到设备 $DEVICE_PATH。请确认机械臂已通过 USB 连接并开机。"
    exit 1
fi

# 2. 获取目标映射名
read -p "请输入您想要固定的端口名称 (例如 follower_arm): " SYMLINK_NAME

if [ -z "$SYMLINK_NAME" ]; then
    echo "未输入名称，将使用默认名称: follower_arm"
    SYMLINK_NAME="follower_arm"
fi

# 3. 提取唯一序列号 (Serial)
# 使用 udevadm info 提取 serial，通常存在于 ATTRS{serial} 中
SERIAL=$(udevadm info -a -n "$DEVICE_PATH" | grep -m 1 '{serial}' | awk -F '"' '{print $2}')

if [ -z "$SERIAL" ]; then
    echo "错误: 无法从 $DEVICE_PATH 提取唯一的 serial 编号。请确保设备具有唯一硬件编码。"
    exit 1
fi

echo "成功获取设备唯一编号: $SERIAL"

# 4. 写入 udev 规则
RULES_DIR="/etc/udev/rules.d"
RULE_FILE="${RULES_DIR}/99-lerobot.rules"

# 构造 udev 规则字符串 (MODE="0666" 确保非 root 用户也能读写，防止 LeRobot 运行报权限错)
RULE="SUBSYSTEM==\"tty\", ATTRS{serial}==\"$SERIAL\", MODE=\"0666\", SYMLINK+=\"$SYMLINK_NAME\""

echo "正在生成 udev 规则并写入 $RULE_FILE ..."
# 将新规则追加到文件中（如果配置多台机械臂，规则会逐行添加）
echo "$RULE" >> "$RULE_FILE"

# 5. 重新加载并触发 udev 规则
echo "正在重新加载 udev 规则..."
udevadm control --reload-rules
udevadm trigger

echo "=== 配置完成 ==="
echo "请拔插一次机械臂的 USB 线，使规则完全生效。"
echo "之后您可以通过 /dev/$SYMLINK_NAME 来稳定访问该设备。"
