# literature/eval_benchmark.py
# 评估体系：衡量"检索与回答"好不好（面试必问"你如何验证系统好坏"）。
#
# 1) retrieval_metrics(ranked, relevant, k)：hit@k / MRR@k
# 2) OFFLINE_BENCHMARK：固定小语料 + 已知相关 PMID 的查询集（确定性、离线、可测试）
# 3) run_offline_benchmark()：在固定语料上跑 rerank，输出每查询指标与均值
# 4) run_live_benchmark()：真实检索若干查询，统计 hit@5（live，结果随文献库漂移，如实报告）
# 5) citation_pass_rate()：用 answer_question 跑 N 个问题，统计引用校验通过率（live，需 key）

from __future__ import annotations

from typing import Dict, List, Sequence, Set, Tuple

from .evidence import Evidence
from .reranker import rerank


# ---------------------------------------------------------------- 指标
def hit_at_k(ranked_ids: Sequence[str], relevant: Set[str], k: int) -> float:
    """Top-K 中是否至少命中一个相关文献。"""
    return 1.0 if any(rid in relevant for rid in list(ranked_ids)[:k]) else 0.0


def mrr_at_k(ranked_ids: Sequence[str], relevant: Set[str], k: int) -> float:
    """首个相关文献的倒数排名（未命中为 0）。"""
    for i, rid in enumerate(list(ranked_ids)[:k]):
        if rid in relevant:
            return 1.0 / (i + 1)
    return 0.0


def retrieval_metrics(ranked: Sequence[Evidence], relevant_pmids: Set[str], k: int = 5) -> Dict[str, float]:
    ids = [e.citation_key() for e in ranked]
    return {"hit@k": hit_at_k(ids, relevant_pmids, k), "mrr@k": mrr_at_k(ids, relevant_pmids, k)}


# ---------------------------------------------------------------- 离线基准（确定性）
def _ev(pmid: str, title: str, abstract: str = "") -> Evidence:
    return Evidence(
        evidence_id=f"e:{pmid}", title=title, pmid=pmid, abstract=abstract,
        source="europepmc",
    )


# 固定小语料：8 条，覆盖 4 个主题（脱酰胺/糖基化/氧化/聚集）+ 无关项
OFFLINE_CORPUS: List[Evidence] = [
    _ev("100001", "Antibody deamidation review", "Asparagine deamidation of therapeutic antibodies"),
    _ev("100002", "Asn deamidation in monoclonal antibodies", "Deamidation affects antibody stability"),
    _ev("100003", "Glycosylation of therapeutic antibodies", "N-linked glycosylation impacts antibody function"),
    _ev("100004", "Oxidation of methionine residues in antibodies", "Methionine oxidation in antibody formulations"),
    _ev("100005", "Antibody aggregation during storage", "Aggregation of monoclonal antibodies over time"),
    _ev("100006", "Immunogenicity of biotherapeutics", "ADA against therapeutic proteins"),
    _ev("100007", "Pharmacokinetics of antibodies", "PK of monoclonal antibodies in vivo"),
    _ev("100008", "Antibody deamidation prediction by deep learning", "Predicting deamidation sites with protein language models"),
]

# 查询 → 相关 PMID 集合（人工标注）
OFFLINE_BENCHMARK: List[Tuple[str, Set[str]]] = [
    ("antibody deamidation", {"100001", "100002"}),
    ("antibody glycosylation", {"100003"}),
    ("methionine oxidation antibody", {"100004"}),
    ("antibody aggregation", {"100005"}),
]


def run_offline_benchmark(k: int = 5) -> Dict[str, object]:
    """在固定语料上跑 rerank，返回每查询指标 + 均值（确定性、离线）。"""
    per_query = []
    for query, relevant in OFFLINE_BENCHMARK:
        ranked = rerank(query, OFFLINE_CORPUS, top_k=k)
        m = retrieval_metrics(ranked, relevant, k)
        per_query.append({"query": query, **m})
    avg_hit = sum(q["hit@k"] for q in per_query) / len(per_query)
    avg_mrr = sum(q["mrr@k"] for q in per_query) / len(per_query)
    return {"k": k, "n_queries": len(per_query), "per_query": per_query,
            "avg_hit@k": round(avg_hit, 4), "avg_mrr@k": round(avg_mrr, 4)}


# ---------------------------------------------------------------- 在线基准（live）
LIVE_BENCHMARK: List[Tuple[str, Set[str]]] = [
    ("antibody deamidation", {"36018377", "41996200"}),
    ("asparagine deamidation antibody", {"39311379", "38546837"}),
    ("monoclonal antibody glycosylation", {"39192481"}),
]


def run_live_benchmark(k: int = 5, source: str = "auto") -> Dict[str, object]:
    """真实检索若干查询，统计 hit@5/MRR@5。结果随文献库漂移，如实报告（live）。"""
    from .search import search_literature

    per_query = []
    for query, relevant in LIVE_BENCHMARK:
        evidence = search_literature(query, max_results=k, source=source, use_cache=False)
        ranked = rerank(query, evidence, top_k=k)
        m = retrieval_metrics(ranked, relevant, k)
        per_query.append({"query": query, "n_results": len(ranked), **m})
    n = len(per_query)
    return {
        "k": k, "n_queries": n, "per_query": per_query,
        "avg_hit@k": round(sum(q["hit@k"] for q in per_query) / n, 4) if n else 0.0,
        "avg_mrr@k": round(sum(q["mrr@k"] for q in per_query) / n, 4) if n else 0.0,
    }


# ---------------------------------------------------------------- 引用通过率（live）
def citation_pass_rate(questions: List[str], *, backend: str = "auto") -> Dict[str, object]:
    """跑 answer_question，统计引用校验通过率与状态分布（live，需要 API key）。"""
    from .pipeline import answer_question

    rows = []
    for q in questions:
        res = answer_question(q, backend=backend)
        rows.append({
            "question": q[:40], "status": res.status,
            "citation_valid": bool(res.validation.get("valid")),
        })
    n = len(rows)
    valid = sum(1 for r in rows if r["citation_valid"])
    return {
        "n": n, "citation_pass_rate": round(valid / n, 4) if n else 0.0,
        "rows": rows,
    }


def _print_offline() -> None:
    import json

    print(json.dumps(run_offline_benchmark(), ensure_ascii=False, indent=2))


def _print_live() -> None:
    import json

    print("== 在线检索基准(live) ==")
    print(json.dumps(run_live_benchmark(), ensure_ascii=False, indent=2))
    print("\n== 引用通过率(live, 需 key) ==")
    questions = ["什么是抗体脱酰胺化？", "什么是抗体糖基化？"]
    print(json.dumps(citation_pass_rate(questions), ensure_ascii=False, indent=2))


if __name__ == "__main__":
    import sys

    if "--live" in sys.argv:
        _print_live()
    else:
        _print_offline()
