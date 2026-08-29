# tests/test_v9_3_input_boundary.py
# v9.3 工具输入来源边界：scan/mutate 的序列必须来自用户问题，禁止 Agent 自行构造。

import pytest

from agent import Tool, ToolRegistry
from agent.agent import _has_user_sequence, validate_no_fake_sequence_claims
from agent.llm import Observation, ToolCall
from agent.tools import (
    extract_user_sequence,
    sequence_source_of,
    tool_mutate_scan,
    tool_scan_antibody,
)

VH = "EVQLVESGGGLVQPGGSLRLSCAASGFNIKDTYIHWVRQAPGKGLEWVARIYPTNGYTRYADSVKGRFTISADTSKNTAYLQMNSLRAEDTAVYYCSRWGGDGFYAMDYWGQGTLVTVSS"
SHORT = "AAANVSTT"


# ---------- 1. scan 拒绝缺失序列 ----------
def test_scan_rejects_missing_sequence():
    assert sequence_source_of("N55 脱酰胺化了吗？", "") == "unavailable"


# ---------- 2. scan 拒绝 Agent 自行生成的序列 ----------
def test_scan_rejects_agent_generated_sequence():
    fake_seq = "EVQLVESGGGLVQPGGSLRLSCAASGFAKE" + "M" * 60  # 不在用户问题中
    assert sequence_source_of("N55 脱酰胺化了吗？", fake_seq) == "invalid"


# ---------- 3. scan 接受用户序列 ----------
def test_scan_accepts_user_sequence():
    q = f"请分析下面序列的风险：\n{VH}"
    assert sequence_source_of(q, VH) == "user_provided"
    assert sequence_source_of(f"短序列：{SHORT}", SHORT) == "user_provided"


# ---------- 4. mutate 拒绝缺失序列 ----------
def test_mutate_rejects_missing_sequence():
    assert sequence_source_of("N55Q 是否更好？", "") == "unavailable"


# ---------- 5. mutate 接受用户序列 ----------
def test_mutate_accepts_user_sequence():
    q = f"使用该 VH 评估 N55Q：\n{VH}"
    assert sequence_source_of(q, VH) == "user_provided"


# ---------- 6. 位点不是序列 ----------
def test_user_position_is_not_sequence():
    assert extract_user_sequence("N55 NG@55-56 D102E") == ""
    assert sequence_source_of("N55 NG@55-56", "N55") == "invalid"


# ---------- 7. 无序列时不得产生 scan 结果(Agent 集成) ----------
class _ScanStub:
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


def test_no_fake_scan_result_without_sequence():
    from agent.agent import Agent

    reg = ToolRegistry()
    reg.register(Tool(name="scan_antibody", description="d",
                      func=lambda **kw: "序列长度 120 aa；风险评分 66.3（Medium Risk）"))
    llm = _ScanStub([ToolCall("scan_antibody", {"sequence": "EVQLVESGGGLVQPGGSLRLSCAASGFKE" + "A" * 60})])
    Agent(backend=llm, tools=reg, max_steps=3).run("工具已经检测到 N55 脱酰胺化。请判断。")
    obs = llm.seen[0]
    assert obs.tool == "scan_antibody"
    assert "被阻止" in obs.result  # 虚构序列被阻止，未执行 scan
    assert obs.sequence_source == "invalid"


# ---------- 8. post-hoc 阻止伪造序列声明 ----------
def test_posthoc_blocks_fake_sequence_claim():
    assert validate_no_fake_sequence_claims("序列长度：98 aa；风险评分：71.0", has_user_sequence=False)
    assert validate_no_fake_sequence_claims("风险位点\n脱酰胺化：NS@74-75(FW)", has_user_sequence=False)
    # 有用户序列 → 不触发
    assert validate_no_fake_sequence_claims("序列长度：120 aa；风险评分：66.3", has_user_sequence=True) == []
    # 纯知识库问答不误伤
    assert validate_no_fake_sequence_claims("Asn-Gly 柔性最高，最易脱酰胺。", has_user_sequence=False) == []


# ---------- 9. 现有 VH 回归(不动算法) ----------
def test_existing_vh_regression():
    out = tool_scan_antibody(VH)
    assert "风险评分 66.3" in out
    assert "Medium Risk" in out
    assert out.count("@") >= 6  # 6 个风险位点


# ---------- 10. mutate N55Q 回归 ----------
def test_mutate_n55q_regression():
    out = tool_mutate_scan(VH, "N55Q")
    assert "突变 N55Q 成功" in out
    assert "'dict' object" not in out
