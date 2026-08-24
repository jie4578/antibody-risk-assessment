# ml/models.py
# 属性预测模型注册表：分类（风险等级）与回归（风险分数）。
#
# 轻量优先：默认用 scikit-learn；lightgbm 存在时额外提供梯度提升树。
# 统一通过 build_model_registry(name, task) 构造模型，便于切换与对比评估。

from __future__ import annotations

from typing import Callable, Dict

# ---------- scikit-learn 导入（核心依赖） ----------
from sklearn.ensemble import (
    GradientBoostingClassifier,
    GradientBoostingRegressor,
    RandomForestClassifier,
    RandomForestRegressor,
)
from sklearn.linear_model import LogisticRegression, Ridge

# ---------- lightgbm 可选 ----------
try:
    import lightgbm as lgb

    _HAS_LGB = True
except Exception:  # pragma: no cover - 环境未装 lightgbm 时降级
    lgb = None
    _HAS_LGB = False


def _lgb_classifier():
    return lgb.LGBMClassifier(n_estimators=200, learning_rate=0.05, random_state=42, verbose=-1)


def _lgb_regressor():
    return lgb.LGBMRegressor(n_estimators=200, learning_rate=0.05, random_state=42, verbose=-1)


# 分类模型工厂
CLASSIFIERS: Dict[str, Callable] = {
    "logistic": lambda: LogisticRegression(max_iter=2000, random_state=42),
    "random_forest": lambda: RandomForestClassifier(n_estimators=200, random_state=42, n_jobs=-1),
    "gbdt": lambda: GradientBoostingClassifier(random_state=42),
}

# 回归模型工厂
REGRESSORS: Dict[str, Callable] = {
    "ridge": lambda: Ridge(alpha=1.0),
    "random_forest": lambda: RandomForestRegressor(n_estimators=200, random_state=42, n_jobs=-1),
    "gbdt": lambda: GradientBoostingRegressor(random_state=42),
}


def build_model_registry():
    """
    构建设备模型注册表。返回 {"classification": {...}, "regression": {...}}。
    若安装 lightgbm，则在两任务下额外暴露 "lightgbm"。
    """
    classifiers = dict(CLASSIFIERS)
    regressors = dict(REGRESSORS)
    if _HAS_LGB:
        classifiers["lightgbm"] = _lgb_classifier
        regressors["lightgbm"] = _lgb_regressor
    return {"classification": classifiers, "regression": regressors}


def make_model(name: str, task: str = "classification"):
    """按名称与任务实例化一个模型。task ∈ {classification, regression}。"""
    registry = build_model_registry()
    if task not in registry:
        raise ValueError(f"未知任务: {task}（可选 classification / regression）")
    pool = registry[task]
    if name not in pool:
        raise ValueError(f"未知模型 {name}（{task} 可选: {', '.join(sorted(pool))}）")
    return pool[name]()


def available_models(task: str = "classification") -> list:
    """返回某任务下可用的模型名列表。"""
    registry = build_model_registry()
    return sorted(registry.get(task, {}).keys())
