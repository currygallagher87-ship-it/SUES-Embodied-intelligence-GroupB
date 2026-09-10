import scservo_sdk

port = '/dev/leader_arm'
baudrate = 1000000  # Feetech 舵机默认波特率 1Mbps

# 初始化端口和协议 (1 代表 STS/SCS 协议)
portHandler = scservo_sdk.PortHandler(port)
packetHandler = scservo_sdk.PacketHandler(1)

if not portHandler.openPort():
    print(f"❌ 串口 {port} 打开失败！请检查连接或权限。")
    exit()

if not portHandler.setBaudRate(baudrate):
    print("❌ 波特率设置失败！")
    exit()

print("🔍 开始暴力扫描总线上的电机 (ID 0 到 15)...")
print("-" * 40)

found_ids = []
for i in range(16):
    model_number, comm_result, error = packetHandler.ping(portHandler, i)
    if comm_result == scservo_sdk.COMM_SUCCESS:
        print(f"✅ 成功找到电机！当前 ID: {i} (型号代码: {model_number})")
        found_ids.append(i)

print("-" * 40)
print(f"📊 扫描结束。共找到 {len(found_ids)} 个电机。在线 ID 列表: {found_ids}")

portHandler.closePort()
