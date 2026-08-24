# tests/test_agent.py
# Agent 模块测试：LLM 后端 / 工具 / 记忆 / ReAct 智能体 / 多智能体编排。

import pytest

from agent import Agent, ConversationMemory, MockLLM, Orchestrator, Tool, ToolRegistry
from agent.llm import DeepSeekLLM, get_llm
from agent.tools import default_tools, tool_rag_search, tool_risk_score, tool_scan_antibody

SEQ = (
    "EVQLVESGGGLVQPGGSLRLSCAASGFNIKDTYIHWVRQAPGKGLEWVARIYPTNGYTRYADSVKG"
    "RFTISADTSKNTAYLQMNSLRAEDTAVYYCSRWGGDGFYAMDYWGQGTLVTVSS"
)


# ---------- LLM 后端 ----------
def test_mock_llm_knowledge_plan():
    llm = MockLLM()
    calls = llm.plan("什么是脱酰胺化？", default_tools().list())
    assert any(c.name == "rag_search" for c in calls)


def test_mock_llm_sequence_plan():
    llm = MockLLM()
    calls = llm.plan("请评估这条序列的风险：" + SEQ, default_tools().list())
    assert any(c.name == "scan_antibody" for c in calls)


def test_get_llm_unknown():
    with pytest.raises(ValueError):
        get_llm("nope")


def test_deepseek_llm_requires_key(monkeypatch):
    # 环境未装 openai → ImportError；装过但缺 key → RuntimeError。两者均应视为"不可用"。
    monkeypatch.delenv("DEEPSEEK_API_KEY", raising=False)
    with pytest.raises((ImportError, RuntimeError)):
        DeepSeekLLM()


# ---------- 工具 ----------
def test_default_tools_contains_core_tools():
    names = default_tools().names()
    assert "scan_antibody" in names
    assert "rag_search" in names


def test_tool_scan_returns_report():
    res = tool_scan_antibody(SEQ)
    assert "风险评分" in res


def test_tool_risk_score():
    res = tool_risk_score(SEQ)
    assert res.startswith("风险评分")


def test_tool_rag_search_returns_context():
    res = tool_rag_search("脱酰胺化为什么重要？")
    assert "脱酰胺" in res


def test_tool_registry_duplicate_and_unknown():
    reg = ToolRegistry()
    reg.register(Tool(name="a", description="a", func=lambda: "x"))
    with pytest.raises(ValueError):
        reg.register(Tool(name="a", description="a", func=lambda: "y"))
    with pytest.raises(KeyError):
        reg.get("nope")


# ---------- 记忆 ----------
def test_memory_accumulates_context():
    m = ConversationMemory()
    m.add_user("问题")
    m.add_observation("scan_antibody", "风险评分 60")
    m.remember("CDR2 存在 NG 位点")
    ctx = m.context()
    assert "问题" in ctx
    assert "风险评分 60" in ctx
    assert "CDR2 存在 NG 位点" in ctx


# ---------- 智能体 ----------
def test_agent_knowledge_question():
    a = Agent()
    r = a.run("什么是脱酰胺化？")
    assert any(s["tool"] == "rag_search" for s in r["steps"])
    assert "脱酰胺" in r["answer"]


def test_agent_scan_question():
    a = Agent()
    r = a.run("请评估这条序列的风险：" + SEQ)
    assert any(s["tool"] == "scan_antibody" for s in r["steps"])
    assert "风险评分" in r["answer"]


def test_agent_shares_memory():
    m = ConversationMemory()
    a = Agent(backend="mock", memory=m)
    a.run("什么是脱酰胺化？" + SEQ)
    assert any(msg["role"] == "user" for msg in m.history())
    assert any(msg["role"] == "observation" for msg in m.history())


# ---------- LangChain adapter (langchain 可选) ----------
def test_langchain_adapter_wrap_tools_when_present():
    pytest.importorskip("langchain")
    from agent.langchain_adapter import wrap_tools

    tools = wrap_tools()
    assert len(tools) >= 5


# ---------- 多智能体编排 ----------
def test_orchestrator_decompose():
    o = Orchestrator()
    active = o.decompose("评估这条序列的风险并告诉我脱酰胺化为什么重要：" + SEQ)
    assert "scan_agent" in active
    assert "knowledge_agent" in active


def test_orchestrator_run_aggregates():
    o = Orchestrator()
    res = o.run("评估这条序列的风险并告诉我脱酰胺化为什么重要：" + SEQ)
    assert res["agents"]
    assert len(res["results"]) == len(res["agents"])
    assert res["answer"]
    # 汇聚结果应同时包含规则扫描与知识检索
    combined = "".join(r["answer"] for r in res["results"])
    assert "风险" in combined or "脱酰胺" in combined
