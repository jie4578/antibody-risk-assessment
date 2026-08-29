# tests/test_agent_prompt.py
# v3.0-B：科研分析 System Prompt 注入验证（离线，不联网）。

from types import SimpleNamespace

import pytest

from agent.llm import SCIENTIFIC_SYSTEM_PROMPT, DeepSeekLLM, MockLLM, get_llm
from agent.tools import default_tools


class _FakeCompletions:
    """捕获 create() 调用并返回固定响应（对应 client.chat.completions）。"""

    def __init__(self, content="final answer", tool_calls=None):
        self.calls = []
        msg = SimpleNamespace(content=content, tool_calls=tool_calls or [])
        self._resp = SimpleNamespace(choices=[SimpleNamespace(message=msg)])

    def create(self, **kwargs):
        self.calls.append(kwargs)
        return self._resp


def _fake_client(completions):
    return SimpleNamespace(chat=SimpleNamespace(completions=completions))


def test_step_first_message_is_system():
    chat = _FakeCompletions()
    llm = DeepSeekLLM()
    llm._client = _fake_client(chat)
    from agent.llm import ToolCall

    tools = default_tools().list()
    llm.step("分析 AAANVSTT 的风险", [], tools)
    msgs = chat.calls[-1]["messages"]
    assert msgs[0]["role"] == "system"
    assert msgs[0]["content"] == SCIENTIFIC_SYSTEM_PROMPT
    assert msgs[1]["role"] == "user"


def test_system_prompt_contains_required_rules():
    for keyword in ("rule_based", "heuristic", "未经实验验证", "literature_search",
                    "不得自行计算", "可追溯", "工具实际返回"):
        assert keyword in SCIENTIFIC_SYSTEM_PROMPT


def test_answer_uses_same_system_prompt():
    chat = _FakeCompletions()
    llm = DeepSeekLLM()
    llm._client = _fake_client(chat)
    from agent.llm import Observation

    llm.answer("问题", [Observation("scan_antibody", "结果")])
    msgs = chat.calls[-1]["messages"]
    assert msgs[0]["role"] == "system"
    assert msgs[0]["content"] == SCIENTIFIC_SYSTEM_PROMPT


def test_complete_uses_same_default_prompt():
    chat = _FakeCompletions()
    llm = DeepSeekLLM()
    llm._client = _fake_client(chat)
    llm.complete("prompt")
    msgs = chat.calls[-1]["messages"]
    assert msgs[0]["content"] == SCIENTIFIC_SYSTEM_PROMPT


def test_complete_custom_system_prompt_wins():
    chat = _FakeCompletions()
    llm = DeepSeekLLM()
    llm._client = _fake_client(chat)
    llm.complete("prompt", system_prompt="自定义")
    assert chat.calls[-1]["messages"][0]["content"] == "自定义"


def test_tool_calling_schema_not_broken():
    import json

    for tool in default_tools().list():
        json.dumps(tool.to_schema())  # 仍可 JSON 序列化


def test_mock_llm_untouched():
    llm = MockLLM()
    tools = default_tools().list()
    # 知识类问题 → 第一步应调用工具(rag_search/literature_search 之一)
    step = llm.step("什么是脱酰胺化？", [], tools)
    assert step.tool_call is not None or step.final_answer
    # 无工具问题 → 直接 final
    final = llm.step("你好", [], tools)
    assert final.is_final


def test_agent_with_mock_still_runs():
    from agent import Agent

    a = Agent(backend="mock")
    r = a.run("什么是脱酰胺化？")
    assert r["answer"]
