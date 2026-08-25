# tests/test_literature/test_search.py
# search_literature：API 响应解析 / 缺字段 / 空结果 / API 失败 / auto 回退 / 缓存。
# 全部离线（monkeypatch _request），不联网。

import pytest

import literature.search as search_mod
from literature import LiteratureSearchError, search_literature
from literature.errors import LiteratureSearchError as LitErr

from .fixtures_data import (
    EUROPEMC_EMPTY_RESULT,
    PUBMED_ESEARCH_EMPTY,
    fake_europepmc_request,
)


def _patch_request(monkeypatch, fake):
    monkeypatch.setattr(search_mod, "_request", fake)


# ---------- 解析 ----------
def test_europepmc_parse_valid_evidence(monkeypatch):
    _patch_request(monkeypatch, fake_europepmc_request)
    evs = search_literature("antibody deamidation", source="europepmc", use_cache=False)
    # 第 3 条(无 pmid 无 abstract)应被过滤 → 剩 2 条
    assert len(evs) == 2
    first = evs[0]
    assert first.pmid == "35921488"
    assert first.pmcid == "PMC9234567"
    assert first.doi == "10.1016/j.xphs.2022.06.003"
    assert first.source == "europepmc"
    assert first.is_open_access is True
    assert first.full_text_available is True
    assert first.year == 2022
    assert first.authors == ["Zhang Y", "Li W", "Wang Q"]


def test_pubmed_parse_metadata_and_abstract(monkeypatch):
    _patch_request(monkeypatch, fake_europepmc_request)
    evs = search_literature("antibody deamidation", source="pubmed", use_cache=False)
    assert len(evs) == 2
    first = evs[0]
    assert first.pmid == "20000001"
    assert first.source == "pubmed"
    assert first.doi == "10.1111/antibody.1"
    assert first.pmcid == "PMC7777777"
    assert first.year == 2021
    assert "Review of antibody deamidation" in first.abstract  # 来自 efetch XML
    assert first.authors == ["Li M"]


# ---------- auto 回退 ----------
def test_auto_falls_back_to_pubmed_when_europepmc_empty(monkeypatch):
    def fake(url, params, *, timeout, retries, source, as_text=False):
        if "europepmc" in url:
            return EUROPEMC_EMPTY_RESULT
        return fake_europepmc_request(url, params, timeout=timeout, retries=retries, source=source, as_text=as_text)

    _patch_request(monkeypatch, fake)
    evs = search_literature("antibody deamidation", source="auto", use_cache=False)
    assert len(evs) == 2
    assert all(e.source == "pubmed" for e in evs)


# ---------- 空结果（≠ API 故障）----------
def test_no_results_returns_empty_list(monkeypatch):
    def fake(url, params, *, timeout, retries, source, as_text=False):
        if "europepmc" in url:
            return EUROPEMC_EMPTY_RESULT
        return PUBMED_ESEARCH_EMPTY

    _patch_request(monkeypatch, fake)
    evs = search_literature("xyzabc123456 nonexistent", source="auto", use_cache=False)
    assert evs == []


# ---------- API 故障（必须抛错，不能伪装成空结果）----------
def test_api_failure_raises(monkeypatch):
    def fake(url, params, *, timeout, retries, source, as_text=False):
        raise LitErr("api_unavailable", "[europepmc] HTTP 500", status_code=500, source="europepmc")

    _patch_request(monkeypatch, fake)
    with pytest.raises(LiteratureSearchError):
        search_literature("antibody", source="europepmc", use_cache=False)


def test_auto_both_sources_fail_raises(monkeypatch):
    def fake(url, params, *, timeout, retries, source, as_text=False):
        raise LitErr("api_unavailable", f"[{source}] HTTP 500", status_code=500, source=source)

    _patch_request(monkeypatch, fake)
    with pytest.raises(LiteratureSearchError):
        search_literature("antibody", source="auto", use_cache=False)


# ---------- 输入校验 ----------
def test_invalid_source_raises():
    with pytest.raises(LiteratureSearchError):
        search_literature("antibody", source="nope", use_cache=False)


def test_empty_query_raises():
    with pytest.raises(LiteratureSearchError):
        search_literature("   ", use_cache=False)


# ---------- 缓存 ----------
def test_cache_hit_avoids_second_request(monkeypatch, tmp_path):
    calls = {"n": 0}

    def fake(url, params, *, timeout, retries, source, as_text=False):
        calls["n"] += 1
        return fake_europepmc_request(url, params, timeout=timeout, retries=retries, source=source, as_text=as_text)

    _patch_request(monkeypatch, fake)
    from literature.cache import LiteratureCache

    cache = LiteratureCache(str(tmp_path / "c.db"))
    monkeypatch.setattr(search_mod, "get_cache", lambda: cache)

    evs1 = search_literature("antibody deamidation", source="europepmc", use_cache=True)
    evs2 = search_literature("antibody deamidation", source="europepmc", use_cache=True)
    assert len(evs1) == len(evs2) == 2
    assert calls["n"] == 1  # 第二次命中缓存，未再请求 API
