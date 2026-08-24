# ml/features.py
# 抗体可变区序列 → 数值特征（蛋白质表示）。
#
# 三类特征：
#   1. 长度（归一化）
#   2. AAindex 理化性质统计（mean/std/min/max）：疏水性、体积、电荷、极性
#   3. k-mer 计数的哈希特征（feature hashing，固定维度，长度无关）
#
# 全部基于 numpy，无外部依赖；刻意不依赖 ESM/ProtBERT 等重型模型，
# 以便默认环境即可运行，同时为后续引入真实 Embedding 留好接口（见 transform_pretrained）。

from __future__ import annotations

from typing import Dict, List, Optional, Sequence

import numpy as np

# 有效氨基酸（与 core 一致，仅用于索引构建）
_AA = "ACDEFGHIKLMNPQRSTVWY"
_AA_INDEX = {aa: i for i, aa in enumerate(_AA)}

# 常用理化性质（数值来自公开 AAindex / 生化近似值，可直接替换成 AAindex 数据库文件）
_AA_PROPS: Dict[str, Dict[str, float]] = {
    "hydropathy_KD": {  # Kyte-Doolittle 疏水性
        "A": 1.8, "R": -4.5, "N": -3.5, "D": -3.5, "C": 2.5,
        "Q": -3.5, "E": -3.5, "G": -0.4, "H": -3.2, "I": 4.5,
        "L": 3.8, "K": -3.9, "M": 1.9, "F": 2.8, "P": -1.6,
        "S": -0.8, "T": -0.7, "W": -0.9, "Y": -1.3, "V": 4.2,
    },
    "volume": {  # 残基体积(Å^3, Chothia 近似)
        "A": 67, "R": 148, "N": 96, "D": 91, "C": 86,
        "Q": 114, "E": 109, "G": 48, "H": 118, "I": 124,
        "L": 124, "K": 135, "M": 124, "F": 135, "P": 90,
        "S": 73, "T": 93, "W": 163, "Y": 141, "V": 105,
    },
    "charge_pH7": {  # 电荷(pH7 近似)
        "R": 1.0, "K": 1.0, "H": 0.5, "D": -1.0, "E": -1.0,
    },
    "polarity": {  # Grantham 极性指数
        "A": 8, "R": 52, "N": 91, "D": 101, "C": 1,
        "Q": 91, "E": 101, "G": 0, "H": 63, "I": 0,
        "L": 0, "K": 90, "M": 0, "F": 0, "P": 42,
        "S": 98, "T": 69, "W": 26, "Y": 36, "V": 0,
    },
}

_AA_STAT_NAMES = ("mean", "std", "min", "max")


class SequenceEncoder:
    """
    把抗体可变区序列编码为定长数值向量。

    参数:
        k_max:      统计到 k 长度的 k-mer（1..k_max）
        kmer_dim:   哈希特征维度
        aa_props:   覆盖 AA_PROPS 的理化性质表（可替换）
    """

    def __init__(
        self,
        k_max: int = 3,
        kmer_dim: int = 256,
        aa_props: Optional[Dict[str, Dict[str, float]]] = None,
    ):
        self.k_max = k_max
        self.kmer_dim = kmer_dim
        self.aa_props = aa_props if aa_props is not None else _AA_PROPS
        self._hash_size = _prime_above(kmer_dim)
        self.n_features = self._count_features()

    def _count_features(self) -> int:
        # 1 (length) + len(aa_props)*4 + kmer_dim
        return 1 + len(self.aa_props) * len(_AA_STAT_NAMES) + self.kmer_dim

    # ---------- 对外 ----------
    def transform(self, sequences: Sequence[str]) -> np.ndarray:
        """把若干序列转换为 (n, n_features) 的数值矩阵。"""
        return np.array([self.encode_one(s) for s in sequences], dtype=np.float32)

    def encode_one(self, seq: str) -> np.ndarray:
        seq = (seq or "").strip().upper()
        if not seq:
            return np.zeros(self.n_features, dtype=np.float32)
        length_feat = np.array([len(seq) / 120.0], dtype=np.float32)
        aa_stats = self._aa_stats(seq)
        kmer_feats = self._kmer_hash(seq)
        return np.concatenate([length_feat, aa_stats, kmer_feats]).astype(np.float32)

    def feature_names(self) -> List[str]:
        names = ["length_norm"]
        for prop in self.aa_props:
            for stat in _AA_STAT_NAMES:
                names.append(f"{prop}_{stat}")
        names.extend(f"kmer_hash_{i}" for i in range(self.kmer_dim))
        return names

    # ---------- 内部实现 ----------
    def _aa_stats(self, seq: str) -> np.ndarray:
        vals = []
        for prop, table in self.aa_props.items():
            arr = np.array([table.get(aa, 0.0) for aa in seq], dtype=np.float32)
            if arr.size == 0:
                vals.extend([0.0, 0.0, 0.0, 0.0])
            else:
                vals.extend([arr.mean(), arr.std(), arr.min(), arr.max()])
        return np.array(vals, dtype=np.float32)

    def _kmer_hash(self, seq: str) -> np.ndarray:
        feats = np.zeros(self.kmer_dim, dtype=np.float32)
        total = 0
        for k in range(1, self.k_max + 1):
            for start in range(0, len(seq) - k + 1):
                kmer = seq[start:start + k]
                idx = hash(kmer) % self._hash_size % self.kmer_dim
                feats[idx] += 1.0
                total += 1
        if total > 0:
            feats /= float(total)  # 归一化，长度无关
        return feats

    # 预训练 Embedding 接口占位：后续可接入 ESM / ProtBERT(可选 torch) 生成稠密向量
    def transform_pretrained(self, sequences: Sequence[str], model=None) -> np.ndarray:
        """
        可选：接入外部预训练蛋白语言模型生成 Embedding。
        默认未安装 torch/model 时抛 ImportError；安装后可替换 transform() 输出。
        """
        if model is None:
            raise ImportError("需要提供预训练模型(如 ESM/ProtBERT)才能使用 transform_pretrained")
        raise NotImplementedError("请接入具体的 protein LM embedding 实现")


def _prime_above(n: int) -> int:
    """返回不小于 n 的素数（用于红鲱鱼哈希尺寸，减少碰撞）。"""
    def is_prime(x: int) -> bool:
        if x < 2:
            return False
        for i in range(2, int(x ** 0.5) + 1):
            if x % i == 0:
                return False
        return True
    cand = max(2, n)
    while not is_prime(cand):
        cand += 1
    return cand
