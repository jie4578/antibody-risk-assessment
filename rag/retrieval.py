# rag/retrieval.py
# 检索策略：向量检索 / BM25 关键词检索 / 混合检索（RRF 融合）。
#
#   - 'vector':  用 Embedder 把 query 向量化后在 VectorStore 里做余弦检索；
#   - 'keyword': 轻量 BM25（无需额外依赖）；
#   - 'hybrid':   Reciprocal Rank Fusion 融合向量与关键词两路排序，兼顾语义与精确词。

from __future__ import annotations

import math
import re
from typing import List

import numpy as np

from .store import VectorStore

_TOKEN_RE = re.compile(r"[A-Za-z0-9]+")
_CJK_RE = re.compile(r"[\u4e00-\u9fff]")


def _tokenize(text: str) -> List[str]:
    """分词：英文按单词，中文按单个字符，便于 BM25 在无分词器时也能匹配。"""
    text = (text or "").lower()
    toks = _TOKEN_RE.findall(text)
    toks += _CJK_RE.findall(text)
    return toks


def _bm25_scores(query: str, texts: List[str], k1: float = 1.5, b: float = 0.75) -> np.ndarray:
    """对每个文档计算 BM25 得分（对给定 query）。"""
    n = len(texts)
    if n == 0:
        return np.array([], dtype=np.float32)
    doc_tokens = [_tokenize(t) for t in texts]
    doc_lens = [len(t) for t in doc_tokens]
    avgdl = sum(doc_lens) / n if n else 0.0
    df: dict = {}
    for toks in doc_tokens:
        for t in set(toks):
            df[t] = df.get(t, 0) + 1
    scores = np.zeros(n, dtype=np.float32)
    q_terms = set(_tokenize(query))
    for i, toks in enumerate(doc_tokens):
        tf: dict = {}
        for t in toks:
            tf[t] = tf.get(t, 0) + 1
        dl = doc_lens[i]
        s = 0.0
        for t in q_terms:
            if t in tf and t in df:
                idf = math.log((n - df[t] + 0.5) / (df[t] + 0.5) + 1.0)
                freq = tf[t]
                denom = freq + k1 * (1.0 - b + b * (dl / avgdl if avgdl else 0.0))
                s += idf * (freq * (k1 + 1.0) / denom if denom else 0.0)
        scores[i] = s
    return scores


def _rrf(rank_lists: List[List[str]], k: int = 60) -> List[str]:
    """Reciprocal Rank Fusion：合并多个排序，返回 doc id 列表（降序）。"""
    fused: dict = {}
    for ranks in rank_lists:
        for rank, doc_id in enumerate(ranks):
            fused[doc_id] = fused.get(doc_id, 0.0) + 1.0 / (k + rank + 1)
    return [doc_id for doc_id, _ in sorted(fused.items(), key=lambda t: t[1], reverse=True)]


def retrieve(
    query: str,
    store: VectorStore,
    embedder=None,
    *,
    top_k: int = 5,
    strategy: str = "vector",
    fusion_k: int = 60,
) -> List[dict]:
    """从 store 中检索与 query 相关的文档块。

    返回 [{id, text, metadata, score}]，按相关度降序。
    """
    if store is None or len(store) == 0:
        return []

    texts = store._texts

    if strategy == "vector":
        if embedder is None:
            raise ValueError("vector 检索需要提供 embedder")
        return store.search(embedder.embed_query(query), top_k)

    if strategy == "keyword":
        scores = _bm25_scores(query, texts)
        order = np.argsort(-scores)[:top_k]
        return [_hit(store, idx, float(scores[idx])) for idx in order]

    if strategy == "hybrid":
        if embedder is None:
            raise ValueError("hybrid 检索需要提供 embedder")
        vec_hits = store.search(embedder.embed_query(query), top_k=top_k * 2)
        vec_rank = [h["id"] for h in vec_hits]
        kw_scores = _bm25_scores(query, texts)
        kw_order = np.argsort(-kw_scores)[:top_k * 2]
        kw_rank = [store._ids[int(i)] for i in kw_order]
        fused = _rrf([vec_rank, kw_rank], k=fusion_k)[:top_k]
        by_id = {h["id"]: h for h in vec_hits}
        # 补充关键词命中但向量未命中的文档
        for i in kw_order[: top_k * 2]:
            doc_id = store._ids[int(i)]
            if doc_id not in by_id:
                by_id[doc_id] = {"id": doc_id, "text": store._texts[int(i)], "metadata": dict(store._metadata[int(i)]), "score": float(kw_scores[int(i)])}
        return [by_id[doc_id] for doc_id in fused if doc_id in by_id]

    raise ValueError(f"未知检索策略: {strategy}（可选 vector / keyword / hybrid）")


def _hit(store: VectorStore, idx: int, score: float) -> dict:
    return {
        "id": store._ids[idx],
        "text": store._texts[idx],
        "metadata": dict(store._metadata[idx]),
        "score": score,
    }
