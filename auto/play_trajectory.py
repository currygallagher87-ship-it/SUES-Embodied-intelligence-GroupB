import scservo_sdk
import time
import json
import os
import sys

# ================= 极致安全配置区 =================
# 【强制要求】请根据您的实际环境，填入绝对安全的初始收纳坐标
# 提示：这应该是一组机械臂完全蜷缩、不容易碰到桌面的坐标
TARGET_POSITIONS = {
    1: 38407,  # 基座 (Base)
    2: 32259,  # 肩部 (Shoulder)
    3: 22543,  # 肘部 (Elbow)
    4: 61963,  # 腕部俯仰 (Wrist Pitch)
    5: 45319,  # 腕部翻滚 (Wrist Roll)
    6: 31750   # 夹爪 (Gripper)
}

# 极限低速和柔和的加速度，杜绝任何猛烈抖动
SPEED_LIMIT = 400
ACCEL = 30
# ================================================

# 【防呆检查 1】：检查用户是否妥善配置了安全坐标
if not TARGET_POSITIONS or len(TARGET_POSITIONS) != 6:
    print("❌ 架构级安全告警：请在代码顶层 TARGET_POSITIONS 处填入 1~6 关节的安全初始坐标！拒绝运行不安全的代码。")
    sys.exit(1)
for k, v in TARGET_POSITIONS.items():
    if not isinstance(v, int) or v <= 0:
        print(f"❌ 架构级安全告警：关节 {k} 的安全坐标异常！拒绝运行。")
        sys.exit(1)

# 【防呆检查 2】：拦截串口冲突
PORT = '/dev/leader_arm'
BAUDRATE = 1000000

portHandler = scservo_sdk.PortHandler(PORT)
packetHandler = scservo_sdk.PacketHandler(1)

if not portHandler.openPort():
    print(f"❌ 严重错误：无法连接机械臂 (端口 {PORT} 受限)。")
    print("💡 解决方案：上一个脚本可能还在后台霸占串口！请确保录制脚本或者 calibrate 界面已被彻底关闭。")
    sys.exit(1)

portHandler.setBaudRate(BAUDRATE)

def safe_move_to(motor_id, target_pos, wait_arrive=True):
    """
    底层闭环单驱函数：每次只唤醒和驱动单个舵机，保证彻底的顺序控制
    wait_arrive=True 代表阻塞式执行，只有这一个舵机到位了，才允许下一个舵机动
    """
    packetHandler.write1ByteTxRx(portHandler, motor_id, 40, 1)    # 锁死力矩（通电）
    packetHandler.write1ByteTxRx(portHandler, motor_id, 41, ACCEL) # 推入温和加速度
    packetHandler.write2ByteTxRx(portHandler, motor_id, 44, 0)
    packetHandler.write2ByteTxRx(portHandler, motor_id, 46, SPEED_LIMIT) # 压制最大移动速率
    
    packetHandler.write2ByteTxRx(portHandler, motor_id, 42, target_pos) # 发送位移指令

    if wait_arrive:
        stuck_frames = 0
        last_pos = -1
        while True:
            # 动态巡查当前位置
            actual_pos, comm, err = packetHandler.read2ByteTxRx(portHandler, motor_id, 56)
            if comm == scservo_sdk.COMM_SUCCESS:
                diff = abs(target_pos - actual_pos)
                if min(diff, 65536 - diff) < 15: # 误差15步内视为触达
                    break
                
                # 防锁死机制
                diff_last = abs(actual_pos - last_pos)
                if min(diff_last, 65536 - diff_last) < 3:
                    stuck_frames += 1
                else:
                    stuck_frames = 0
                
                if stuck_frames > 40: # 若持续2秒位置不变，解除阻塞防止死循环
                    break
                last_pos = actual_pos
            time.sleep(0.05)

def main():
    # 读取同目录下的 JSON 保存动作
    save_path = os.path.join(os.path.dirname(__file__), 'trajectory.json')
    if not os.path.exists(save_path):
        print("❌ 致命错误：找不到动作记录文件 trajectory.json！")
        print("💡 请先运行 python3 record_trajectory.py 去录制一段动作。")
        portHandler.closePort()
        sys.exit(1)
        
    with open(save_path, 'r') as f:
        trajectory = json.load(f)
        
    if not trajectory or len(trajectory) == 0:
        print("❌ 错误：录制文件内没有任何动作信息 (0 帧)。请重新录制！")
        sys.exit(1)

    print("-" * 50)
    print("🛡️ 防呆级·安全回放系统正式启动...")
    print("-" * 50)
    
    print("👉 阶段 1/3：【防互砸归零】强制从末端向基座顺序收束...")
    # 强制采取 6 -> 5 -> 4 -> 3 -> 2 -> 1 纯单步串行
    for i in range(6, 0, -1):
        print(f"   ⮑  正在柔和收拢关节 {i} ...")
        safe_move_to(i, TARGET_POSITIONS[i], wait_arrive=True)
        
    print("\n👉 阶段 2/3：【轨迹预备】移动至录像第一帧起始点...")
    first_frame = trajectory[0]
    for i in range(6, 0, -1):
        target = first_frame[str(i)] # 从JSON读取出来的 key 是字符串 "1", "2" 等
        safe_move_to(i, target, wait_arrive=True)
        
    print("\n▶️ 阶段 3/3：按照原始时间轴回放录制动作，严格禁止群殴乱跑...")
    time.sleep(1) # 给操作者一点反应时间
    
    try:
        # 回放每一帧。在发送指令时，依然保持 6->1 的逻辑指令发出顺位。
        # 这里 wait_arrive=False 是因为要保持动作流畅连贯，不能一顿一顿的，但发送顺序绝对保证规则约束。
        for frame in trajectory:
            for i in range(6, 0, -1):
                target = frame[str(i)]
                safe_move_to(i, target, wait_arrive=False)
            
            time.sleep(0.1) # 严格校准：对标录制时的 10Hz 时长，1/10=0.1
    except KeyboardInterrupt:
        print("\n🛑 用户紧急打断了播放！")
        
    print("\n✅ 回放顺利结束！")
    print("🔁 阶段终：【防互砸归零】动作已谢幕，机械臂恢复收纳姿势...")
    for i in range(6, 0, -1):
        safe_move_to(i, TARGET_POSITIONS[i], wait_arrive=True)
        
    print("🎉 任务完美落幕，所有外设资源已安全释放。")
    portHandler.closePort()

if __name__ == "__main__":
    main()
