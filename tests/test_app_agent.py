# tests/test_app_agent.py
# 页面层 Agent 回调测试：格式化 / 返回值数量 / 异常不吞成"错误" / 脱敏（mock，不调用真实 LLM）。

import pytest

import app
from app import _redact_sensitive, format_agent_steps


def _tool_step(tool="scan_antibody", args=None, result="风险评分 91.0", retried=False):
    return {"type": "tool", "tool": tool, "arguments": args or {"sequence": "AAANVSTT"},
            "result": result, "retried": retried}


def _final_step(answer="最终回答"):
    return {"type": "final", "answer": answer, "thought": "t"}


class _FakeAgent:
    def __init__(self, result=None, error=None):
        self._result = result or {"steps": [_tool_step(), _final_step()], "answer": "回答文本"}
        self._error = error

    def run(self, question):
        if self._error:
            raise self._error
        return self._result


class _FakeOrchestrator:
    def __init__(self, result=None, error=None):
        self._result = result or {
            "agents": ["scan_agent"],
            "results": [{"agent": "scan_agent", "steps": [_tool_step(), _final_step()], "answer": "内层"}],
            "answer": "汇总回答",
        }
        self._error = error

    def run(self, question):
        if self._error:
            raise self._error
        return self._result


# ---------- format_agent_steps ----------
def test_format_steps_tool_and_final():
    txt = format_agent_steps([_tool_step(), _final_step()])
    assert "scan_antibody" in txt
    assert "风险评分 91.0" in txt
    assert "最终回答" not in txt  # final 不进日志


def test_format_steps_empty():
    assert format_agent_steps([]) == "（未调用工具）"


def test_format_steps_retry_flag():
    txt = format_agent_steps([_tool_step(retried=True)])
    assert "[重试]" in txt


def test_format_steps_redacts_key():
    txt = format_agent_steps([_tool_step(result="error sk-abc12345xyz")])
    assert "sk-abc12345xyz" not in txt
    assert "sk-****" in txt


# ---------- 脱敏 ----------
def test_redact_sensitive():
    assert _redact_sensitive("key=sk-abc12345xyz") == "key=sk-****"


# ---------- agent_orchestrate_wrapper ----------
def test_orchestrate_wrapper_success(monkeypatch):
    import agent as agent_mod

    monkeypatch.setattr(app, "_llm_backend", lambda: "mock")
    monkeypatch.setattr(agent_mod, "Orchestrator", lambda **kw: _FakeOrchestrator())
    out = app.agent_orchestrate_wrapper("分析 AAANVSTT")
    assert len(out) == 2  # 与 Gradio outputs 数量一致
    log, ans = out
    assert "scan_antibody" in log
    assert "汇总回答" in ans


def test_orchestrate_wrapper_error_not_swallowed(monkeypatch):
    import agent as agent_mod

    monkeypatch.setattr(app, "_llm_backend", lambda: "mock")
    boom = _FakeOrchestrator(error=RuntimeError("sk-abc12345xyz boom"))
    monkeypatch.setattr(agent_mod, "Orchestrator", lambda **kw: boom)
    log, ans = app.agent_orchestrate_wrapper("问题")
    assert "❌" in log and "RuntimeError" in log and "boom" in log
    assert "sk-abc12345xyz" not in log  # key 已脱敏
    assert log == ans  # 两个输出一致(错误块)


# ---------- agent_ask_wrapper ----------
def test_ask_wrapper_success(monkeypatch):
    import agent as agent_mod

    monkeypatch.setattr(agent_mod, "Agent", lambda **kw: _FakeAgent())
    log, ans, tool = app.agent_ask_wrapper("分析")
    assert "scan_antibody" in log
    assert ans == "回答文本"
    assert tool == "scan_antibody"


def test_ask_wrapper_error(monkeypatch):
    import agent as agent_mod

    monkeypatch.setattr(agent_mod, "Agent", lambda **kw: _FakeAgent(error=ValueError("bad input")))
    log, ans, tool = app.agent_ask_wrapper("分析")
    assert "❌" in log and "ValueError" in log
    assert tool == "（无）"
