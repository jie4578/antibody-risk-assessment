# ml/train.py
# 训练 / 评估管线：分类(高风险与否) + 回归(风险分数)。
#
# 产出：
#   - 训练/测试切分 + (可选) K 折交叉验证
#   - 分类指标：accuracy / precision / recall / f1 / roc_auc
#   - 回归指标：R2 / MAE / RMSE
#   - 特征重要性（树模型用 feature_importances_，线性用 |系数| ）
#   - 训练好的模型与编码器配置（可落盘复用）

from __future__ import annotations

import os
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional

import numpy as np
import pandas as pd

from sklearn.metrics import (
    accuracy_score,
    f1_score,
    mean_absolute_error,
    mean_squared_error,
    precision_score,
    r2_score,
    recall_score,
    roc_auc_score,
)
from sklearn.model_selection import StratifiedKFold, train_test_split

from . import models as model_module
from .features import SequenceEncoder

try:
    import joblib

    _HAS_JOBLIB = True
except Exception:  # pragma: no cover
    joblib = None
    _HAS_JOBLIB = False

# 与 data.py 标签列一致
TARGET_CLASS = "high_risk"
TARGET_REGRESSION = "risk_score"


@dataclass
class TrainResult:
    """一次训练的汇总结果。"""
    task: str
    model_name: str
    model: Any = None
    metrics: Dict[str, float] = field(default_factory=dict)
    feature_importance: List[tuple] = field(default_factory=list)
    n_train: int = 0
    n_test: int = 0
    report: str = ""

    def to_dict(self) -> Dict[str, Any]:
        return {
            "task": self.task,
            "model_name": self.model_name,
            "metrics": dict(self.metrics),
            "feature_importance_top": self.feature_importance[:10],
            "n_train": self.n_train,
            "n_test": self.n_test,
        }


def _class_target(df: pd.DataFrame) -> np.ndarray:
    return df[TARGET_CLASS].astype(int).to_numpy()


def _regression_target(df: pd.DataFrame) -> np.ndarray:
    return df[TARGET_REGRESSION].astype(float).to_numpy()


def split_dataset(df: pd.DataFrame, task: str, *, test_size: float = 0.2, seed: int = 42):
    """按任务切分数据集。分类用分层切分，回归用普通切分。"""
    y = _class_target(df) if task == "classification" else _regression_target(df)
    stratify = y if task == "classification" else None
    idx_train, idx_test = train_test_split(
        np.arange(len(df)),
        test_size=test_size,
        random_state=seed,
        stratify=stratify,
    )
    return df.iloc[idx_train].reset_index(drop=True), df.iloc[idx_test].reset_index(drop=True)


def evaluate_classification(model, X_test: np.ndarray, y_test: np.ndarray) -> Dict[str, float]:
    preds = model.predict(X_test)
    proba = model.predict_proba(X_test)[:, 1] if hasattr(model, "predict_proba") else None
    metrics = {
        "accuracy": accuracy_score(y_test, preds),
        "precision": precision_score(y_test, preds, zero_division=0),
        "recall": recall_score(y_test, preds, zero_division=0),
        "f1": f1_score(y_test, preds, zero_division=0),
    }
    if proba is not None:
        try:
            metrics["roc_auc"] = roc_auc_score(y_test, proba)
        except ValueError:
            metrics["roc_auc"] = float("nan")
    return metrics


def evaluate_regression(model, X_test: np.ndarray, y_test: np.ndarray) -> Dict[str, float]:
    preds = model.predict(X_test)
    return {
        "r2": r2_score(y_test, preds),
        "mae": mean_absolute_error(y_test, preds),
        "rmse": float(np.sqrt(mean_squared_error(y_test, preds))),
    }


def feature_importance(model, feature_names: List[str]) -> List[tuple]:
    """返回按重要性降序的 [(feature_name, score), ...]。"""
    name = model.__class__.__name__.lower()
    if hasattr(model, "feature_importances_"):
        scores = np.asarray(model.feature_importances_, dtype=float)
    elif hasattr(model, "coef_"):
        coef = np.asarray(model.coef_)
        scores = np.abs(coef).ravel() if coef.ndim > 1 else np.abs(coef)
        scores = np.asarray(scores, dtype=float)
    else:
        return []
    pairs = list(zip(feature_names, scores.tolist()))
    pairs.sort(key=lambda t: t[1], reverse=True)
    return pairs


def _cross_val(model, X, y, task: str, cv_folds: int, seed: int) -> Dict[str, float]:
    """K 折交叉验证的平均指标。"""
    from sklearn.base import clone

    skf = StratifiedKFold(n_splits=cv_folds, shuffle=True, random_state=seed)
    scores: Dict[str, List[float]] = {}
    for tr_idx, va_idx in skf.split(X, y):
        m = clone(model)
        m.fit(X[tr_idx], y[tr_idx])
        if task == "classification":
            res = evaluate_classification(m, X[va_idx], y[va_idx])
        else:
            res = evaluate_regression(m, X[va_idx], y[va_idx])
        for k, v in res.items():
            scores.setdefault(k, []).append(v)
    return {k: float(np.mean(v)) for k, v in scores.items()}


def train_pipeline(
    df: pd.DataFrame,
    encoder: Optional[SequenceEncoder] = None,
    *,
    task: str = "classification",
    model_name: str = "logistic",
    test_size: float = 0.2,
    seed: int = 42,
    use_cv: bool = False,
    cv_folds: int = 5,
    save_path: Optional[str] = None,
) -> TrainResult:
    """
    训练管线主入口。

    df 需包含列：sequence、risk_score、risk_level、high_risk（由 ml.data.build_dataset 生成）。
    task ∈ {classification, regression}。
    save_path 非空时把 (模型 + 编码器配置) 落盘为 joblib/pickle。
    """
    if encoder is None:
        encoder = SequenceEncoder()
    if task not in ("classification", "regression"):
        raise ValueError("task 只能是 classification 或 regression")

    df_train, df_test = split_dataset(df, task, test_size=test_size, seed=seed)

    X_train = encoder.transform(df_train["sequence"].tolist())
    X_test = encoder.transform(df_test["sequence"].tolist())
    y_train = _class_target(df_train) if task == "classification" else _regression_target(df_train)
    y_test = _class_target(df_test) if task == "classification" else _regression_target(df_test)

    model = model_module.make_model(model_name, task)
    model.fit(X_train, y_train)

    if task == "classification":
        metrics = evaluate_classification(model, X_test, y_test)
    else:
        metrics = evaluate_regression(model, X_test, y_test)

    # 交叉验证（可选）
    if use_cv:
        cv_metrics = _cross_val(model, np.vstack([X_train, X_test]), np.concatenate([y_train, y_test]), task, cv_folds, seed)
        metrics = {f"{k} (cv)": round(v, 4) for k, v in cv_metrics.items()} | metrics

    fi = feature_importance(model, encoder.feature_names())

    result = TrainResult(
        task=task,
        model_name=model_name,
        model=model,
        metrics={k: round(float(v), 4) for k, v in metrics.items()},
        feature_importance=fi[:10],
        n_train=int(len(df_train)),
        n_test=int(len(df_test)),
        report="",
    )
    result.report = _format_report(result, encoder)

    if save_path:
        _save_bundle(model, encoder, save_path)

    return result


def _format_report(result: TrainResult, encoder: SequenceEncoder) -> str:
    lines = ["=== 训练报告 ==="]
    lines.append(f"任务: {result.task} | 模型: {result.model_name} | 特征维度: {encoder.n_features}")
    lines.append(f"训练样本: {result.n_train} | 测试样本: {result.n_test}")
    for k, v in result.metrics.items():
        lines.append(f"  {k}: {v}")
    lines.append("特征重要性 Top:")
    for name, score in result.feature_importance:
        lines.append(f"  {name}: {score:.4f}")
    return "\n".join(lines)


def _save_bundle(model, encoder: SequenceEncoder, path: str) -> None:
    os.makedirs(os.path.dirname(os.path.abspath(path)), exist_ok=True)
    data = {
        "model": model,
        "encoder_config": {
            "k_max": encoder.k_max,
            "kmer_dim": encoder.kmer_dim,
            "aa_props": encoder.aa_props,
            "n_features": encoder.n_features,
        },
    }
    if _HAS_JOBLIB:
        joblib.dump(data, path)
    else:
        import pickle

        with open(path, "wb") as f:
            pickle.dump(data, f)


def load_bundle(path: str):
    """加载 save_bundle 保存的 (模型, 编码器配置)。返回 (model, encoder)。"""
    if _HAS_JOBLIB:
        data = joblib.load(path)
    else:
        import pickle

        with open(path, "rb") as f:
            data = pickle.load(f)
    cfg = data["encoder_config"]
    encoder = SequenceEncoder(k_max=cfg["k_max"], kmer_dim=cfg["kmer_dim"], aa_props=cfg["aa_props"])
    return data["model"], encoder
