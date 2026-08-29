# agent/agent.py
# ReAct 工具调用智能体（真迭代循环）：
#   while: LLM 单步决策(step) → 若返回工具调用则执行 → 观察喂回 → 再决策
#          → 直到 LLM 输出 Final Answer 或达到 max_steps。
# 特性：
#   - Thought → Action → Observation → 再决策 的多轮循环
#   - 工具失败 → 反思重试一次（同参数重试，仍失败则把错误观察喂回 LLM）
#   - 工具事实边界：最终回答只允许使用工具实际返回的数据；越权数字/等级 → 提醒重写一次
#   - run_collect()：只收集工具事实，不生成 LLM 报告（供编排器汇总，避免专家报告污染）
#   - MockLLM 同样支持单步推进（离线可演示多步迭代）
#   - 默认用 MockLLM 离线运行；backend="deepseek" 时走真实函数调用

from __future__ import annotations

import re
import uuid
from typing import List, Optional

from .llm import LLMBackend, Observation, ReActStep, get_llm
from .literature_relevance import build_literature_note, build_user_assertion_note
from .memory import ConversationMemory
from .tools import SEQUENCE_TOOLS, ToolRegistry, blocked_sequence_message, default_tools, sequence_source_of

# 工具返回结果中被视为"失败"的前缀（用于反思重试判定）
_ERROR_PREFIXES = ("工具 ", "错误", "突变失败", "执行异常")


def _is_error_result(text: str) -> bool:
    t = (text or "").strip()
    return any(t.startswith(p) for p in _ERROR_PREFIXES)


def _fact_violations(answer: str, observations: List[Observation]) -> List[str]:
    """事实边界检查：回答中出现工具未返回的数字/百分比/风险等级 → 越权。

    tool_facts 只能来自工具真实返回；LLM 不得自行计算/改写/升级。
    """
    tool_text = " ".join(str(o.result) for o in observations)
    bad = []
    for m in re.findall(r"\d+\.\d+|\d+(?:\.\d+)?%", answer or ""):
        if m not in tool_text:
            bad.append(m)
    for lvl in ("Low Risk", "Medium Risk", "High Risk"):
        if lvl in (answer or "") and lvl not in tool_text:
            bad.append(lvl)
    return bad


def enforce_fact_boundary(llm, question: str, observations: List[Observation], answer: str) -> str:
    """工具事实边界守卫：若最终回答包含工具未返回的数据，提醒 LLM 重写一次。"""
    bad = _fact_violations(answer, observations)
    if bad:
        reminder = (
            "你的回答包含了工具未返回的数据（" + "、".join(bad) + "）。"
            "工具是唯一事实来源：只允许使用工具实际返回的评分、风险与数据，"
            "不得自行计算、改写、升级或新增。请基于工具返回结果重新输出最终回答。"
        )
        answer = llm.answer(question + "\n\n" + reminder, observations)
    return answer


# ---------- v9.2：post-hoc 确定性校验（位点声称 + PMID/DOI 引用） ----------

# 位点表达：NG@55-56 / NS@84-85 / DG@102-103 / M@83 / M107 / N55 / D102 / S63
_POSITION_RE = re.compile(r"[A-Z]{1,3}@\d+(?:-\d+)?|\b[A-Z]\d{2,3}\b")
# 工具事实声明词（位点被写成工具结果的表达）
_TOOL_CLAIM_WORDS = (
    "工具检测到", "工具识别", "工具返回", "工具结果显示", "工具检测",
    "rule_based", "检测到", "分析发现", "识别为", "被工具",
)
# 否定/软化词（该行不是工具事实声明）
_NEGATION_WORDS = (
    "未检测到", "工具未返回", "工具未检测", "未识别", "未经工具验证",
    "用户给定", "未确认", "假设", "如果", "可能", "推测",
)
# 风险数据行前缀（"脱酰胺化：…" 等，表示该行把位点列为风险）
_RISK_PREFIXES = ("脱酰胺化", "异构化", "氧化", "N-糖基化", "O-糖基化", "糖基化", "修饰")


def _positions(text: str) -> set:
    """提取文本中的位点起始位置（NG@55-56 → 55；M107 → 107）。"""
    out = set()
    for m in _POSITION_RE.findall(str(text or "")):
        d = re.search(r"@?(\d+)", m)
        if d:
            out.add(int(d.group(1)))
    return out


def validate_position_claims(answer: str, question: str, observations: List[Observation]) -> List[str]:
    """post-hoc 位点声称校验：把"工具未返回/用户给定"的位点写成工具事实 → 违规。

    - 工具实际返回的位点（scan_antibody / mutate_scan 结果中出现）：允许"工具检测到"。
    - 用户问题给定位点、工具未返回：必须"用户给定/未经工具验证"，否则违规。
    - 工具与用户都未给出的位点出现在回答中：视为编造位点，违规。
    """
    tool_text = " ".join(
        str(o.result) for o in observations or []
        if getattr(o, "tool", None) in ("scan_antibody", "mutate_scan", "risk_score")
    )
    tool_pos = _positions(tool_text)
    user_pos = _positions(str(question or ""))
    violations = []
    for line in (answer or "").splitlines():
        line_pos = _positions(line)
        if not line_pos:
            continue
        negated = any(w in line for w in _NEGATION_WORDS)
        claimed = any(w in line for w in _TOOL_CLAIM_WORDS) or line.startswith(_RISK_PREFIXES)
        for p in line_pos:
            if p in tool_pos:
                continue  # 工具确实返回该位置 → 允许
            if p in user_pos:
                if claimed and not negated:
                    violations.append(f"位置 {p}:用户给定位点被写成工具事实（行:{line[:50]}）")
                continue
            if claimed and not negated:
                violations.append(f"位置 {p}:工具未返回的位点被写成工具事实（行:{line[:50]}）")
    return violations


_PMID_RE = re.compile(r"PMID\s*[:：]?\s*(\d{5,9})", re.IGNORECASE)
_DOI_RE = re.compile(r"DOI\s*[:：]?\s*([^\s,，;；)）]+)", re.IGNORECASE)


def _literature_facts(question: str, observations: List[Observation]):
    """收集 literature_search 实际返回的 pmid/doi → relevance；以及是否调用过检索。"""
    from .literature_relevance import classify_literature_relevance

    pmid_rel, doi_rel = {}, {}
    called = False
    for obs in observations or []:
        if getattr(obs, "tool", None) != "literature_search":
            continue
        called = True
        if str(obs.result).strip()[:20].startswith(("未检索到", "错误", "检索失败")):
            continue
        for a in classify_literature_relevance(question, obs.result):
            if a.get("pmid"):
                pmid_rel[a["pmid"]] = a["relevance"]
            if a.get("doi"):
                doi_rel[a["doi"]] = a["relevance"]
    return pmid_rel, doi_rel, called


def validate_literature_citations(answer: str, question: str, observations: List[Observation]) -> List[str]:
    """post-hoc 文献引用校验：PMID/DOI 必须来自 literature_search 且 relevance != irrelevant。"""
    pmid_rel, doi_rel, called = _literature_facts(question, observations)
    violations = []
    for m in _PMID_RE.finditer(answer or ""):
        pmid = m.group(1)
        if not called or pmid not in pmid_rel:
            violations.append(f"PMID {pmid}:不在 literature_search 实际返回中")
        elif pmid_rel[pmid] == "irrelevant":
            violations.append(f"PMID {pmid}:irrelevant 文献被引用")
    for m in _DOI_RE.finditer(answer or ""):
        doi = m.group(1).rstrip(".")
        if not called or doi not in doi_rel:
            violations.append(f"DOI {doi}:不在 literature_search 实际返回中")
        elif doi_rel[doi] == "irrelevant":
            violations.append(f"DOI {doi}:irrelevant 文献被引用")
    return violations


def _has_user_sequence(question: str, observations: List[Observation]) -> bool:
    """本轮是否存在来自用户问题的合法序列输入（scan/mutate 实际执行）。"""
    q = str(question or "").upper()
    for o in observations or []:
        if getattr(o, "tool", None) not in SEQUENCE_TOOLS:
            continue
        if getattr(o, "sequence_source", "") == "user_provided":
            return True
        seq = (getattr(o, "arguments", None) or {}).get("sequence", "")
        if seq and str(seq).strip().upper() in q:
            return True
    return False


def validate_no_fake_sequence_claims(answer: str, has_user_sequence: bool) -> List[str]:
    """无合法用户序列时，回答中出现序列长度/工具评分/工具事实声明/风险位点数据 → 违规。

    纯知识库问答（如"为什么 NG 容易脱酰胺"）不含"序列长度: N aa / 风险评分: 数字"等模式，不误伤。
    """
    if has_user_sequence:
        return []
    bad = []
    t = answer or ""
    if re.search(r"序列长度\s*[:：]?\s*\d+\s*aa", t):
        bad.append("序列长度(无用户序列)")
    if re.search(r"风险评分\s*[:：]?\s*\d", t):
        bad.append("风险评分(无用户序列)")
    if re.search(r"工具检测到|工具识别|工具返回|rule_based", t):
        bad.append("工具事实声明(无用户序列)")
    if re.search(r"(?m)^\s*(脱酰胺化|异构化|氧化|N-糖基化|O-糖基化)[：:]\s*[A-Z]", t):
        bad.append("风险位点数据(无用户序列)")
    return bad


def enforce_claim_boundaries(
    llm, question: str, observations: List[Observation], answer: str,
    rewrite_facts: Optional[List[Observation]] = None,
) -> str:
    """post-hoc 边界守卫：位点声称 + PMID/DOI 引用 + 无用户序列伪造声明；违规 → 提醒重写一次。"""
    bad = validate_position_claims(answer, question, observations)
    bad += validate_literature_citations(answer, question, observations)
    bad += validate_no_fake_sequence_claims(answer, _has_user_sequence(question, observations))
    if bad:
        reminder = (
            "你的回答存在事实边界问题:(" + "; ".join(bad[:6]) + ")。"
            "工具是唯一事实来源:工具未返回的位点不得写成「工具检测到/rule_based/风险位点」;"
            "用户给定位点必须标注「用户给定/未经工具验证」;"
            "PMID/DOI 只能来自 literature_search 实际返回，irrelevant 文献不得引用;"
            "本轮没有合法的用户抗体序列时，禁止输出任何基于序列扫描产生的序列长度、风险位点或工具评分，"
            "请明确说明缺少序列。请基于工具返回结果重写最终回答。"
        )
        answer = llm.answer(question + "\n\n" + reminder, rewrite_facts if rewrite_facts is not None else observations)
    return answer


class Agent:
    """
    工具调用智能体（真 ReAct 迭代循环）。

    参数:
        backend:   'mock' | 'openai' | 'deepseek'，或一个 LLMBackend 实例。
        tools:     ToolRegistry；默认 default_tools()。
        memory:    ConversationMemory；默认新建（可跨轮共享）。
        max_steps: ReAct 循环最大步数（含工具调用与最终答案步）。
        retry_on_failure: 工具失败时是否反思重试一次（默认 True）。
    """

    def __init__(
        self,
        backend="mock",
        tools: Optional[ToolRegistry] = None,
        memory: Optional[ConversationMemory] = None,
        max_steps: int = 6,
        retry_on_failure: bool = True,
    ):
        self.llm: LLMBackend = get_llm(backend) if isinstance(backend, str) else backend
        self.tools = tools if tools is not None else default_tools()
        self.memory = memory if memory is not None else ConversationMemory()
        self.max_steps = max_steps
        self.retry_on_failure = retry_on_failure

    def plan(self, question: str) -> List:
        """返回该问题下 LLM 规划的工具调用列表（供外部预览，非执行主路径）。"""
        return self.llm.plan(question, self.tools.list())

    def _execute_tool_loop(self, question: str, max_steps: Optional[int] = None):
        """ReAct 工具循环：逐步执行 LLM 选择的工具并收集 Observation。

        返回 (steps, observations, final_answer)。
        final_answer 为 None 表示循环被 max_steps 截断（需调用 llm.answer 兜底生成回答）。
        """
        steps = []
        observations: List[Observation] = []
        tool_names = {t.name for t in self.tools.list()}
        final_answer = None
        limit = max_steps if max_steps is not None else self.max_steps

        for _ in range(limit):
            decision: ReActStep = self.llm.step(question, observations, self.tools.list())

            # Final Answer → 结束
            if decision.is_final:
                final_answer = decision.final_answer
                steps.append({"type": "final", "thought": decision.thought, "answer": final_answer})
                break

            # Action → 执行工具
            call = decision.tool_call
            if call.name not in tool_names:
                observations.append(Observation(call.name, f"未知工具: {call.name}"))
                continue
            tool = self.tools.get(call.name)
            # v9.3：工具输入来源边界——scan/mutate 的序列必须来自用户问题，禁止 Agent 自行构造
            if call.name in SEQUENCE_TOOLS:
                seq = (call.arguments or {}).get("sequence", "")
                src = sequence_source_of(question, seq)
                if src in ("unavailable", "invalid"):
                    result = blocked_sequence_message(call.name, src)
                    obs = Observation(call.name, result, call_id=f"call_{uuid.uuid4().hex[:8]}",
                                      arguments=call.arguments, sequence_source=src)
                    observations.append(obs)
                    steps.append({"type": "tool", "tool": call.name, "arguments": call.arguments,
                                  "result": result, "retried": False, "blocked": True})
                    continue
                src = "user_provided"
            else:
                src = ""
            result = tool.run(call.arguments)

            # 工具失败 → 反思重试一次（同参数）
            retried = False
            if _is_error_result(result) and self.retry_on_failure:
                retried_result = tool.run(call.arguments)
                if not _is_error_result(retried_result):
                    result = retried_result
                retried = True

            obs = Observation(call.name, result, call_id=f"call_{uuid.uuid4().hex[:8]}",
                              arguments=call.arguments, sequence_source=src)
            observations.append(obs)
            steps.append({
                "type": "tool", "tool": call.name, "arguments": call.arguments,
                "result": result, "retried": retried,
            })
        else:
            # 达到 max_steps 仍未 Final Answer → 兜底标记（回答由 run() 生成）
            steps.append({"type": "final", "thought": "max_steps reached", "answer": ""})

        return steps, observations, final_answer

    def run(self, question: str, *, remember_facts: bool = True) -> dict:
        """真 ReAct 循环 + 工具事实边界守卫：最终回答只基于工具返回结果。"""
        self.memory.add_user(question)
        steps, observations, final_answer = self._execute_tool_loop(question)

        for obs in observations:
            self.memory.add_observation(obs.tool, obs.result)
            if remember_facts and (obs.result.startswith("风险评分") or obs.result.startswith("ML 预测")):
                self.memory.remember(obs.result[:160])

        # 事实来源注记（v7/v8）：文献相关性 + 用户给定位点(未经工具确认) → 喂给最终回答
        facts = list(observations)
        lit_note = build_literature_note(question, observations)
        if lit_note:
            facts.append(Observation("literature_relevance", lit_note))
        user_note = build_user_assertion_note(question, observations)
        if user_note:
            facts.append(Observation("fact_source", user_note))
        if len(facts) > len(observations):
            answer = self.llm.answer(question, facts)
        else:
            answer = final_answer if final_answer is not None else self.llm.answer(question, observations)
        answer = enforce_fact_boundary(self.llm, question, observations, answer)
        # v9.2：post-hoc 位点声称 + PMID/DOI 引用校验（重写时使用含注记的 facts）
        answer = enforce_claim_boundaries(self.llm, question, observations, answer, rewrite_facts=facts)

        if steps and steps[-1]["type"] == "final":
            steps[-1]["answer"] = answer
        else:
            steps.append({"type": "final", "thought": "final", "answer": answer})

        self.memory.add_assistant(answer)
        return {"question": question, "steps": steps, "answer": answer}

    def run_collect(self, question: str) -> dict:
        """只执行工具调用并收集事实(observations)，不生成 LLM 报告（供编排器汇总）。"""
        steps, observations, _ = self._execute_tool_loop(question)
        return {"steps": steps, "observations": observations}

    def ask(self, question: str) -> str:
        """便捷：只返回最终答案字符串。"""
        return self.run(question)["answer"]
