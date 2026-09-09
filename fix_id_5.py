import scservo_sdk
import time

port = '/dev/leader_arm'
baudrate = 1000000

portHandler = scservo_sdk.PortHandler(port)
packetHandler = scservo_sdk.PacketHandler(1)

if not portHandler.openPort():
    print("❌ 串口打开失败！")
    exit()

portHandler.setBaudRate(baudrate)

# 目标明确：把现在的冒牌 6 号，改回真正的 5 号
old_id = 6
new_id = 5

print(f"🔧 准备将冒牌的 ID {old_id} 强行纠正为手腕专属 ID {new_id}...")

# 1. 解锁 EEPROM (向地址 48 写入 0)
packetHandler.write1ByteTxRx(portHandler, old_id, 48, 0)
time.sleep(0.1)

# 2. 修改 ID (向地址 5 写入新的 ID)
packetHandler.write1ByteTxRx(portHandler, old_id, 5, new_id)
time.sleep(0.1)

# 3. 锁定 EEPROM (向地址 48 写入 1，注意此时要用新 ID 去通信)
packetHandler.write1ByteTxRx(portHandler, new_id, 48, 1)

print("✅ 修改指令已发送！正在验证...")
time.sleep(0.5)

# 验证是否修改成功
model, result, error = packetHandler.ping(portHandler, new_id)
if result == scservo_sdk.COMM_SUCCESS:
    print(f"🎉 验证成功！手腕电机已重生，当前真实 ID 为: {new_id}")
else:
    print("❌ 验证失败，请检查连线。")

portHandler.closePort()
