import scservo_sdk

PORT = '/dev/follower_arm'
BAUDRATE = 1000000

portHandler = scservo_sdk.PortHandler(PORT)
packetHandler = scservo_sdk.PacketHandler(1)

if not portHandler.openPort():
    print("❌ 串口打开失败！")
    exit()

portHandler.setBaudRate(BAUDRATE)

print("🧘 正在释放所有关节力矩...")

for i in range(1, 7):
    # 向地址 40 写入 0 (Torque Off)
    result, error = packetHandler.write1ByteTxRx(portHandler, i, 40, 0)
    if result == scservo_sdk.COMM_SUCCESS:
        print(f"✅ ID {i} 卸力成功，现在可以自由转动。")
    else:
        print(f"⚠️ ID {i} 卸力失败！")

print("\n🎉 机械臂已进入[自由拖动模式]！")
print("👉 请手动将其摆放到完美校准姿态，然后运行 read_safe_pose.py")

portHandler.closePort()
