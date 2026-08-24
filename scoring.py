# scoring.py
# Rule-based Computational Risk Score：纯 Python 确定性打分。
# 无外部 API、无随机性、无机器学习、无 LLM。
# 仅供候选序列相对优先级排序；未经实验验证（详见 README）。

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Dict, List, Optional, Tuple

from models import AnalysisResult, RiskItem

# ---------- 常量（集中定义，禁止散落在函数中） ----------

# 基序基准罚分（依据现有 RISK_MOTIFS 描述中的严重度梯度校准）
BASE_PENALTIES: Dict[str, float] = {
    "NG": 6.0, "NS": 5.0, "NN": 4.0,   # 脱酰胺化
    "DG": 6.0, "DS": 5.0, "DA": 3.0,   # 异构化
    "M": 4.0,                          # 氧化
    "N-糖基化": 9.0,                   # PTM（按 category 匹配）
}

# CDR 区域权重：heuristic weighting，未经实验验证
CDR_WEIGHT: float = 1.3
FRAMEWORK_WEIGHT: float = 1.0

REGION_WEIGHTS: Dict[str, float] = {
    "CDR1": CDR_WEIGHT,
    "CDR2": CDR_WEIGHT,
    "CDR3": CDR_WEIGHT,
    "FW": FRAMEWORK_WEIGHT,
    "Framework": FRAMEWORK_WEIGHT,
}

CDR_REGIONS = ("CDR1", "CDR2", "CDR3")

# 同一基序第 2 次及以后：基准罚分 × 递减系数（第 1 次 = 100%，后续 = 50%）
DIMINISHING_FACTOR: float = 0.5

PTM_CATEGORY = "N-糖基化"

CATEGORY_BUCKETS = ("PTM", "Chemical Liability")
REGION_BUCKETS = ("CDR", "Framework")


@dataclass
class RiskScore:
    """Rule-based 评分的统一结果。category_breakdown 与 region_breakdown 是两个正交视角，不能相加。"""
    overall_score: float = float("nan")
    risk_level: str = "N/A"
    total_penalty: float = 0.0
    category_breakdown: Dict[str, float] = field(
        default_factory=lambda: {"PTM": 0.0, "Chemical Liability": 0.0}
    )
    region_breakdown: Dict[str, float] = field(
        default_factory=lambda: {"CDR": 0.0, "Framework": 0.0}
    )
    contributing_factors: List[str] = field(default_factory=list)

    def to_dict(self) -> Dict[str, object]:
        """用于 batch / UI 的扁平化输出。"""
        return {
            "overall_score": self.overall_score,
            "risk_level": self.risk_level,
            "total_penalty": self.total_penalty,
            "category_breakdown": dict(self.category_breakdown),
            "region_breakdown": dict(self.region_breakdown),
            "contributing_factors": list(self.contributing_factors),
        }


def _base_penalty(risk_item) -> float:
    """取基准罚分：N-糖基化按 category 匹配，其余按 motif 匹配；未知 → 0。"""
    if risk_item.category == PTM_CATEGORY:
        return BASE_PENALTIES.get(PTM_CATEGORY, 0.0)
    return BASE_PENALTIES.get(risk_item.motif, 0.0)


def _position_start(position) -> int:
    """把 position（int 或 "1-2"）转成起始位置 int，用于确定性排序。"""
    try:
        return int(str(position).split("-")[0])
    except (TypeError, ValueError):
        return 0


def _risk_level(score: float) -> str:
    if 80 <= score <= 100:
        return "Low Risk"
    if 60 <= score < 80:
        return "Medium Risk"
    return "High Risk"


def _invalid_score(invalid_chain_names: List[str]) -> RiskScore:
    nan = float("nan")
    return RiskScore(
        overall_score=nan,
        risk_level="N/A",
        total_penalty=nan,
        category_breakdown={"PTM": nan, "Chemical Liability": nan},
        region_breakdown={"CDR": nan, "Framework": nan},
        contributing_factors=[f"{name} sequence invalid" for name in invalid_chain_names],
    )


def compute_risk_score(
    chain_results: List[Tuple[str, Optional[AnalysisResult]]],
) -> RiskScore:
    """
    计算 Rule-based Risk Score。

    参数:
        chain_results: [(chain_name, AnalysisResult | None)]，顺序即评分顺序：
            VH 在前、VL 在后；链内按 position 升序。
            结果为 None 或 errors 非空 → 该链视为无效。

    返回:
        RiskScore。双链均无效时 overall_score=NaN、risk_level="N/A"。
    """
    valid_chains: List[Tuple[str, "AnalysisResult"]] = []
    invalid_names: List[str] = []
    for name, result in chain_results:
        if result is None or result.errors:
            invalid_names.append(name)
        else:
            valid_chains.append((name, result))

    if not valid_chains:
        return _invalid_score(invalid_names)

    # 收集风险条目并防御性去重：(chain, category, motif, position, region) 完全相同只算一次。
    # 注意：VH/VL 各自是独立序列，相同 position 数字不代表同一事件，因此键必须含 chain。
    items: List[Tuple[str, object]] = []
    seen = set()
    for name, result in valid_chains:
        for r in result.risks:
            key = (name, r.category, r.motif, r.position, r.region)
            if key in seen:
                continue
            seen.add(key)
            items.append((name, r))

    # 确定性顺序：链顺序按传入顺序（VH 在前），链内 position 升序
    chain_index = {name: i for i, (name, _) in enumerate(chain_results)}
    items.sort(key=lambda t: (chain_index[t[0]], _position_start(t[1].position)))

    motif_count: Dict[Tuple[str, str], int] = {}
    total = 0.0
    category_breakdown = {"PTM": 0.0, "Chemical Liability": 0.0}
    region_breakdown = {"CDR": 0.0, "Framework": 0.0}
    factors = [f"{name} sequence invalid" for name in invalid_names]

    for name, r in items:
        base = _base_penalty(r)
        if base <= 0:
            factors.append(f"{name} {r.motif}@{r.position} {r.category} ({r.region}) [unknown category, penalty 0]")
            continue

        # 同一 (category, motif) 分组：第 1 次全额，后续 ×0.5
        key = (r.category, r.motif)
        count = motif_count.get(key, 0)
        effective_base = base if count == 0 else base * DIMINISHING_FACTOR
        motif_count[key] = count + 1

        weight = REGION_WEIGHTS.get(r.region, FRAMEWORK_WEIGHT)
        penalty = effective_base * weight
        total += penalty

        if r.category == PTM_CATEGORY:
            category_breakdown["PTM"] += penalty
        else:
            category_breakdown["Chemical Liability"] += penalty

        if r.region in CDR_REGIONS:
            region_breakdown["CDR"] += penalty
        else:
            region_breakdown["Framework"] += penalty

        factors.append(f"{name} {r.motif}@{r.position} {r.category} ({r.region})")

    overall = max(0.0, 100.0 - total)
    overall = min(100.0, overall)
    overall = round(overall, 2)  # 消除浮点噪声

    return RiskScore(
        overall_score=overall,
        risk_level=_risk_level(overall),
        total_penalty=total,
        category_breakdown=category_breakdown,
        region_breakdown=region_breakdown,
        contributing_factors=factors,
    )
