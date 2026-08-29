# tests/test_literature_relevance.py
# v7 文献相关性优化：无关文献不得作为直接证据；相关文献才可引用；无相关文献明确说明。

from agent import Tool, ToolRegistry
from agent.llm import SCIENTIFIC_SYSTEM_PROMPT as P
from agent.literature_relevance import (
    build_literature_note,
    classify_literature_relevance,
)

# 与 NG 脱酰胺无关的 N-糖基化论文（Qiu B 场景）
N_GLYCO_PAPER = (
    "[1] Title: N-glycosylation sites in antibody Fab regions\n"
    "    Authors: Qiu B, Wang X\n"
    "    Journal: Antibodies (2025)\n"
    "    PMID: 41090251\n"
    "    PMCID: -\n"
    "    DOI: 10.xxxx/yyy\n"
    "    Abstract: We characterized non-consensus N-glycosylation in Fab domains, glycan occupancy and fucosylation."
)
# 与脱酰胺相关的文献（抗体 CDR 脱酰胺）
DEAMIDATION_PAPER = (
    "[1] Title: Deamidation of Asn-Gly motifs in therapeutic antibody CDRs\n"
    "    Authors: Smith J\n"
    "    Journal: mAbs (2023)\n"
    "    PMID: 22334455\n"
    "    PMCID: -\n"
    "    DOI: 10.xxxx/abc\n"
    "    Abstract: Asn-Gly is prone to deamidation via succinimide intermediates, affecting antibody charge heterogeneity."
)

Q = "请分析 VH 序列中的 NG@55-56 是否值得关注，并查找相关文献"


# ---------- 1/6. 无关 N-糖基化论文不得作为 NG 脱酰胺证据 ----------
def test_nglyco_paper_irrelevant_for_deamidation():
    ann = classify_literature_relevance(Q, N_GLYCO_PAPER)
    assert ann[0]["relevance"] == "irrelevant"
    assert "糖基化" in ann[0]["reason"]


# ---------- 2. 相关文献可以引用 ----------
def test_deamidation_antibody_paper_relevant():
    ann = classify_literature_relevance(Q, DEAMIDATION_PAPER)
    assert ann[0]["relevance"] == "direct"


def test_deamidation_mechanism_paper_general():
    mech = (
        "[1] Title: Asparagine deamidation chemistry\n"
        "    Authors: Geiger T\n"
        "    Journal: J Pharm Sci (2019)\n"
        "    PMID: 99887766\n"
        "    PMCID: -\n"
        "    DOI: -\n"
        "    Abstract: Asparagine deamidation proceeds through a succinimide intermediate under physiological conditions."
    )
    ann = classify_literature_relevance(Q, mech)
    assert ann[0]["relevance"] == "general"


# ---------- 3. 没有相关文献时明确"未找到直接相关文献" ----------
def test_note_marks_no_direct_literature():
    from agent.llm import Observation

    note = build_literature_note(Q, [Observation("literature_search", N_GLYCO_PAPER)])
    assert note is not None
    assert "本次检索未找到直接相关文献" in note
    assert "相关性=irrelevant" in note


def test_note_none_without_literature():
    from agent.llm import Observation

    assert build_literature_note(Q, [Observation("scan_antibody", "风险评分 91.0")]) is None


# ---------- 4. 不允许自行生成 PMID/DOI ----------
def test_prompt_forbids_invented_metadata():
    assert "不得使用模型记忆自行生成 PMID、DOI" in P


# ---------- 5. 一般性证据 ≠ 当前抗体已实验验证 ----------
def test_note_not_validated_for_this_antibody():
    from agent.llm import Observation

    note = build_literature_note(Q, [Observation("literature_search", DEAMIDATION_PAPER)])
    assert "未验证是否针对本抗体/本位点" in note


# ---------- 7. prompt 要求相关性过滤 ----------
def test_prompt_requires_relevance_filter():
    assert "irrelevant" in P
    assert "N-糖基化论文作为脱酰胺风险" in P


# ---------- 8. 集成：Agent 最终回答注入相关性注记(离线) ----------
class _StubLLM:
    def __init__(self, calls):
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


def test_agent_run_attaches_relevance_note():
    from agent.agent import Agent
    from agent.llm import ToolCall

    reg = ToolRegistry()
    reg.register(Tool(name="literature_search", description="d", func=lambda **kw: N_GLYCO_PAPER))
    llm = _StubLLM([ToolCall("literature_search", {"query": "NG deamidation"})])
    Agent(backend=llm, tools=reg, max_steps=4).run(Q)
    assert any(o.tool == "literature_relevance" for o in llm.seen)
    note = next(o.result for o in llm.seen if o.tool == "literature_relevance")
    assert "相关性=irrelevant" in note
