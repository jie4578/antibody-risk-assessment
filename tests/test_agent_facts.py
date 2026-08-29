# tests/test_agent_facts.py
# 工具事实边界（v5）：最终回答只能基于工具返回结果；
# answer() 必须注入工具事实；专家只收集事实；越权数据触发重写。

from types import SimpleNamespace

import pytest

from agent.llm import DeepSeekLLM, Observation


class _FakeCompletions:
    def __init__(self, content="final"):
        self.calls = []
        msg = SimpleNamespace(content=content, tool_calls=[])
        self._resp = SimpleNamespace(choices=[SimpleNamespace(message=msg)])

    def create(self, **kwargs):
        self.calls.append(kwargs)
        return self._resp


def _fake_llm():
    llm = DeepSeekLLM()
    comp = _FakeCompletions()
    llm._client = SimpleNamespace(chat=SimpleNamespace(completions=comp))
    return llm, comp


# ---------- 1. answer() 必须把工具事实注入 user 消息 ----------
def test_answer_injects_tool_facts():
    llm, comp = _fake_llm()
    llm.answer("分析 AAANVSTT", [Observation("scan_antibody", "风险评分 91.0（Low Risk）")])
    user = comp.calls[-1]["messages"][1]["content"]
    assert "风险评分 91.0（Low Risk）" in user  # 工具事实在
    assert "工具是唯一事实来源" in user


def test_answer_without_observations_keeps_question():
    llm, comp = _fake_llm()
    llm.answer("你好", [])
    assert comp.calls[-1]["messages"][1]["content"] == "你好"


# ---------- 2. 事实边界守卫 ----------
class _StubLLM:
    def __init__(self, answers):
        self.answers = list(answers)
        self.calls = 0
        self.last_question = ""

    def answer(self, question, observations):
        self.calls += 1
        self.last_question = question
        return self.answers.pop(0)


def test_fact_boundary_regenerates_on_invented_score():
    from agent.agent import enforce_fact_boundary

    obs = [Observation("scan_antibody", "序列长度 8 aa；风险评分 91.0（Low Risk）；命中: [N-糖基化] NVS@4-6(FW)")]
    llm = _StubLLM(["重写: 风险评分 91.0（Low Risk）"])  # 重写时返回干净答案
    out = enforce_fact_boundary(llm, "q", obs, "score 0.72 且 风险评分 91.0（Low Risk）")
    assert llm.calls == 1  # 越权 0.72 → 重写一次
    assert "重写" in out
    assert "工具未返回" in llm.last_question  # 重写时带提醒


def test_fact_boundary_passes_clean_answer():
    from agent.agent import enforce_fact_boundary

    obs = [Observation("risk_score", "风险评分 91.0（Low Risk）")]
    llm = _StubLLM(["风险评分 91.0（Low Risk）"])
    out = enforce_fact_boundary(llm, "q", obs, "风险评分 91.0（Low Risk）")
    assert llm.calls == 0  # 无越权 → 不重写
    assert out == "风险评分 91.0（Low Risk）"


# ---------- 3. run_collect：只收集事实，不生成报告 ----------
def test_run_collect_no_report():
    from agent import Agent

    r = Agent(backend="mock").run_collect("什么是脱酰胺化？")
    assert "observations" in r and "steps" in r
    assert "answer" not in r
    assert r["observations"]  # 至少一个工具事实


# ---------- 4. Orchestrator：专家无报告 + 模板污染移除 + 事实暴露 ----------
def test_orchestrator_facts_only_and_no_template():
    from agent import Orchestrator

    o = Orchestrator()
    res = o.run("什么是脱酰胺化？")
    assert res["answer"]
    assert res["tool_facts"]
    assert "我协调了多个专家智能体" not in res["answer"]  # 旧聚合模板已移除
    assert "以上为多专家协同的离线演示回复" not in res["answer"]
    for r in res["results"]:
        assert r["answer"] == ""  # 专家不再生成完整报告
