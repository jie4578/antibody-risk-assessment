# ml/transformer.py
# 最小 Transformer 编码器（可选，需安装 torch）。
#
# 目标：展示把抗体序列当作 token 序列，
# 用"位置编码 + 多头自注意力 + 前馈网络"做编码，再接分类头做风险预测。
#
# 说明：默认核心依赖不含 torch（轻量原则）。安装 torch 后可直接用
#   build_transformer_classifier(...) 训练一个最小 Transformer 分类器。
#   未安装 torch 时本模块导入不报错，但调用构建函数会给出清晰提示。

from __future__ import annotations

from typing import Optional


def build_transformer_classifier(
    vocab_size: int = 20,
    d_model: int = 64,
    nhead: int = 4,
    num_layers: int = 2,
    max_len: int = 128,
    num_classes: int = 2,
    dropout: float = 0.1,
):
    """构造一个把氨基酸序列映射为类别的小型 Transformer 分类器。

    需安装 torch：`pip install torch`。返回一个 torch.nn.Module。
    """
    try:
        import torch
        import torch.nn as nn
    except Exception as e:  # pragma: no cover - 环境未装 torch 时给出可读提示
        raise ImportError(
            "需要安装 torch 才能使用 Transformer：pip install torch（也可用 pip install '.[all]'）"
        ) from e

    class PositionalEncoding(nn.Module):
        def __init__(self, d_model: int, max_len: int, dropout: float):
            super().__init__()
            import math

            pe = torch.zeros(max_len, d_model)
            pos = torch.arange(0, max_len, dtype=torch.float32).unsqueeze(1)
            div = torch.exp(torch.arange(0, d_model, 2).float() * (-math.log(10000.0) / d_model))
            pe[:, 0::2] = torch.sin(pos * div)
            pe[:, 1::2] = torch.cos(pos * div)
            self.register_buffer("pe", pe.unsqueeze(0))
            self.dropout = nn.Dropout(dropout)

        def forward(self, x):
            x = x + self.pe[:, : x.size(1)]
            return self.dropout(x)

    class TransformerEncoder(nn.Module):
        def __init__(self):
            super().__init__()
            self.embedding = nn.Embedding(vocab_size, d_model)
            self.pos = PositionalEncoding(d_model, max_len, dropout)
            encoder_layer = nn.TransformerEncoderLayer(
                d_model=d_model, nhead=nhead, dim_feedforward=4 * d_model, dropout=dropout, batch_first=True
            )
            self.encoder = nn.TransformerEncoder(encoder_layer, num_layers=num_layers)
            self.fc = nn.Linear(d_model, num_classes)

        def forward(self, x):
            # x: (batch, seq_len) 的氨基酸索引
            mask = (x != 0)  # padding=0 作为 mask
            x = self.embedding(x)
            x = self.pos(x)
            x = self.encoder(x, src_key_padding_mask=~mask)
            x = x.mean(dim=1)  # 平均池化 → (batch, d_model)
            return self.fc(x)

    return TransformerEncoder()
