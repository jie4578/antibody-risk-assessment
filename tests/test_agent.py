# tests/test_agent.py
# Agent 模块测试：LLM 后端 / 工具 / 记忆 / ReAct 智能体 / 多智能体编排。

import pytest

from agent import Agent, ConversationMemory, MockLLM, Orchestrator, Tool, ToolRegistry
from agent.llm import DeepSeekLLM, ToolCall, get_llm
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
    # 让 config 不加载真实 .env 且清掉环境变量 → 缺 key → 应抛错（未装 openai 时抛 ImportError，否则 RuntimeError）
    import config

    monkeypatch.setattr(config, "_DOTENV_PATHS", [])
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


def test_langchain_adapter_tool_invoke_when_present():
    pytest.importorskip("langchain")
    from agent.langchain_adapter import wrap_tools

    tools = wrap_tools()
    rag = [t for t in tools if t.name == "rag_search"][0]
    result = rag.invoke({"question": "什么是脱酰胺化？"})
    assert "脱酰胺" in str(result)


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


# ---------- 真 ReAct 迭代循环 ----------
def test_react_multistep_executes_tools_in_order():
    # 含序列 + 突变关键词 + "风险" → mock 规划为 [scan_antibody, mutate_scan, rag_search]，循环应逐步执行
    a = Agent()
    r = a.run("评估这条序列的风险并做 N55Q 突变：" + SEQ)
    tools = [s["tool"] for s in r["steps"] if s["type"] == "tool"]
    assert tools == ["scan_antibody", "mutate_scan", "rag_search"]
    assert any(s["type"] == "final" for s in r["steps"])


def test_react_stops_early_with_final_answer():
    # 无任何工具触发 → 第一轮即 Final Answer，steps 里不应有 tool 步骤
    a = Agent()
    r = a.run("你好")
    assert all(s["type"] == "final" for s in r["steps"])
    assert r["answer"]


class _StubLLM:
    """固定返回工具调用序列、最后给 Final Answer 的桩 LLM。"""

    def __init__(self, calls, final="done"):
        self.calls = list(calls)
        self.final = final

    def plan(self, question, tools):
        return list(self.calls)

    def step(self, question, observations, tools):
        from agent.llm import ReActStep

        if len(observations) < len(self.calls):
            return ReActStep(tool_call=self.calls[len(observations)])
        return ReActStep(final_answer=self.final)

    def answer(self, question, observations):
        return self.final


def test_react_tool_failure_retries_once(monkeypatch):
    from agent import Tool, ToolRegistry
    from agent.agent import Agent

    calls = {"n": 0}

    def bad_func(**kwargs):
        calls["n"] += 1
        return "工具 bad_tool 执行异常: boom"

    reg = ToolRegistry()
    reg.register(Tool(name="bad_tool", description="always fails", func=bad_func))
    agent = Agent(backend=_StubLLM([ToolCall("bad_tool", {})]), tools=reg, max_steps=3)
    r = agent.run("随便")
    assert calls["n"] == 2  # 初始 + 反思重试一次
    tool_step = [s for s in r["steps"] if s["type"] == "tool"][0]
    assert tool_step["retried"] is True


class _NeverFinalLLM:
    """永远返回工具调用、从不给 Final Answer 的桩（用于验证 max_steps 截断）。"""

    def plan(self, question, tools):
        return []

    def step(self, question, observations, tools):
        from agent.llm import ReActStep

        return ReActStep(tool_call=ToolCall("risk_score", {"sequence": "ACD"}))

    def answer(self, question, observations):
        return "done"


def test_react_max_steps_stops_and_answers():
    from agent.agent import Agent

    # 桩永远返回工具调用 → 循环应被 max_steps 截断并走 answer 兜底
    agent = Agent(backend=_NeverFinalLLM(), tools=None, max_steps=3)
    r = agent.run("打分")
    assert r["answer"] == "done"
    tool_count = len([s for s in r["steps"] if s["type"] == "tool"])
    assert tool_count == 3  # max_steps=3 全部用于工具步后走兜底回答
