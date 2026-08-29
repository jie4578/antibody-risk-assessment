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
    assert "自行重新计算" in P
    assert "只能引用 scan_antibody / risk_score" in P


def test_prompt_forbids_second_scoring_system():
    assert "Severity × Likelihood" in P
    assert "1-25" in P and "0-10" in P
    assert "第二套评分体系" in P


def test_prompt_requires_tool_score_priority():
    assert "只能引用" in P and "实际返回的评分" in P
    assert "无工具评分" in P


def test_prompt_raw_1based_position():
    assert "原始序列 1-based position" in P


def test_prompt_no_imgt_kabat_guess():
    for key in ("IMGT", "Kabat", "Chothia", "AHo"):
        assert key in P


def test_prompt_no_antibody_identity_guess():
    assert "不得仅凭 VH/VL 序列" in P
    assert "抗体药物身份" in P


def test_prompt_heuristic_must_be_labeled():
    assert "heuristic / 启发式 / 未经实验验证" in P
    assert "不得把 heuristic 写成" in P
    assert "已确认风险" in P  # 作为"禁止写成"的对象出现


def test_prompt_literature_as_general_evidence():
    assert "一般性文献证据" in P
    assert "不得写成" in P and "文献证明该序列" in P


def test_prompt_no_fabricated_pmid_doi():
    assert "PMID" in P and "DOI" in P
    assert "严禁根据模型记忆补充" in P
    assert "当前可用文献证据不足。" in P


def test_prompt_no_fabricated_experimental_data():
    for key in ("不得编造实验结果", "氧化率", "降解百分比", "KD", "Tm", "半衰期", "LC-MS/MS"):
        assert key in P
    assert "下一步验证建议" in P


def test_prompt_distinguishes_four_information_types():
    for key in ("工具计算结果", "文献证据", "Agent 推断", "下一步验证建议"):
        assert key in P


def test_prompt_evidence_limitations_section():
    assert "证据局限性与风险声明" in P


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
