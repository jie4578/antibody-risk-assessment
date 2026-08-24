# ml/evaluate.py
# 推理 + 可视化：混淆矩阵、ROC 曲线、特征重要性图。
# matplotlib 为可选依赖；未安装时函数会给出清晰提示，不影响训练/评估。

from __future__ import annotations

import os
from typing import List, Optional, Sequence, Tuple

import numpy as np


def _import_pyplot():
    try:
        import matplotlib

        matplotlib.use("Agg")
        import matplotlib.pyplot as plt

        return plt
    except Exception:  # pragma: no cover
        raise ImportError(
            "可视化需要 matplotlib。请安装: pip install matplotlib"
        )


def confusion_matrix_plot(
    y_true: Sequence[int],
    y_pred: Sequence[int],
    labels: Optional[List[str]] = None,
    save_path: str = "confusion_matrix.png",
) -> str:
    """保存混淆矩阵图，返回保存路径。"""
    from sklearn.metrics import confusion_matrix, ConfusionMatrixDisplay

    plt = _import_pyplot()
    y_true = np.asarray(y_true, dtype=int)
    y_pred = np.asarray(y_pred, dtype=int)
    cm = confusion_matrix(y_true, y_pred, labels=sorted(set(np.unique(y_true))))
    if labels is None:
        labels = [str(i) for i in sorted(set(np.unique(y_true)))]
    disp = ConfusionMatrixDisplay(confusion_matrix=cm, display_labels=labels)
    fig, ax = plt.subplots(figsize=(5, 5))
    disp.plot(ax=ax, cmap="Blues", colorbar=False)
    ax.set_title("Confusion Matrix")
    os.makedirs(os.path.dirname(os.path.abspath(save_path)), exist_ok=True)
    fig.tight_layout()
    fig.savefig(save_path, dpi=120)
    plt.close(fig)
    return save_path


def roc_curve_plot(y_true: Sequence[int], proba: Sequence[float], save_path: str = "roc_curve.png") -> str:
    """保存 ROC 曲线（含 AUC），返回保存路径。"""
    from sklearn.metrics import roc_curve, auc

    plt = _import_pyplot()
    y_true = np.asarray(y_true, dtype=int)
    proba = np.asarray(proba, dtype=float)
    fpr, tpr, _ = roc_curve(y_true, proba)
    roc_auc = auc(fpr, tpr)
    fig, ax = plt.subplots(figsize=(5, 5))
    ax.plot(fpr, tpr, color="darkorange", lw=2, label=f"ROC (AUC = {roc_auc:.3f})")
    ax.plot([0, 1], [0, 1], color="navy", lw=1, linestyle="--")
    ax.set_xlim([0.0, 1.0])
    ax.set_ylim([0.0, 1.05])
    ax.set_xlabel("False Positive Rate")
    ax.set_ylabel("True Positive Rate")
    ax.set_title("ROC Curve")
    ax.legend(loc="lower right")
    os.makedirs(os.path.dirname(os.path.abspath(save_path)), exist_ok=True)
    fig.tight_layout()
    fig.savefig(save_path, dpi=120)
    plt.close(fig)
    return save_path


def feature_importance_plot(
    pairs: Sequence[Tuple[str, float]],
    top_n: int = 15,
    save_path: str = "feature_importance.png",
) -> str:
    """保存特征重要性条形图，返回保存路径。"""
    plt = _import_pyplot()
    pairs = list(pairs)[:top_n]
    if not pairs:
        raise ValueError("无特征重要性可绘制")
    names = [p[0] for p in pairs][::-1]
    scores = [float(p[1]) for p in pairs][::-1]
    fig, ax = plt.subplots(figsize=(7, max(3, 0.3 * len(names))))
    ax.barh(names, scores, color="steelblue")
    ax.set_xlabel("Importance")
    ax.set_title("Feature Importance (top)")
    os.makedirs(os.path.dirname(os.path.abspath(save_path)), exist_ok=True)
    fig.tight_layout()
    fig.savefig(save_path, dpi=120)
    plt.close(fig)
    return save_path
