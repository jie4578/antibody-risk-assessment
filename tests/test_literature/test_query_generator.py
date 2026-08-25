# tests/test_literature/test_query_generator.py
# Query Generator：只生成检索词、绝不生成论文/引用；LLM 异常/违规回退规则模式。

import pytest

from literature.query_generator import TERM_MAP, _rule_query, generate_query


class _StubLLM:
    def __init__(self, text):
        self.text = text

    def complete(self, prompt, system_prompt=None):
        return self.text


def test_rule_query_uses_term_map():
    q, mode = generate_query("什么是抗体脱酰胺化？", backend="mock")
    assert mode == "rule"
    assert "antibody" in q
    assert "deamidation" in q


def test_rule_query_never_contains_citation():
    q, mode = generate_query("什么是抗体脱酰胺化？", backend="mock")
    # 不允许出现 PMID 样式数字 / DOI / Title 等论文元数据
    assert not any(ch.isdigit() for ch in q)
    assert "PMID" not in q.upper()
    assert "10." not in q


def test_rule_query_english_words():
    q, _ = generate_query("What causes antibody deamidation?", backend="mock")
    assert "antibody" in q
    assert "deamidation" in q


def test_llm_mode_returns_query(monkeypatch):
    import agent.llm as llm_mod

    monkeypatch.setattr(llm_mod, "get_llm", lambda name="mock", **kw: _StubLLM('("antibody" OR "therapeutic antibody") AND deamidation'))
    q, mode = generate_query("什么是抗体脱酰胺化？", backend="deepseek")
    assert mode == "llm"
    assert "deamidation" in q


def test_llm_forbidden_output_falls_back_to_rule(monkeypatch):
    import agent.llm as llm_mod

    # LLM 违规输出论文标题/PMID → 必须被拒绝并回退规则
    monkeypatch.setattr(llm_mod, "get_llm", lambda name="mock", **kw: _StubLLM("PMID: 12345678 Some invented paper title"))
    q, mode = generate_query("什么是抗体脱酰胺化？", backend="deepseek")
    assert mode == "rule"
    assert "12345678" not in q


def test_llm_exception_falls_back_to_rule(monkeypatch):
    import agent.llm as llm_mod

    def boom(name="mock", **kw):
        raise RuntimeError("llm down")

    monkeypatch.setattr(llm_mod, "get_llm", boom)
    q, mode = generate_query("什么是抗体脱酰胺化？", backend="deepseek")
    assert mode == "rule"
    assert q


def test_term_map_has_key_terms():
    for cn in ("脱酰胺化", "糖基化", "抗体", "氧化", "免疫原性"):
        assert cn in TERM_MAP
