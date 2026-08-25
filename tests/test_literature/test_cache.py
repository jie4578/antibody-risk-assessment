# tests/test_literature/test_cache.py
# 缓存：命中 / 过期 / 清除 / key 规范化。

import time

from literature.cache import LiteratureCache, cache_key, normalize_query


def test_cache_set_get(tmp_path):
    c = LiteratureCache(str(tmp_path / "c.db"))
    c.set("k1", [{"a": 1}])
    assert c.get("k1") == [{"a": 1}]
    assert c.get("missing") is None


def test_cache_expiry(tmp_path):
    c = LiteratureCache(str(tmp_path / "c.db"), ttl_seconds=0)  # 立即过期
    c.set("k1", [{"a": 1}])
    assert c.get("k1") is None


def test_cache_clear(tmp_path):
    c = LiteratureCache(str(tmp_path / "c.db"))
    c.set("k1", [1])
    c.clear()
    assert c.get("k1") is None


def test_normalize_query():
    assert normalize_query("  Antibody   DEAMIDATION  ") == "antibody deamidation"


def test_cache_key_components():
    assert cache_key("A b", "europepmc", 5) == cache_key("a   b", "europepmc", 5)
    assert cache_key("a", "pubmed", 5) != cache_key("a", "europepmc", 5)
