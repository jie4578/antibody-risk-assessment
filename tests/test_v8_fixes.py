# tests/test_v8_fixes.py
# v8 修复验证：mutate_scan 崩溃 / 文献相关性标题优先 / 用户给定位点不得冒充工具事实。

import pytest

from agent import Tool, ToolRegistry
from agent.literature_relevance import build_user_assertion_note, classify_literature_relevance
from agent.tools import tool_mutate_scan


# ---------- 1/2. mutate_scan 修复 ----------
def test_mutate_scan_returns_valid_result():
    out = tool_mutate_scan("AAANVSTT", "N4Q")
    assert "突变 N4Q 成功" in out
    assert "'dict' object" not in out  # 不再崩溃


def test_mutate_scan_real_mutation():
    out = tool_mutate_scan("AAANVSTT", "N4Q")
    before = out.split("突变后风险类别计数")[0]
    after = out.split("突变后风险类别计数")[1].split("\n")[0]
    assert "突变前风险类别计数" in out
    assert "'N-糖基化': 1" in before   # 突变前 1 个 N-糖基化
    assert "'N-糖基化'" not in after   # N4Q 消除 NVS 基序


def test_mutate_scan_real_vh_mutation():
    vh = "EVQLVESGGGLVQPGGSLRLSCAASGFNIKDTYIHWVRQAPGKGLEWVARIYPTNGYTRYADSVKGRFTISADTSKNTAYLQMNSLRAEDTAVYYCSRWGGDGFYAMDYWGQGTLVTVSS"
    out = tool_mutate_scan(vh, "N55Q")
    assert "突变 N55Q 成功" in out
    assert "突变后风险类别计数" in out


# ---------- 3/4. 分类器标题主题优先 ----------
N_GLYCO_PAPER = (
    "[1] Title: Computational analysis reveals non-consensus N-glycosylation in antibody Fab regions\n"
    "    Authors: Qiu B\n"
    "    Journal: Antibodies (2025)\n"
    "    PMID: 41090251\n"
    "    PMCID: -\n"
    "    DOI: -\n"
    "    Abstract: We characterized N-glycosylation sites; deamidation of Asn in CDRs was also considered."
)

DEAMIDATION_Q = "请分析 VH 序列中的 NG@55-56 是否存在脱酰胺化风险"


def test_classifier_title_primary():
    ann = classify_literature_relevance(DEAMIDATION_Q, N_GLYCO_PAPER)
    assert ann[0]["relevance"] != "direct"  # 摘要提到 deamidation 不能覆盖 N-糖基化标题


def test_nglyco_paper_not_direct_for_deamidation():
    ann = classify_literature_relevance(DEAMIDATION_Q, N_GLYCO_PAPER)
    assert ann[0]["relevance"] == "irrelevant"
    assert "糖基化" in ann[0]["reason"]


# ---------- v9.1: general 主题 KeyError 修复 ----------
def test_classifier_general_topic_no_crash():
    from agent.literature_relevance import _classify_for_topic, build_literature_note

    # 1) topic="general" 不抛异常
    rel, reason = _classify_for_topic("general", "any title", "any abstract")
    assert rel == "general" and reason

    # 2) 未知 topic 不抛 KeyError
    rel2, _ = _classify_for_topic("unknown", "title", "abstract")
    assert rel2 == "general"

    # 3) general 主题 + literature_search 返回 → 不崩溃（v9 中 Orchestrator 崩溃路径）
    from agent.llm import Observation

    note = build_literature_note(
        "请比较 N55Q、D102E、M107L 哪个更好",
        [Observation("literature_search",
                     "[1] Title: A study on antibody stability\n    PMID: 11111111\n    Abstract: stability analysis")],
    )
    assert note is not None
    assert "相关性=" in note


def test_classifier_four_topics_regression():
    from agent.literature_relevance import classify_literature_relevance

    def _one(question, title):
        paper = f"[1] Title: {title}\n    PMID: 22222222\n    Abstract: abstract text"
        return classify_literature_relevance(question, paper)[0]["relevance"]

    # deamidation：脱酰胺论文不能判 irrelevant
    assert _one("NG@55-56 是否存在脱酰胺化风险", "Deamidation of Asn-Gly in antibodies") in ("direct", "general")
    # isomerization
    assert _one("DG@102-103 异构化风险", "Aspartate isomerization in peptides") in ("direct", "general")
    # oxidation
    assert _one("M107 氧化风险", "Methionine oxidation in proteins") in ("direct", "general")
    # glycosylation
    assert _one("这条序列有没有 N-糖基化风险", "N-glycosylation occupancy analysis") in ("direct", "general")
    # 脱酰胺问题 + N-糖基化论文 → irrelevant（标题优先，不能回归）
    assert _one("NG@55-56 是否存在脱酰胺化风险", "N-glycosylation of antibody Fab regions") == "irrelevant"

class _StubLLM:
    def __init__(self, calls=()):
        self.calls = list(calls)
        self.seen = []

    def plan(self, question, tools):
        return list(self.calls)

    def step(self, question, observations, tools):
        from agent.llm import ReActStep

        if len(observations) < len(self.calls):
            return ReActStep(tool_call=self.calls[len(observations)])
        return ReActStep(final_answer="done")

    def answer(self, question, observations):
        self.seen = list(observations)
        return "done"


def test_user_position_not_tool_fact():
    """scan 未调用 + 用户问题含 NG@55-56 → 必须注入「用户给定」注记。"""
    from agent.agent import Agent

    llm = _StubLLM()  # 直接 final，不调用任何工具
    Agent(backend=llm, tools=ToolRegistry(), max_steps=3).run("请分析 NG@55-56 是否值得关注")
    note = next((o.result for o in llm.seen if o.tool == "fact_source"), None)
    assert note is not None
    assert "用户给定" in note and "NG@55-56" in note


def test_tool_position_can_be_called_tool_fact():
    """scan 确实返回 NG@55-56（序列来自用户问题）→ 不注入「用户给定」注记。"""
    from agent.agent import Agent
    from agent.llm import ToolCall

    VH = "EVQLVESGGGLVQPGGSLRLSCAASGFNIKDTYIHWVRQAPGKGLEWVARIYPTNGYTRYADSVKGRFTISADTSKNTAYLQMNSLRAEDTAVYYCSRWGGDGFYAMDYWGQGTLVTVSS"
    reg = ToolRegistry()
    reg.register(Tool(
        name="scan_antibody", description="d",
        func=lambda **kw: "序列长度 120 aa；风险评分 66.3（Medium Risk）；命中风险基序: [脱酰胺化] NG@55-56(CDR2)",
    ))
    llm = _StubLLM([ToolCall("scan_antibody", {"sequence": VH})])
    Agent(backend=llm, tools=reg, max_steps=3).run(f"请分析这条序列中的 NG@55-56 是否值得关注：\n{VH}")
    assert not any(o.tool == "fact_source" for o in llm.seen)  # 位点已被工具确认 → 无注记
