#!/usr/bin/env python

# Copyright 2024 Tony Z. Zhao and The HuggingFace Inc. team. All rights reserved.
#
# Licensed under the Apache License, Version 2.0 (the "License");
# you may not use this file except in compliance with the License.
# You may obtain a copy of the License at
#
#     http://www.apache.org/licenses/LICENSE-2.0
#
# Unless required by applicable law or agreed to in writing, software
# distributed under the License is distributed on an "AS IS" BASIS,
# WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
# See the License for the specific language governing permissions and
# limitations under the License.
from dataclasses import dataclass, field

from lerobot.configs.policies import PreTrainedConfig
from lerobot.configs.types import NormalizationMode
from lerobot.optim.optimizers import AdamWConfig


@PreTrainedConfig.register_subclass("act")
@dataclass
class ACTConfig(PreTrainedConfig):
    """ACT (Action Chunking Transformers) 策略的配置类。
    由于交由 HuggingFace 风格的框架管理，这里继承了 PreTrainedConfig，并支持直接反序列化。
    """

    # 1. 输入 / 输出结构 (Input / output structure)
    n_obs_steps: int = 1  # 丢给策略模型的环境观测历史步数（默认 1，即只看当前时刻）
    chunk_size: int = 100 # 动作分块大小：一次性预测未来多少步的系列动作
    n_action_steps: int = 100 # 实际在物理环境中执行的步数。它决定了多久调用一次模型。若是想开启平滑集成，必须设为 1

    normalization_mapping: dict[str, NormalizationMode] = field(
        default_factory=lambda: {
            "VISUAL": NormalizationMode.MEAN_STD, # 图像采用均值-标准差归一化
            "STATE": NormalizationMode.MEAN_STD,  # 关节状态采用均值-标准差归一化
            "ACTION": NormalizationMode.MEAN_STD, # 动作采用均值-标准差归一化
        }
    )

    # 2. 架构配置 (Architecture)
    # 视觉基座网络 (Vision backbone)
    vision_backbone: str = "resnet18" # 用于编码图片的 Torchvision 骨干网络名称
    pretrained_backbone_weights: str | None = "ResNet18_Weights.IMAGENET1K_V1" # 使用 ImageNet 预训练权重
    replace_final_stride_with_dilation: int = False # 是否用空洞卷积替换 ResNet 最后的 2x2 步长下采样操作
    
    # 3. Transformer 网络层配置 (Transformer layers)
    pre_norm: bool = False # 在 Transformer 块中是否使用 pre-norm
    dim_model: int = 512 # Transformer 的主要隐藏维度
    n_heads: int = 8 # 多头注意力的头数
    dim_feedforward: int = 3200 # 前馈神经网络扩展后的隐层维度
    feedforward_activation: str = "relu" # 激活函数
    n_encoder_layers: int = 4 # Encoder 编码器层数，负责融合多视角图像和当前的关节状态信息
    # 注意：原版 ACT 有一个 Bug 导致只用到 1 层 Decoder。此处为了对齐原版算法的实际表现也设为 1。
    n_decoder_layers: int = 1 
    
    # 4. VAE（变分自编码器）配置：ACT 处理多种抓取分布（动作多模态）的精髓组件
    use_vae: bool = True # 是否在训练期间使用变分目标（即 CVAE）引入动作随机性
    latent_dim: int = 32 # VAE 隐维度的长度（这 32 位向量压缩了人类某次特定示范轨迹的特征/风格）
    n_vae_encoder_layers: int = 4 # VAE 专属编码器的层数

    # 5. 推理阶段特有优化 (Inference)
    # 如果开启时序集成（即每步都推理，对重叠预测动作加权平均）来平滑动作，原版建议此处使用 0.01
    temporal_ensemble_coeff: float | None = None

    # 6. 训练和损失计算超参 (Training and loss computation)
    dropout: float = 0.1 # 随机丢弃率，防止死记硬背
    kl_weight: float = 10.0 # VAE 中 KL 散度损失项的权重。控制“模仿”和“泛化生成”的比重。

    # 7. 优化器/训练超参预设 (Training preset)
    optimizer_lr: float = 1e-5 # Transformer 这边的基础学习率
    optimizer_weight_decay: float = 1e-4 # 权重衰减惩罚（正则化项），同样用于抗过拟合
    optimizer_lr_backbone: float = 1e-5 # 视觉骨干网络 (ResNet) 那里单独偏小的学习率

    def __post_init__(self):
        super().__post_init__()

        """输入与约束验证逻辑。"""
        if not self.vision_backbone.startswith("resnet"):
            raise ValueError(
                f"`vision_backbone` must be one of the ResNet variants. Got {self.vision_backbone}."
            )
        if self.temporal_ensemble_coeff is not None and self.n_action_steps > 1:
            raise NotImplementedError(
                "`n_action_steps` must be 1 when using temporal ensembling. This is "
                "because the policy needs to be queried every step to compute the ensembled action."
            )
        if self.n_action_steps > self.chunk_size:
            raise ValueError(
                f"The chunk size is the upper bound for the number of action steps per model invocation. Got "
                f"{self.n_action_steps} for `n_action_steps` and {self.chunk_size} for `chunk_size`."
            )
        if self.n_obs_steps != 1:
            raise ValueError(
                f"Multiple observation steps not handled yet. Got `nobs_steps={self.n_obs_steps}`"
            )

    def get_optimizer_preset(self) -> AdamWConfig:
        return AdamWConfig(
            lr=self.optimizer_lr,
            weight_decay=self.optimizer_weight_decay,
        )

    def get_scheduler_preset(self) -> None:
        return None

    def validate_features(self) -> None:
        if not self.image_features and not self.env_state_feature:
            raise ValueError("You must provide at least one image or the environment state among the inputs.")

    @property
    def observation_delta_indices(self) -> None:
        return None

    @property
    def action_delta_indices(self) -> list:
        return list(range(self.chunk_size))

    @property
    def reward_delta_indices(self) -> None:
        return None
