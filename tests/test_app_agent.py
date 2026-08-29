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


# ---------- 简洁科研风格格式 ----------
def test_format_steps_concise_style():
    txt = format_agent_steps([_tool_step(
        result="序列长度 120 aa；规则风险评分 66.3（Medium Risk）；命中风险基序: [脱酰胺化] NG@55-56(CDR2); [氧化] M@83(FW)"
    )])
    assert "工具调用" in txt
    assert "scan_antibody" in txt
    assert "风险评分：66.3" in txt
    assert "风险等级：Medium Risk" in txt
    assert "发现 2 个风险位点" in txt
    assert "===" not in txt      # 无分隔符
    assert "sequence=" not in txt  # 无完整参数
    assert "->" not in txt       # 无箭头


def test_format_steps_tool_failure_shows_reason():
    txt = format_agent_steps([_tool_step(result="工具 scan_antibody 执行异常: boom")])
    assert "工具调用失败：scan_antibody" in txt
    assert "原因：" in txt and "boom" in txt


# ---------- 最终回答展示清理 ----------
def test_clean_answer_strips_markdown():
    from app import _clean_answer

    out = _clean_answer("**风险位点**\n---\n### 脱酰胺化\n正文内容")
    assert "**" not in out and "---" not in out and "###" not in out
    assert "风险位点" in out and "脱酰胺化" in out and "正文内容" in out


def test_clean_answer_strips_mock_phrases():
    from app import _clean_answer

    out = _clean_answer("您好，我协调了多个专家智能体，汇总如下：\n分析结果")
    assert "您好" not in out and "我协调了多个专家智能体" not in out
    assert "分析结果" in out


def test_clean_answer_keeps_plain_text():
    from app import _clean_answer

    assert _clean_answer("普通科研文本") == "普通科研文本"


def test_clean_answer_strips_single_asterisk():
    from app import _clean_answer

    assert _clean_answer("*风险*") == "风险"


def test_clean_answer_strips_blockquote_and_code():
    from app import _clean_answer

    out = _clean_answer("> 引用块\n`code` 内容")
    assert ">" not in out and "`" not in out
    assert "引用块" in out and "code" in out


def test_clean_answer_strips_table():
    from app import _clean_answer

    out = _clean_answer("| 工具 | 结果 |\n|---|---|\n| scan | 91.0 |")
    assert "|" not in out and "---" not in out
    assert "工具" in out and "91.0" in out


def test_clean_answer_strips_underline_separator():
    from app import _clean_answer

    out = _clean_answer("标题\n___\n正文")
    assert "___" not in out and "标题" in out and "正文" in out


def test_clean_answer_strips_list_bullets():
    from app import _clean_answer

    out = _clean_answer("- NG@55-56\n* M@83")
    assert "- NG" not in out and "* M" not in out
    assert "NG@55-56" in out and "M@83" in out


def test_clean_answer_keeps_motif_dash():
    from app import _clean_answer

    # 基序中的连字符(55-56)不能被误删
    assert "NG@55-56（CDR2）" in _clean_answer("重点关注 NG@55-56（CDR2）")



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
