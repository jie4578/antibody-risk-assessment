# tests/test_literature/test_pipeline.py
# Pipeline：无证据 / API 故障 / 正常回答 / 引用校验与 regenerate（全部离线 mock）。

import pytest

import literature.pipeline as pipe_mod
from literature import LiteratureSearchError, answer_question
from literature.evidence import Evidence


def _ev(pmid="12345678", doi="10.1000/abc"):
    return Evidence(
        evidence_id=f"e:{pmid}", title="Antibody deamidation review", pmid=pmid, doi=doi,
        abstract="Asn-Gly motifs are prone to deamidation.", source="europepmc",
    )


def _patch_search(monkeypatch, result):
    monkeypatch.setattr(pipe_mod, "search_literature", lambda *a, **kw: result)


def _patch_llm(monkeypatch, answers):
    """answers: 可迭代，每次调用返回下一个。"""
    it = iter(answers)

    def fake(question, context, backend, *, fix_citation=False):
        return next(it)

    monkeypatch.setattr(pipe_mod, "_llm_answer", fake)


def test_pipeline_no_evidence(monkeypatch):
    _patch_search(monkeypatch, [])
    res = answer_question("xyzabc123456 不存在的主题", backend="mock")
    assert res.status == "no_evidence"
    assert "未检索到足够相关的文献证据" in res.answer


def test_pipeline_api_unavailable(monkeypatch):
    def boom(*a, **kw):
        raise LiteratureSearchError("api_unavailable", "[europepmc] HTTP 500", source="europepmc")

    monkeypatch.setattr(pipe_mod, "search_literature", boom)
    res = answer_question("antibody", backend="mock")
    assert res.status == "api_unavailable"
    assert "不可用" in res.error


def test_pipeline_ok_with_valid_citation(monkeypatch):
    _patch_search(monkeypatch, [_ev()])
    _patch_llm(monkeypatch, ["Asn-Gly 易脱酰胺 (PMID: 12345678)"])
    res = answer_question("什么是抗体脱酰胺化？", backend="mock")
    assert res.status == "ok"
    assert res.validation["valid"] is True
    assert len(res.evidence) == 1


def test_pipeline_invalid_citation_triggers_regenerate(monkeypatch):
    _patch_search(monkeypatch, [_ev()])
    # 第一次编造 PMID → 触发 regenerate；第二次合法 → ok
    _patch_llm(monkeypatch, ["(PMID: 99999999)", "(PMID: 12345678)"])
    res = answer_question("什么是抗体脱酰胺化？", backend="mock")
    assert res.status == "ok"
    assert res.validation["valid"] is True


def test_pipeline_citation_failed_after_retry(monkeypatch):
    _patch_search(monkeypatch, [_ev()])
    # 两次都编造 → citation_failed
    _patch_llm(monkeypatch, ["(PMID: 99999999)", "(PMID: 88888888)"])
    res = answer_question("什么是抗体脱酰胺化？", backend="mock")
    assert res.status == "citation_failed"
    assert res.validation["valid"] is False
