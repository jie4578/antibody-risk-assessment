# tests/test_literature/test_reranker.py
# Reranker：确定性排序 / 标题权重 > 摘要权重 / 去重 / Top-K 上限 / 稳定性。

from literature.evidence import Evidence
from literature.reranker import MAX_TOP_K, relevance_score, rerank


def _ev(pmid, title, abstract="", doi=""):
    return Evidence(evidence_id=f"e:{pmid}", title=title, pmid=pmid, doi=doi, abstract=abstract, source="europepmc")


def test_title_match_beats_abstract_only():
    ev_title = _ev("1", "Antibody deamidation causes instability", abstract="")
    ev_abs = _ev("2", "Something else", abstract="Antibody deamidation discussed here")
    assert relevance_score("antibody deamidation", ev_title) > relevance_score("antibody deamidation", ev_abs)


def test_rerank_sorts_by_score_desc():
    evs = [
        _ev("1", "Unrelated paper", abstract=""),
        _ev("2", "Antibody deamidation review", abstract="Antibody deamidation"),
    ]
    ranked = rerank("antibody deamidation", evs, top_k=5)
    assert ranked[0].pmid == "2"


def test_rerank_stable_same_input():
    evs = [_ev("1", "Antibody", abstract="deamidation"), _ev("2", "Deamidation", abstract="")]
    a = [e.pmid for e in rerank("antibody deamidation", evs)]
    b = [e.pmid for e in rerank("antibody deamidation", evs)]
    assert a == b


def test_rerank_dedup_by_pmid():
    evs = [_ev("1", "Antibody deamidation", abstract="x"), _ev("1", "Antibody deamidation dup", abstract="x")]
    ranked = rerank("antibody deamidation", evs)
    assert len(ranked) == 1


def test_rerank_topk_capped():
    evs = [_ev(str(i), f"Antibody deamidation paper {i}", abstract="deamidation") for i in range(20)]
    ranked = rerank("antibody deamidation", evs, top_k=100)
    assert len(ranked) == MAX_TOP_K


def test_rerank_empty():
    assert rerank("anything", []) == []
