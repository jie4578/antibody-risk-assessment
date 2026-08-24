# rag/embeddings.py
# 文本 Embedding 抽象：默认离线实现，可选接入真实模型。
#
# 默认提供两种：
#   - TfidfEmbedder:  基于 sklearn TfidfVectorizer 的稀疏向量（经典、可解释、离线）
#   - HashingEmbedder: n-gram 特征哈希到固定维度（无需拟合、确定性）
#
# 可选接入真实稠密 Embedding：安装 sentence-transformers 后可用
#   SentenceTransformerEmbedder；接口统一为 embed_documents / embed_query。

from __future__ import annotations

from typing import List, Optional

import numpy as np

from sklearn.feature_extraction.text import TfidfVectorizer


class TfidfEmbedder:
    """基于 TF-IDF 的文本向量化（稀疏检索）。需先 fit 语料。

    默认使用字符 n-gram（analyzer='char_wb'），对中英文皆可检索，
    避免中文被当作单一 token 导致 query 与文档无重叠。
    """

    def __init__(self, analyzer: str = "char_wb", ngram_range: tuple = (3, 5), min_df: int = 1, **vectorizer_kwargs):
        self._vectorizer = TfidfVectorizer(
            analyzer=analyzer, ngram_range=ngram_range, min_df=min_df, **vectorizer_kwargs
        )
        self._fitted = False
        self.dim: Optional[int] = None

    def fit(self, texts: List[str]) -> "TfidfEmbedder":
        self._vectorizer.fit(texts)
        self._fitted = True
        self.dim = len(self._vectorizer.vocabulary_)
        return self

    def embed_documents(self, texts: List[str]) -> np.ndarray:
        if not self._fitted:
            raise RuntimeError("TfidfEmbedder 尚未 fit（请先用文档语料调用 fit）")
        return self._vectorizer.transform(texts).toarray().astype(np.float32)

    def embed_query(self, text: str) -> np.ndarray:
        if not self._fitted:
            raise RuntimeError("TfidfEmbedder 尚未 fit")
        return self._vectorizer.transform([text]).toarray().astype(np.float32)[0]


class HashingEmbedder:
    """n-gram 特征哈希到固定维度，并 L2 归一化。确定性、无需拟合。"""

    def __init__(self, dim: int = 512, ngram_range: tuple = (1, 2), seed: int = 42):
        self.dim = dim
        self.ngram_range = ngram_range
        self._hash_mod = _prime_above(dim)
        self._seed = seed

    def _tokenize(self, text: str) -> List[str]:
        text = (text or "").lower()
        toks = []
        for n in range(self.ngram_range[0], self.ngram_range[1] + 1):
            for i in range(len(text) - n + 1):
                toks.append(text[i:i + n])
        return toks

    def embed_documents(self, texts: List[str]) -> np.ndarray:
        return np.array([self._embed(t) for t in texts], dtype=np.float32)

    def embed_query(self, text: str) -> np.ndarray:
        return self._embed(text)

    def _embed(self, text: str) -> np.ndarray:
        vec = np.zeros(self.dim, dtype=np.float32)
        toks = self._tokenize(text)
        for t in toks:
            h = (hash((t, self._seed)) % self._hash_mod) % self.dim
            vec[h] += 1.0
        norm = np.linalg.norm(vec)
        if norm > 0:
            vec /= norm
        return vec


class _SentenceTransformerEmbedder:
    """可选：接入 sentence-transformers 生成真实稠密向量。"""

    def __init__(self, model_name: str = "all-MiniLM-L6-v2"):
        try:
            from sentence_transformers import SentenceTransformer
        except Exception as e:  # pragma: no cover
            raise ImportError("需要安装 sentence-transformers 才能使用该 Embedder") from e
        self._model = SentenceTransformer(model_name)
        self.dim = self._model.get_sentence_embedding_dimension()

    def embed_documents(self, texts: List[str]) -> np.ndarray:
        return self._model.encode(texts, normalize_embeddings=True)

    def embed_query(self, text: str) -> np.ndarray:
        return self._model.encode([text], normalize_embeddings=True)[0]


def get_embedder(name: str = "tfidf", **kwargs):
    """Embedder 工厂。name ∈ {tfidf, hashing, sentence-transformer}。"""
    if name == "tfidf":
        return TfidfEmbedder(**kwargs)
    if name == "hashing":
        return HashingEmbedder(**kwargs)
    if name in ("sentence-transformer", "sentence_transformers", "st"):
        return _SentenceTransformerEmbedder(**kwargs)
    raise ValueError(f"未知 Embedder: {name}（可选 tfidf / hashing / sentence-transformer）")


def _prime_above(n: int) -> int:
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
