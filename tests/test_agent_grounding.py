# tests/test_agent_grounding.py
# v3.0-C：Evidence-Grounded Agent —— 证据边界约束测试（离线，验证实际 prompt 而非硬编码副本）。

from types import SimpleNamespace

import pytest

from agent.llm import SCIENTIFIC_SYSTEM_PROMPT, DeepSeekLLM, MockLLM, get_llm
from agent.tools import default_tools

P = SCIENTIFIC_SYSTEM_PROMPT


class _FakeCompletions:
    def __init__(self, content="final", tool_calls=None):
        self.calls = []
        msg = SimpleNamespace(content=content, tool_calls=tool_calls or [])
        self._resp = SimpleNamespace(choices=[SimpleNamespace(message=msg)])

    def create(self, **kwargs):
        self.calls.append(kwargs)
        return self._resp


def _fake_llm():
    llm = DeepSeekLLM()
    comp = _FakeCompletions()
    llm._client = SimpleNamespace(chat=SimpleNamespace(completions=comp))
    return llm, comp


# ---------- 1-12：prompt 证据边界约束 ----------
def test_prompt_forbids_self_computed_score():
    assert "不得自行计算" in P
    assert "新的风险评分" in P


def test_prompt_forbids_second_scoring_system():
    assert "新的评分体系" in P
    assert "未自行计算" in P


def test_prompt_requires_tool_score_priority():
    assert "scan_antibody 返回的风险位点可以直接报告" in P
    assert "risk_score 返回的评分和等级可以直接报告" in P
    assert "以工具实际结果为准" in P


def test_prompt_raw_1based_position():
    assert "原始输入序列的 1-based position" in P


def test_prompt_no_imgt_kabat_guess():
    for key in ("IMGT", "Kabat", "Chothia"):
        assert key in P
    assert "或其他编号体系" in P


def test_prompt_no_antibody_identity_guess():
    assert "不得根据序列猜测具体抗体身份" in P


def test_prompt_heuristic_must_be_labeled():
    assert "heuristic / 未经实验验证" in P
    assert "不得把 heuristic 描述成" in P


def test_prompt_literature_as_general_evidence():
    assert "rag_search 只能作为知识库信息" in P
    assert "不能伪装成真实文献检索结果" in P


def test_prompt_no_fabricated_pmid_doi():
    assert "PMID" in P and "DOI" in P
    assert "不得使用模型记忆自行生成" in P
    assert "本次未检索特定文献。" in P


def test_prompt_no_fabricated_experimental_data():
    assert "不得编造实验数据" in P
    assert "LC-MS/MS" in P
    assert "不得自行设计具体实验条件" in P


def test_prompt_distinguishes_information_sections():
    for key in ("工具评分", "文献证据", "重点关注", "验证建议", "说明"):
        assert key in P


def test_prompt_evidence_limitations_section():
    assert "评分和风险位点来自工具返回结果" in P
    assert "未自行计算新的评分体系" in P


# ---------- 13-15：注入回归（真实后端） ----------
def test_step_first_message_still_system():
    llm, comp = _fake_llm()
    llm.step("问题", [], default_tools().list())
    msgs = comp.calls[-1]["messages"]
    assert msgs[0]["role"] == "system"
    assert msgs[0]["content"] == SCIENTIFIC_SYSTEM_PROMPT


def test_answer_uses_same_prompt():
    from agent.llm import Observation

    llm, comp = _fake_llm()
    llm.answer("问题", [Observation("scan_antibody", "结果")])
    msgs = comp.calls[-1]["messages"]
    assert msgs[0]["content"] == SCIENTIFIC_SYSTEM_PROMPT


def test_complete_default_uses_same_prompt():
    llm, comp = _fake_llm()
    llm.complete("prompt")
    assert comp.calls[-1]["messages"][0]["content"] == SCIENTIFIC_SYSTEM_PROMPT


# ---------- 16：MockLLM 不受影响 ----------
def test_mock_llm_unaffected():
    llm = MockLLM()
    tools = default_tools().list()
    step = llm.step("什么是脱酰胺化？", [], tools)
    assert step.tool_call is not None or step.final_answer
    final = llm.step("你好", [], tools)
    assert final.is_final
