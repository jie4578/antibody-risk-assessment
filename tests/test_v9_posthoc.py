# tests/test_v9_posthoc.py
# v9.2 post-hoc 确定性校验：位点声称 + PMID/DOI 引用。

import pytest

from agent.agent import (
    enforce_claim_boundaries,
    validate_literature_citations,
    validate_position_claims,
)
from agent.llm import Observation
from agent.tools import tool_mutate_scan

DEAMIDATION_Q = "请分析 VH 序列中的 NG@55-56 是否存在脱酰胺化风险"

N_GLYCO_PAPER = (
    "[1] Title: Computational analysis reveals non-consensus N-glycosylation in antibody Fab regions\n"
    "    Authors: Qiu B\n"
    "    Journal: Antibodies (2025)\n"
    "    PMID: 41090251\n"
    "    DOI: 10.1016/j.ab.2025.01.001\n"
    "    Abstract: We characterized N-glycosylation sites; deamidation of Asn was also considered."
)
DEAM_PAPER = (
    "[1] Title: Deamidation of Asn-Gly motifs in therapeutic antibody CDRs\n"
    "    Authors: Smith J\n"
    "    Journal: mAbs (2023)\n"
    "    PMID: 12345678\n"
    "    DOI: 10.1080/19420862.2023.1234567\n"
    "    Abstract: Asn-Gly is prone to deamidation via succinimide intermediates in antibodies."
)


# ---------- 1. 用户给定位点 ≠ 工具事实 ----------
def test_posthoc_user_position_not_tool_fact():
    bad = validate_position_claims("工具检测到 NG@55-56 存在脱酰胺风险", "请分析 NG@55-56", [])
    assert any("用户给定" in b for b in bad)


def test_posthoc_user_position_ok_when_marked_user_given():
    bad = validate_position_claims(
        "用户给定的 NG@55-56 未经工具验证，不能视为工具检测结果", "请分析 NG@55-56", []
    )
    assert bad == []


# ---------- 2. 工具实际返回位点允许声明 ----------
def test_posthoc_tool_position_can_be_claimed():
    obs = [Observation("scan_antibody", "命中风险基序: [脱酰胺化] NG@55-56(CDR2)")]
    bad = validate_position_claims("工具检测到 NG@55-56 脱酰胺风险位点", "请分析风险", obs)
    assert bad == []


# ---------- 3. 编造位点触发重写 ----------
def test_posthoc_unknown_position_triggers_rewrite():
    bad = validate_position_claims("XX@99-100 是工具检测到的风险位点", "请分析风险", [])
    assert any("99" in b for b in bad)


class _StubLLM:
    def __init__(self, answers):
        self.answers = list(answers)
        self.calls = 0
        self.last_question = ""

    def answer(self, question, observations):
        self.calls += 1
        self.last_question = question
        return self.answers.pop(0)


def test_posthoc_rewrite_once_on_violation():
    llm = _StubLLM(["用户给定的 NG@55-56 未经工具验证"])  # 重写时返回干净答案
    out = enforce_claim_boundaries(llm, "请分析 NG@55-56", [], "工具检测到 NG@55-56 是风险位点")
    assert llm.calls == 1  # 越权 → 重写一次
    assert "用户给定" in out
    assert "事实边界问题" in llm.last_question


# ---------- 4/5. PMID 校验 ----------
def test_unknown_pmid_triggers_rewrite():
    bad = validate_literature_citations("该机制可见 PMID 12345678", "问题", [])
    assert any("12345678" in b for b in bad)


def test_known_pmid_allowed():
    obs = [Observation("literature_search", DEAM_PAPER)]
    bad = validate_literature_citations("该机制可见 PMID 12345678", DEAMIDATION_Q, obs)
    assert bad == []


# ---------- 6. irrelevant 文献即使 PMID 存在也不得引用 ----------
def test_irrelevant_pmid_not_allowed():
    obs = [Observation("literature_search", N_GLYCO_PAPER)]
    bad = validate_literature_citations("支持证据 PMID 41090251", DEAMIDATION_Q, obs)
    assert any("irrelevant" in b for b in bad)


def test_irrelevant_doi_not_allowed():
    obs = [Observation("literature_search", N_GLYCO_PAPER)]
    bad = validate_literature_citations("DOI 10.1016/j.ab.2025.01.001", DEAMIDATION_Q, obs)
    assert any("irrelevant" in b for b in bad)


# ---------- 7. general topic 不崩溃(v9.1 回归) ----------
def test_general_topic_no_crash():
    from agent.literature_relevance import _classify_for_topic

    assert _classify_for_topic("general", "t", "a")[0] == "general"
    assert _classify_for_topic("unknown", "t", "a")[0] == "general"


# ---------- 8. mutate_scan 回归(v8 修复) ----------
def test_mutate_scan_regression():
    out = tool_mutate_scan("AAANVSTT", "N4Q")
    assert "突变 N4Q 成功" in out
    assert "'dict' object" not in out
