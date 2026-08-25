# literature/reranker.py
# 确定性相关性排序（第一阶段，不引入 Embedding / Vector DB）：
#   - query token 与 title 匹配（权重高）
#   - query token 与 abstract 匹配（权重低）
#   - 稳定排序：相同输入必须得到相同顺序（按 (-score, citation_key) 排序）
#   - 按 citation_key 去重 + Top-K（默认 5，最大 10）

from __future__ import annotations

import re
from typing import List, Sequence

from .evidence import Evidence

TITLE_WEIGHT = 3.0
ABSTRACT_WEIGHT = 1.0
MAX_TOP_K = 10

_TOKEN_RE = re.compile(r"[A-Za-z0-9]+")
_CJK_RE = re.compile(r"[\u4e00-\u9fff]")


def _tokens(text: str) -> List[str]:
    text = (text or "").lower()
    return _TOKEN_RE.findall(text) + _CJK_RE.findall(text)


def relevance_score(query: str, evidence: Evidence) -> float:
    """确定性打分：query token 在 title 的命中 ×3 + 在 abstract 的命中 ×1。"""
    q_tokens = _tokens(query)
    if not q_tokens:
        return 0.0
    title = _tokens(evidence.title)
    abstract = _tokens(evidence.abstract)
    q_set = set(q_tokens)
    title_hits = sum(1 for t in q_set if t in title)
    abstract_hits = sum(1 for t in q_set if t in abstract)
    return TITLE_WEIGHT * title_hits + ABSTRACT_WEIGHT * abstract_hits


def rerank(query: str, evidence: Sequence[Evidence], top_k: int = 5) -> List[Evidence]:
    """打分、去重、排序、截断 Top-K。返回新列表，不修改入参。"""
    top_k = min(max(int(top_k), 1), MAX_TOP_K)
    seen = set()
    scored: List[tuple] = []
    for ev in evidence:
        key = ev.citation_key()
        if not key or key in seen:
            continue
        seen.add(key)
        scored.append((relevance_score(query, ev), ev))
    # 稳定排序：分数降序；同分按 citation_key 字典序（确定性）
    scored.sort(key=lambda t: (-t[0], t[1].citation_key()))
    return [ev for _, ev in scored[:top_k]]
