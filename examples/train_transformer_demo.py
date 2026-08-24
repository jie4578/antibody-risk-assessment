# examples/train_transformer_demo.py
# 实测 ml/transformer.py：用合成数据训练最小 Transformer 分类器并报告测试集准确率。
#
# 运行（需先安装 torch）：
#   pip install ".[dl]"          # 或 pip install torch
#   python examples/train_transformer_demo.py

import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import numpy as np
import torch
import torch.nn as nn

from ml.data import build_dataset
from ml.transformer import build_transformer_classifier

AA = "ACDEFGHIKLMNPQRSTVWY"


def seq_to_indices(seq: str):
    """序列 → 氨基酸索引（0 保留给 padding）。"""
    return [AA.index(a) + 1 for a in seq]


def main() -> None:
    print("== 1/3 构造数据集（规则弱标签）==")
    df = build_dataset(n=600, seed=42)
    y = df["high_risk"].astype(int).to_numpy()
    seqs = [seq_to_indices(s) for s in df["sequence"]]
    max_len = max(len(s) for s in seqs)
    X = np.zeros((len(seqs), max_len), dtype=np.int64)
    for i, s in enumerate(seqs):
        X[i, : len(s)] = s
    print(f"样本 {len(df)}，最长序列 {max_len} aa，高风险占比 {y.mean():.2f}")

    print("\n== 2/3 构建并训练最小 Transformer ==")
    model = build_transformer_classifier(
        vocab_size=len(AA) + 1, d_model=64, nhead=4, num_layers=2,
        max_len=max_len, num_classes=2,
    )
    print(f"模型参数: {sum(p.numel() for p in model.parameters()):,}")

    from sklearn.model_selection import train_test_split

    Xtr, Xte, ytr, yte = train_test_split(X, y, test_size=0.2, random_state=42, stratify=y)
    opt = torch.optim.Adam(model.parameters(), lr=1e-3)
    loss_fn = nn.CrossEntropyLoss()

    model.train()
    for epoch in range(5):
        opt.zero_grad()
        logits = model(torch.tensor(Xtr))
        loss = loss_fn(logits, torch.tensor(ytr))
        loss.backward()
        opt.step()
        print(f"epoch {epoch + 1}/5  loss={loss.item():.4f}")

    print("\n== 3/3 测试集评估 ==")
    model.eval()
    with torch.no_grad():
        logits = model(torch.tensor(Xte))
        preds = logits.argmax(1).numpy()
    acc = float((preds == yte).mean())
    print(f"Transformer 测试集准确率: {acc:.4f}")
    print("说明: 标签来自规则引擎(weak label), 结果用于验证 Transformer 可训练收敛, 非实验结论。")


if __name__ == "__main__":
    main()
