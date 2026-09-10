import scservo_sdk
import time
import sys

PORT = '/dev/leader_arm'
BAUDRATE = 1000000

# ----------------- 极致安全配置 -----------------
SAFE_REST_POSTURE = {
    1: 38407,
    2: 32259,
    3: 22543,
    4: 61963,
    5: 45319,
    6: 31750
}

SPEED_LIMIT = 400      # 限速锁再降 33%！绝对的慢动作
ACCEL = 30             

STEP_SIZE = 5          
STEP_DELAY = 0.02      
BLOCK_THRESHOLD = 25   
BACKOFF = 150          
# ------------------------------------------------

portHandler = scservo_sdk.PortHandler(PORT)
packetHandler = scservo_sdk.PacketHandler(1)

if not portHandler.openPort():
    print("❌ 串口打开失败！请检查连线。")
    sys.exit(1)
portHandler.setBaudRate(BAUDRATE)

def safe_speed_move(motor_id, target_pos):
    """【闭环等待函数】不走到位置，绝不放行！"""
    print(f"   🧘 ID {motor_id} 正在缓慢平滑移动至 {target_pos}...")
    packetHandler.write1ByteTxRx(portHandler, motor_id, 40, 1) # 永不断电
    packetHandler.write1ByteTxRx(portHandler, motor_id, 41, ACCEL)
    packetHandler.write2ByteTxRx(portHandler, motor_id, 44, 0)
    packetHandler.write2ByteTxRx(portHandler, motor_id, 46, SPEED_LIMIT) 
    
    packetHandler.write2ByteTxRx(portHandler, motor_id, 42, target_pos)

    # 动态侦测是否到达（误差小于 15 步视为到达）
    last_pos_for_check = -1
    stuck_frames = 0
    while True:
        actual_pos, comm, err = packetHandler.read2ByteTxRx(portHandler, motor_id, 56)
        if comm == scservo_sdk.COMM_SUCCESS:
            diff = abs(target_pos - actual_pos)
            error = min(diff, 65536 - diff)
            if error < 15:
                break
                
            # 防止机械卡死导致无限死循环
            diff_from_last = abs(actual_pos - last_pos_for_check)
            if min(diff_from_last, 65536 - diff_from_last) < 4:
                stuck_frames += 1
            else:
                stuck_frames = 0
                
            if stuck_frames > 40: # 约 2 秒停滞
                print("   ⚠️ 警告：到达目标前卡住，已提前放行。")
                break
                
            last_pos_for_check = actual_pos
        time.sleep(0.05) # 高频侦测
    print(f"   ✅ 稳稳到达。")

def find_limit(motor_id, direction, name):
    # 读初始位置
    actual_pos = None
    while actual_pos is None:
        pos, comm, err = packetHandler.read2ByteTxRx(portHandler, motor_id, 56)
        if comm == scservo_sdk.COMM_SUCCESS:
            actual_pos = pos

    steps_taken = 0
    target_pos = actual_pos
    recent_positions = []

    packetHandler.write1ByteTxRx(portHandler, motor_id, 40, 1)
    packetHandler.write1ByteTxRx(portHandler, motor_id, 41, 0) # 试探无加速，保证灵敏
    packetHandler.write2ByteTxRx(portHandler, motor_id, 44, 0) 
    packetHandler.write2ByteTxRx(portHandler, motor_id, 46, SPEED_LIMIT)

    print(f"🔍 ID {motor_id} 开始向【{name}】盲探 (起点: {actual_pos})...")

    while True:
        target_pos = (target_pos + (STEP_SIZE * direction)) % 65536
        packetHandler.write2ByteTxRx(portHandler, motor_id, 42, target_pos)
        
        time.sleep(STEP_DELAY)

        # 读取新位置
        new_actual_pos, comm, err = packetHandler.read2ByteTxRx(portHandler, motor_id, 56)
        if comm != scservo_sdk.COMM_SUCCESS:
            continue

        recent_positions.append(new_actual_pos)
        if len(recent_positions) > 10:
            recent_positions.pop(0)

        diff = abs(target_pos - new_actual_pos)
        error = min(diff, 65536 - diff)
        
        # 防止target_pos跑得太远产生过大拉力
        if error > 50:
            target_pos = (new_actual_pos + (50 * direction)) % 65536
            
        # 稳健的物理阻塞检测：0.2秒内位置变化极小
        if len(recent_positions) == 10:
            pos_diff = abs(recent_positions[-1] - recent_positions[0])
            pos_diff = min(pos_diff, 65536 - pos_diff)
            if pos_diff <= 2: 
                print(f"   🛑 触墙拦截！当前位置: {new_actual_pos} (检测到物理阻力)")
                actual_pos = new_actual_pos
                break
            
        actual_pos = new_actual_pos
        steps_taken += STEP_SIZE
        if steps_taken > 4500:
            print(f"   ⚠️ 达到单向最大探索行程，防空转保护触发！")
            break

    # 回撤并闭环等待
    safe_limit = (actual_pos - (BACKOFF * direction)) % 65536
    print("   🔙 正在回撤释放应力...")
    safe_speed_move(motor_id, safe_limit)
    
    return safe_limit

# ================= 核心执行流 =================
limits_result = {}

print("🤖 逆向极端安全探测系统启动！(真实闭环控制版)")
print("⚠️ 请将手放在电源上！\n")
time.sleep(2)

print("🛡️ 初始化：机械臂正在极低速展开至安全基准态...")
for i in range(6, 0, -1):
    safe_speed_move(i, SAFE_REST_POSTURE[i])

# 在每个大步骤之间增加停顿缓冲
time.sleep(1)

for i in range(6, 0, -1):
    print(f"\n================ 开始测试 ID {i} ================")
    
    min_val = find_limit(i, -1, "最小值")
    time.sleep(0.5)
    
    # 【修复】返回安全基准位置，避免接下来的最大值测试需要跨过整个量程导致行程超限
    print("   🔄 返回安全基准位置中转...")
    safe_speed_move(i, SAFE_REST_POSTURE[i])
    time.sleep(0.5)
    
    max_val = find_limit(i, 1, "最大值")
    
    if min_val is not None and max_val is not None:
        limits_result[i] = {"min": min_val, "max": max_val}
        
    print(f"   🔄 测试完毕，ID {i} 闭环归位...")
    safe_speed_move(i, SAFE_REST_POSTURE[i])
    time.sleep(0.5)

print("\n🎉 逆向限速探测完美结束！物理极限档案如下：")
print("-" * 50)
print("SAFE_LIMITS = {")
for motor_id in sorted(limits_result.keys()):
    print(f"    {motor_id}: [{limits_result[motor_id]['min']}, {limits_result[motor_id]['max']}],")
print("}")
print("-" * 50)

portHandler.closePort()
