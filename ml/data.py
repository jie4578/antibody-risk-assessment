# ml/data.py
# 可复现的合成抗体序列数据集 + 规则弱标签。
#
# 为什么用合成数据：
#   - 项目当前只有少量真实抗体序列（example_antibodies.csv），不足以训练模型；
#   - 我们用"确定性规则引擎"(core + scoring) 作为弱标签给序列打分，
#     从而离线、可复现地构造一份带标签的数据集，串起"序列→特征→模型"完整 ML 流程。
#   - 标签来自规则，模型学习的是规则引擎的更平滑/可泛化替身，文档中会如实说明。

from __future__ import annotations

import os
import random
from typing import List, Optional, Tuple

import pandas as pd

# 复用既有规则引擎作为"弱标签"来源，不复制打分逻辑
from core import analyze_sequence
from scoring import compute_risk_score

# 本项目默认 CDR 边界（Kabat 手动边界，与 app.py / batch_analysis.py 默认一致）
DEFAULT_CDR = (31, 35, 50, 65, 99, 110)

# 用于向序列中注入已知风险基序，制造"高风险"样本（使标签分布非退化）
_RISKY_EDITORS: List[Tuple[str, int]] = [
    ("NG", 2), ("NS", 2), ("NN", 2),     # 脱酰胺化
    ("DG", 2), ("DS", 2), ("DA", 2),     # 异构化
    ("M", 1),                            # 氧化
    ("NST", 3), ("NGS", 3),              # N-糖基化
]

# 有效氨基酸（与 core.VALID_AMINO_ACIDS 一致，禁止复制，这里仅用于随机突变生成）
_AA = "ACDEFGHIKLMNPQRSTVWY"

# 示例数据路径（相对项目根目录）
_EXAMPLE_CSV = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "example_antibodies.csv")


class BaseSequencePool:
    """从 example_antibodies.csv 加载真实的抗体可变区序列作为"母本"。"""

    def __init__(self, csv_path: str = _EXAMPLE_CSV):
        self._csv_path = csv_path
        self._sequences: List[str] = []
        self._load()

    def _load(self) -> None:
        df = pd.read_csv(self._csv_path)
        seqs: List[str] = []
        for col in ("VH", "VL"):
            if col in df.columns:
                for v in df[col]:
                    v = str(v).strip().upper()
                    if v and set(v) <= set(_AA):
                        seqs.append(v)
        if not seqs:
            raise ValueError(f"未从 {self._csv_path} 载入任何有效序列")
        self._sequences = seqs

    @property
    def sequences(self) -> List[str]:
        return list(self._sequences)

    def sample(self, rng: random.Random) -> str:
        return rng.choice(self._sequences)


def mutate_sequence_random(seq: str, rng: random.Random, n_mutations: int) -> str:
    """对序列施加 n_mutations 次随机点突变（换成不同的氨基酸），制造序列多样性。"""
    if n_mutations <= 0:
        return seq
    chars = list(seq.upper())
    n = len(chars)
    positions = rng.sample(range(n), min(n_mutations, n))
    for pos in positions:
        others = [a for a in _AA if a != chars[pos]]
        chars[pos] = rng.choice(others)
    return "".join(chars)


def inject_risk_motifs(seq: str, rng: random.Random, n_sites: int) -> str:
    """注入 n_sites 个已知风险基序，制造高风险样本。"""
    chars = list(seq.upper())
    n = len(chars)
    for _ in range(n_sites):
        editor, width = rng.choice(_RISKY_EDITORS)
        if n < width:
            continue
        start = rng.randint(0, n - width)
        chars[start:start + width] = list(editor)
    return "".join(chars)


def make_variant(base: str, rng: random.Random, *, p_inject: float = 0.6) -> str:
    """由母本生成一条变异体：随机点突变 + 视概率注入风险基序。"""
    seq = base
    n_mut = rng.choice([0, 1, 2, 3, 4])
    seq = mutate_sequence_random(seq, rng, n_mut)
    if rng.random() < p_inject:
        n_sites = rng.choice([1, 1, 2, 2, 3])
        seq = inject_risk_motifs(seq, rng, n_sites)
    return seq


def rule_label(seq: str) -> Tuple[float, str]:
    """用规则引擎给单条序列打分，返回 (risk_score, risk_level)。"""
    result = analyze_sequence(seq, *DEFAULT_CDR)
    if result.errors:
        return float("nan"), "invalid"
    score = compute_risk_score([("VH", result)])
    return round(float(score.overall_score), 2), str(score.risk_level)


def build_dataset(
    n: int = 800,
    seed: int = 42,
    pool: Optional[BaseSequencePool] = None,
    *,
    p_inject: float = 0.6,
) -> pd.DataFrame:
    """
    构造带标签的抗体序列数据集。

    返回 DataFrame，列：
        sequence    抗体可变区序列
        risk_score  规则弱标签（连续）
        risk_level  Low / Medium / High Risk
        high_risk   bool，risk_level == "High Risk"
    """
    if n <= 0:
        raise ValueError("n 必须为正整数")
    rng = random.Random(seed)
    if pool is None:
        pool = BaseSequencePool()

    rows = []
    attempts = 0
    while len(rows) < n and attempts < n * 20:
        attempts += 1
        seq = make_variant(pool.sample(rng), rng, p_inject=p_inject)
        score, level = rule_label(seq)
        if level == "invalid" or score != score:  # NaN 检查
            continue
        rows.append({
            "sequence": seq,
            "risk_score": score,
            "risk_level": level,
            "high_risk": level == "High Risk",
        })

    if not rows:
        raise RuntimeError("未能生成任何有效样本，请检查规则引擎或母本序列")

    return pd.DataFrame(rows).reset_index(drop=True)
