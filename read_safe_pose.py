import scservo_sdk

PORT = '/dev/leader_arm'
BAUDRATE = 1000000

portHandler = scservo_sdk.PortHandler(PORT)
packetHandler = scservo_sdk.PacketHandler(1)

if not portHandler.openPort():
    print("❌ 串口打开失败！请检查连接或权限。")
    exit()
portHandler.setBaudRate(BAUDRATE)

print("🔍 正在读取当前完美姿态的绝对坐标...\n")
safe_positions = {}

# 遍历 1 到 6 号舵机
for i in range(1, 7):
    # Feetech 内存表：地址 56 是当前位置 (Present Position，2字节)
    pos, comm, err = packetHandler.read2ByteTxRx(portHandler, i, 56)
    if comm == scservo_sdk.COMM_SUCCESS:
        safe_positions[i] = pos
        print(f"ID {i}: {pos}")
    else:
        print(f"⚠️ ID {i} 读取失败，请检查连线！")

print("\n✅ 读取完成！请将上面的数值复制，填入归位脚本中。")
portHandler.closePort()
