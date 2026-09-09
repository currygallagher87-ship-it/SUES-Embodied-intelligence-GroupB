import scservo_sdk
import time
import json
import os
import sys

# 【配置区】由于是Leader Arm主臂，通常连接 /dev/leader_arm
PORT = '/dev/leader_arm'
BAUDRATE = 1000000

# 初始化串口与包处理器
portHandler = scservo_sdk.PortHandler(PORT)
packetHandler = scservo_sdk.PacketHandler(1)

# 【防呆检查】如果串口被其他脚本占用，立刻拦截报错
if not portHandler.openPort():
    print(f"❌ 严重错误：无法打开串口 {PORT}！")
    print("💡 解决方案：请确保 lerobot-calibrate 或其他读取机械臂的脚本已经 [完全关闭]（Ctrl+C），否则会发生串口独占冲突。")
    sys.exit(1)

portHandler.setBaudRate(BAUDRATE)

def main():
    print("🤖 欢迎使用：防呆级·手动动作录制系统")
    print("-" * 50)
    
    # 第一步：卸载所有舵机力矩，让机械臂变软，允许手动拖拽
    for i in range(1, 7):
        packetHandler.write1ByteTxRx(portHandler, i, 40, 0) # 内存地址 40 是扭矩开关，0 代表关闭扭矩
    
    print("✅ 力矩已全部卸载！现在您可以随意拖拽机械臂。")
    print("🔴 准备录制中... (请将机械臂移动到您想要的起始动作位置)")
    time.sleep(3)
    
    trajectory = []
    record_time = 60.0 # 默认录制 60 秒
    hz = 10 # 采集频率，10Hz代表每秒记录10个关键帧，对缓慢动作足够了
    interval = 1.0 / hz
    
    print("⏺️ 正在录制 (持续60秒)... 【随时可按 Ctrl+C 提前结束录制】")
    
    try:
        start_time = time.time()
        while time.time() - start_time < record_time:
            frame = {}
            # 读取每个关节的位置 (1到6)
            for i in range(1, 7):
                pos, comm, err = packetHandler.read2ByteTxRx(portHandler, i, 56) # 内存地址 56 是当前真实位置
                if comm == scservo_sdk.COMM_SUCCESS:
                    frame[i] = pos
            
            # 只有当6个舵机的数据都成功读到，才算一次有效的关键帧，避免跳帧杂音数据
            if len(frame) == 6: 
                trajectory.append(frame)
            
            time.sleep(interval)
    except KeyboardInterrupt:
        print("\n🛑 检测到人为中断，录制提前结束。")
        
    # 将录制的数据保存为 JSON 动作文件
    save_path = os.path.join(os.path.dirname(__file__), 'trajectory.json')
    with open(save_path, 'w') as f:
        json.dump(trajectory, f, indent=4)
        
    print("-" * 50)
    print(f"💾 录制完美收官！共记录了 {len(trajectory)} 帧动作数据。")
    print(f"📁 动作文件已安全存放于：{save_path}")
    print("👉 接下来，您可以随时运行 play_trajectory.py 来回放这段动作！")
    
    portHandler.closePort()

if __name__ == "__main__":
    main()
