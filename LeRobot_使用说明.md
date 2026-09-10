# LeRobot 机械臂动态抓取平台：完整环境与使用手册

本文档是针对基于 LeRobot 与 SO101 机械臂二次开发的**动态捡球抓取平台**的完整使用手册。包含了从底层硬件配置、安全防护控制、数据集采集清洗，到最终的**自动化夹取检测、情绪联动与评估**的端到端全流程详细说明。

---

## 一、 环境依赖与硬件准备工作

### 1.1 软件环境安装
项目基于 Python 3.10+ 和 PyTorch 运行。请在激活相应的 Conda / 虚拟环境后，进入项目根目录执行：
```bash
# 基础安装
pip install -e .
# 如果连接的是 Feetech (飞特) 舵机，建议执行：
pip install -e ".[feetech]"
```
**情绪展示依赖**：为了运行新增的 `tools/grasp/emotion_display.py`，请确保安装了以下库：
```bash
pip install opencv-python numpy Pillow
```

### 1.2 硬件串口绑定与测试 (非常重要)
由于 Linux 系统每次重新插拔 USB 时端口号 (`/dev/ttyUSB0` 等) 可能会变动，这会导致程序找不到机械臂。
*   **固定串口**：提供了一个脚本自动化绑定唯一的端口名（如 `/dev/follower_arm`）：
    ```bash
    sudo bash tools/arm/fix_arm_port.sh
    ```
    *根据提示输入当前实际的 `/dev/ttyUSBx` 路径，脚本会提取硬件序列号，写入 udev 规则。完成后重新插拔一次 USB 线即可永久生效。*
*   **检查舵机连通性**：运行 `python tools/arm/scan.py`。该脚本会以 1Mbps 的波特率扫描总线上的电机，打印出所有在线的电机 ID，确保 1~6 号关节均正常在线。
*   **检查摄像头**：运行 `python tools/arm/find_cam.py`，列出系统中可用的摄像头 ID 索引。请根据输出结果，修改 `tools/grasp/eval_with_grasp_detect.py` 中的 `CAMERAS` 配置（如 `index_or_path=0` 和 `2`）。

---

## 二、 核心工作流：夹取姿态标定与自动化评估 (重点)

本次升级的核心功能是**“让机器人知道自己什么时候完成了任务，并给出情绪反馈自动停止”**。这需要以下三个脚本紧密配合：

### 2.1 步骤一：标定目标姿态 (`tools/grasp/grasp_debug.py`)
在进行自动检测前，我们需要设定一个基准的“放球/任务完成”姿态。
*   **运行命令**（在仓库根目录执行）：
    ```bash
    python tools/grasp/grasp_debug.py
    ```
*   **工作原理与操作**：
    1. 脚本启动后会连接机械臂，并**立刻卸载所有 6 个关节的力矩 (Torque Off)**。
    2. 此时机械臂处于软态，您可以**手动将其拖动**到完美的“放球位置”或“夹取成功位置”。
    3. 脚本会在终端**实时刷新**当前 6 个关节的绝对数值。
    4. 当您调整到满意的位置后，**按下 `Enter` (回车) 键**。
    5. 程序会将当前的 6 个关节数值提取，并保存至脚本同目录（`tools/grasp/`）下的 **`place_pose.json`** 文件中。终端会提示“✅ 姿态已保存”。
    6. **按下 `Ctrl + C`** 安全退出该工具。

### 2.2 步骤二：启动情绪与状态联动服务 (`tools/grasp/emotion_display.py`)
如果您的机器人配备了显示屏幕（如行空板），可以启动此服务提供可视化反馈。
*   **运行命令** (请开启一个全新的终端运行，使其常驻后台)：
    ```bash
    python tools/grasp/emotion_display.py
    ```
*   **工作原理**：
    该脚本独立于主程序运行，它以 0.5 秒的频率轮询读取 `/tmp/robot_emotion.txt` 文件。根据文件内的文本（如 `search`, `grab`, `success`, `sleep` 等），使用 OpenCV 在屏幕上无缝切换并播放对应的 GIF 动画。

### 2.3 步骤三：带夹取检测的自动化推理评估 (`tools/grasp/eval_with_grasp_detect.py`)
这是最核心的自动化控制脚本。在配置好 `tools/grasp/place_pose.json` 和策略模型路径后运行：
*   **运行命令**（在仓库根目录执行）：
    ```bash
    python tools/grasp/eval_with_grasp_detect.py
    ```
*   **脚本内部的自动化工作逻辑**：
    1. **初始化与加载**：脚本首先加载 `place_pose.json`，并连接摄像头、机械臂，最后将 ACT 模型加载到 GPU。
    2. **开场联动**：程序正式开始推理前，会通过终端运行 ROS2 命令：`ros2 topic pub ... 'grab'`，发送抓取指令。同时（或者通过修改状态文件的方式）让情绪系统显示“抓取中”。
    3. **实时检测容差 (Frame Detection)**：在死循环推理每一帧时，程序会将机械臂当前真实的 `observation` 关节位置，与 `place_pose.json` 中的目标位置相减。如果 **6 个关节的误差全部小于 `POSE_TOLERANCE` (默认 20.0 步)**，则计数器加一。
    4. **确认动作发生 (Debounce 机制)**：为了防止路过该位置造成的误判，只有当误差在容限内**连续保持 `POSE_MATCH_FRAMES` (默认 15 帧，约 0.5 秒)** 时，系统才正式确认“检测到放球姿态”。
    5. **动作缓冲延时 (Wait Buffer)**：确认放球后，程序不会粗暴中断导致球掉落。程序会触发一个 `AFTER_PLACE_WAIT_S` (默认 3.7 秒) 的倒计时。在这 3.7 秒内，模型依然会继续输出动作，以完成“松开夹爪并把手臂抬起”的连贯收尾。
    6. **成功判定与自动退出**：3.7 秒缓冲期结束，程序会在终端打印成功信息，**通过 ROS2 发送 `success` 成功指令**，保存本次评估的数据录像（如需），随后安全断开硬件并自动关闭 Python 进程。

---

## 三、 数据集管理与清洗工具链 (`tools/dataset/` 目录)

在训练前，难免会采集到损坏的或需要优化的数据片段，`tools/dataset/` 目录提供了一套离线数据集处理工具（无需写代码，在仓库根目录直接运行即可）。

*   **`tools/dataset/check_corruptions.py` (数据损坏筛查)**：
    批量读取数据集中的 `.parquet` 文件，检查 `timestamp` 字段。若发现时间戳倒退或异常跳跃，会打印出损坏的 `episode` 编号。
*   **`tools/dataset/delete_episode.py` (精准删除坏数据)**：
    用法：`python tools/dataset/delete_episode.py <episode_index>`。它不仅会物理删除对应的 `.parquet` 和 `.mp4` 文件，还会自动修正 `meta/episodes.jsonl` 和 `info.json` 中的总帧数与条目，保持数据集元数据的一致性。
*   **`tools/dataset/fix_dataset_59.py` (一次性修复脚本)**：
    针对特定损坏 episode 的元数据与文件清理，逻辑与 `delete_episode.py` 类似，可作为修复范例参考。
*   **`filter_dataset.py` (数据集截断提取)**：
    用于将一个庞大的数据集截取前 $N$ 条（例如前 181 条）并拷贝到一个新文件夹。自动更新所有的 Meta 数据，用于提纯高质量的基础数据。
*   **`merge_dataset.py` (无缝拼接数据集)**：
    这是最复杂也最常用的脚本。当您新采集了 40 条数据想并入原本 181 条的基础数据中时，该脚本会自动把新数据的 `episode_index` 和 `index` (帧号) 加上基数偏移，重命名视频文件，并修改底层 Parquet 表结构，最终合并成包含 221 条记录的完整数据集。

---

## 四、 机械臂安全调试与快捷控制指令

调试机械臂非常危险，稍有不慎可能造成撞击损坏。项目中包含一套底层的安全控制工具，均位于 `tools/arm/` 目录，在仓库根目录运行（例如 `python tools/arm/relax_arm.py`）：

### 4.1 基础快捷状态控制
*   **`tools/arm/relax_arm.py`**: 一键向所有 6 个关节发送 `Torque Off` (地址 40 写 0) 指令。使机械臂瞬间无力瘫软，方便人工将其摆放到安全位置。
*   **`tools/arm/read_safe_pose.py`**: 配合上方使用，摆放好后，运行此脚本会读取地址 56 的真实坐标，打印出当前完美姿态的各个关节数值，供记录使用。

### 4.2 极度安全的归位系统
*   **`tools/arm/default_pose.py` / `tools/arm/auto_pose.py`**:
    很多开源项目在归位时会让各个关节以最快速度直接冲向目标，极易砸到桌子。这两个脚本对 Feetech 舵机的底层寄存器做了精细控制：
    1. 强制写入加速度 `ACCEL=20` (地址 41)，确保起步平滑。
    2. 强制限制最高速度 `SPEED_LIMIT=0`，并将运行时间强行锁死为 5000 毫秒 (`MOVE_TIME=5000`)。
    3. 最后向地址 42 同步发送坐标。这保证了无论当前机械臂在什么扭曲的姿态，都会**像树懒一样极为缓慢且各个关节同步**地回归基准收纳姿态。

### 4.3 物理极值探测 (`tools/arm/auto_find_limits.py`)
当更换了机构或螺丝后，运行此脚本可以安全探索物理极限。它会以超低速度让关节向两侧盲探，利用闭环反馈：一旦检测到位置变化卡死（误差>15但物理位置不更新），立刻判定为碰到物理死区并回撤释放应力，自动为您总结出安全的 `SAFE_LIMITS`。

---

## 五、 手动动作轨迹录制与回放 (`auto/` 目录)

如果您不想使用复杂的视觉模型，只希望机械臂死记硬背重复一套动作，可以使用这里的工具：

*   **`auto/record_trajectory.py`**: 
    运行后自动卸载力矩，您开始拖动机械臂。脚本会以 10Hz 的频率默默记录下所有关节的轨迹，并在 60 秒（或按 Ctrl+C）后保存为 `trajectory.json`。
*   **`auto/play_trajectory.py`**: 
    **防呆级回放**。运行后，它不会立刻乱动。第一步：强制使用顺位 `6->5->4->3->2->1` 的安全防互砸顺序依次回到收纳姿态。第二步：安全移动到 JSON 录像的第一帧。第三步：精确还原 10Hz 的原始时间流进行动作回放。回放结束，再次安全收回。

---

## 六、 模型训练参考 (`setting.txt`)

当数据集（如 `data_all`）准备完毕后，可以通过根目录的 `lerobot.scripts.train` 模块启动 ACT (Action Chunking with Transformers) 的微调训练。
典型的高质量训练配置已记录在 `outputs/train/setting.txt`：
```bash
python -m lerobot.scripts.train \
  --policy.path=<预训练模型所在目录路径> \
  --dataset.repo_id=data_all \
  --dataset.root=<数据集绝对路径> \
  --dataset.image_transforms.enable=true \
  --policy.use_amp=true \
  --policy.optimizer_lr=2e-6 \
  --policy.optimizer_lr_backbone=1e-6 \
  --batch_size=64 \
  --steps=80000 \
  --num_workers=4 \
  --save_freq=10000 \
  --output_dir=outputs/train/act_finetune_model
```
*(注意：若要在训练中避免 OOM，可调整 `batch_size`，`use_amp=true` 能大幅降低显存占用)*
