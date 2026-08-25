# tests/test_literature/test_live.py
# Live 测试：真实调用 Europe PMC / PubMed（需要网络）。
# 默认 skip；手动执行：pytest -m live

import pytest

pytestmark = pytest.mark.live


def test_live_europepmc_search():
    from literature import search_literature

    evs = search_literature(
        "asparagine deamidation antibody", max_results=3, source="europepmc", use_cache=False
    )
    assert len(evs) >= 1
    assert all(e.is_valid() for e in evs)
    assert all(e.source == "europepmc" for e in evs)


def test_live_pubmed_search():
    from literature import search_literature

    evs = search_literature(
        "asparagine deamidation antibody", max_results=3, source="pubmed", use_cache=False
    )
    assert len(evs) >= 1
    assert all(e.is_valid() for e in evs)


def test_live_fulltext_oa():
    from literature import fetch_full_text, search_literature

    evs = search_literature(
        "antibody deamidation", max_results=10, source="europepmc", use_cache=False
    )
    oa = [e for e in evs if e.is_open_access and e.pmcid]
    if not oa:
        pytest.skip("本次检索未找到 Open Access 全文")
    text = fetch_full_text(oa[0].pmcid)
    assert len(text) > 100
