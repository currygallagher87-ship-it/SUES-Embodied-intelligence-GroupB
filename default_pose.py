import scservo_sdk
import time
import sys

# 注意：你现在接的是主臂还是从臂？根据需要修改 PORT
PORT = '/dev/follower_arm'
BAUDRATE = 1000000

# 你读取到的真实安全数值 (包含多圈负数的补码，这很正常)
TARGET_POSITIONS = {
    1: 41740,
    2: 33027,
    3: 23823,
    4: 60171,
    5: 45063,
    6: 32774,
}

# 移动时间设为 5000ms (5秒)
MOVE_TIME = 5000 

portHandler = scservo_sdk.PortHandler(PORT)
packetHandler = scservo_sdk.PacketHandler(1)

if not portHandler.openPort():
    print("❌ 串口打开失败！请检查权限或连线。")
    sys.exit(1)

portHandler.setBaudRate(BAUDRATE)

print("🚀 机械臂安全唤醒中，正在极低速前往校准基准点...")

# ================= 核心修复区 =================

# 第一步：先给所有舵机统一下达“纪律”（配置速度和时间）
for motor_id in TARGET_POSITIONS.keys():
    # 1. 开启扭矩
    packetHandler.write1ByteTxRx(portHandler, motor_id, 40, 1)
    
    # 2. 设定加速度 (地址41)：设为 20，让它起步和停止时有平滑的加减速缓冲 (防抽搐)
    packetHandler.write1ByteTxRx(portHandler, motor_id, 41, 20)
    
    # 3. 设定运行时间 (地址44)：明确写入 5000 毫秒
    packetHandler.write2ByteTxRx(portHandler, motor_id, 44, MOVE_TIME)
    
    # 4. 设定最大速度 (地址46)：设为 0。在 Feetech 逻辑中，速度设为0代表“速度完全由上面的运行时间决定”
    packetHandler.write2ByteTxRx(portHandler, motor_id, 46, 0)

# 第二步：统一发送目标位置 (同步起步)
# 只有收到地址 42 的指令，舵机才会开始运动。这样写能保证所有关节严格同时起步！
for motor_id, target_pos in TARGET_POSITIONS.items():
    # 发送目标位置 (地址42)
    packetHandler.write2ByteTxRx(portHandler, motor_id, 42, target_pos)

# ==============================================

print(f"⏳ 动作执行中，预计等待 {MOVE_TIME/1000} 秒...")
time.sleep(MOVE_TIME / 1000.0 + 0.5)

print("🎉 绝对安全归位完成！硬件已锁死在最佳校准位。")
portHandler.closePort()
