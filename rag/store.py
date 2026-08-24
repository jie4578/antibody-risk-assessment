# rag/store.py
# 内存向量存储 + 余弦相似度检索。默认纯 numpy，简单可靠、可离线。
#
# 可选：安装 faiss-cpu 后用 FaissStore 获得大规模高效检索（接口一致）。

from __future__ import annotations

from typing import Dict, List, Optional

import numpy as np


class VectorStore:
    """内存向量库。添加向量后可按余弦相似度检索 top-k。"""

    def __init__(self, dim: Optional[int] = None):
        self.dim = dim
        self._ids: List[str] = []
        self._texts: List[str] = []
        self._metadata: List[dict] = []
        self._matrix: Optional[np.ndarray] = None

    def __len__(self) -> int:
        return len(self._ids)

    def add(
        self,
        ids: List[str],
        texts: List[str],
        vectors: np.ndarray,
        metadata: Optional[List[dict]] = None,
    ) -> None:
        vectors = np.asarray(vectors, dtype=np.float32)
        if vectors.ndim == 1:
            vectors = vectors.reshape(1, -1)
        if vectors.shape[0] != len(ids):
            raise ValueError("ids / vectors 长度不一致")
        if self.dim is None:
            self.dim = vectors.shape[1]
        elif vectors.shape[1] != self.dim:
            raise ValueError(f"向量维度不一致: 期望 {self.dim}，得到 {vectors.shape[1]}")
        if metadata is None:
            metadata = [{} for _ in ids]
        self._ids.extend(ids)
        self._texts.extend(texts)
        self._metadata.extend(metadata)
        old = self._matrix if self._matrix is not None else np.zeros((0, self.dim), dtype=np.float32)
        self._matrix = np.vstack([old, vectors])

    def search(self, query_vec: np.ndarray, top_k: int = 5) -> List[dict]:
        """按余弦相似度返回 top-k。返回 [{id, text, metadata, score}]。"""
        if self._matrix is None or len(self) == 0:
            return []
        q = np.asarray(query_vec, dtype=np.float32).reshape(1, -1)
        sims = cosine_similarity(q, self._matrix)  # (n_docs,)
        order = np.argsort(-sims)[:top_k]
        results = []
        for idx in order:
            idx = int(idx)
            results.append({
                "id": self._ids[idx],
                "text": self._texts[idx],
                "metadata": dict(self._metadata[idx]),
                "score": float(sims[idx]),
            })
        return results

    def id_to_index(self) -> Dict[str, int]:
        return {i: idx for idx, i in enumerate(self._ids)}


def cosine_similarity(a: np.ndarray, b: np.ndarray) -> np.ndarray:
    """计算 a(1,d) 与 b(n,d) 的余弦相似度，返回 (n,)。"""
    a = np.asarray(a, dtype=np.float32)
    b = np.asarray(b, dtype=np.float32)
    na = np.linalg.norm(a)
    nb = np.linalg.norm(b, axis=1, keepdims=True)
    denom = na * nb.ravel()
    denom[denom == 0] = 1e-9
    return (b @ a.ravel()) / denom


class FaissStore(VectorStore):
    """可选：基于 faiss-cpu 的向量库。需安装 faiss-cpu。"""

    def __init__(self, dim: int, index_type: str = "flat"):
        try:
            import faiss
        except Exception as e:  # pragma: no cover
            raise ImportError("需要安装 faiss-cpu 才能使用 FaissStore") from e
        super().__init__(dim)
        self._faiss = faiss
        self._index = faiss.IndexFlatIP(dim) if index_type == "flat" else faiss.IndexFlatL2(dim)
        self._norm = index_type == "flat"

    def add(self, ids, texts, vectors, metadata=None):
        vectors = np.asarray(vectors, dtype=np.float32)
        if vectors.ndim == 1:
            vectors = vectors.reshape(1, -1)
        if self._norm:
            faiss.normalize_L2(vectors)
        self._index.add(vectors)
        super().add(ids, texts, vectors, metadata)

    def search(self, query_vec, top_k=5):
        import numpy as _np
        q = _np.asarray(query_vec, dtype=_np.float32).reshape(1, -1)
        if self._norm:
            self._faiss.normalize_L2(q)
        D, I = self._index.search(q, top_k)
        out = []
        for score, idx in zip(D[0], I[0]):
            if idx < 0:
                continue
            idx = int(idx)
            out.append({
                "id": self._ids[idx],
                "text": self._texts[idx],
                "metadata": dict(self._metadata[idx]),
                "score": float(score),
            })
        return out
