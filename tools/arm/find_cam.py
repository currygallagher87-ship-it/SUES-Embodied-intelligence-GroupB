import cv2

def list_available_cameras(max_tests=10):
    """
    列出所有可用的摄像头设备

    参数:
        max_tests (int): 要测试的最大摄像头索引数量，默认为10

    返回:
        list: 包含可用摄像头索引的列表
    """
    available_cameras = []
    consecutive_failures = 0
    max_consecutive_failures = 3  # 连续失败3次后停止检测

    for i in range(max_tests):
        cap = cv2.VideoCapture(i)
        if cap.isOpened():
            # 尝试读取一帧以确保摄像头真的可用
            ret, frame = cap.read()
            if ret:
                available_cameras.append(i)
                print(f"找到可用摄像头: 索引 {i}")
                consecutive_failures = 0  # 重置失败计数器
            else:
                consecutive_failures += 1
            cap.release()
        else:
            consecutive_failures += 1

        # 如果连续失败多次，说明可能已经检测完所有摄像头
        if consecutive_failures >= max_consecutive_failures:
            break

    if not available_cameras:
        print("未找到可用的摄像头设备")
    else:
        print(f"共找到 {len(available_cameras)} 个可用摄像头")

    return available_cameras

# 使用示例
if __name__ == "__main__":
    cameras = list_available_cameras()
