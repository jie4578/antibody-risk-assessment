# agent/agent.py
# ReAct 工具调用智能体（真迭代循环）：
#   while: LLM 单步决策(step) → 若返回工具调用则执行 → 观察喂回 → 再决策
#          → 直到 LLM 输出 Final Answer 或达到 max_steps。
# 特性：
#   - Thought → Action → Observation → 再决策 的多轮循环
#   - 工具失败 → 反思重试一次（同参数重试，仍失败则把错误观察喂回 LLM）
#   - MockLLM 同样支持单步推进（离线可演示多步迭代）
#   - 默认用 MockLLM 离线运行；backend="deepseek" 时走真实函数调用

from __future__ import annotations

import uuid
from typing import List, Optional

from .llm import LLMBackend, Observation, ReActStep, get_llm
from .memory import ConversationMemory
from .tools import ToolRegistry, default_tools

# 工具返回结果中被视为"失败"的前缀（用于反思重试判定）
_ERROR_PREFIXES = ("工具 ", "错误", "突变失败", "执行异常")


def _is_error_result(text: str) -> bool:
    t = (text or "").strip()
    return any(t.startswith(p) for p in _ERROR_PREFIXES)


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

    def run(self, question: str, *, remember_facts: bool = True) -> dict:
        """真 ReAct 循环：单步决策 → 执行工具 → 观察 → 再决策，直到 Final Answer。"""
        self.memory.add_user(question)
        steps = []
        observations: List[Observation] = []
        answer = ""
        tool_names = {t.name for t in self.tools.list()}

        for step_no in range(self.max_steps):
            decision: ReActStep = self.llm.step(question, observations, self.tools.list())

            # Final Answer → 结束
            if decision.is_final:
                answer = decision.final_answer
                steps.append({"type": "final", "thought": decision.thought, "answer": answer})
                break

            # Action → 执行工具
            call = decision.tool_call
            if call.name not in tool_names:
                observations.append(Observation(call.name, f"未知工具: {call.name}"))
                continue
            tool = self.tools.get(call.name)
            result = tool.run(call.arguments)

            # 工具失败 → 反思重试一次（同参数）
            retried = False
            if _is_error_result(result) and self.retry_on_failure:
                retried_result = tool.run(call.arguments)
                if not _is_error_result(retried_result):
                    result = retried_result
                retried = True

            obs = Observation(call.name, result, call_id=f"call_{uuid.uuid4().hex[:8]}", arguments=call.arguments)
            observations.append(obs)
            self.memory.add_observation(call.name, result)
            steps.append({
                "type": "tool", "tool": call.name, "arguments": call.arguments,
                "result": result, "retried": retried,
            })
            if remember_facts and (result.startswith("风险评分") or result.startswith("ML 预测")):
                self.memory.remember(result[:160])
        else:
            # 达到 max_steps 仍未 Final Answer → 用已有观察生成最终答案
            answer = self.llm.answer(question, observations)
            steps.append({"type": "final", "thought": "max_steps reached", "answer": answer})

        self.memory.add_assistant(answer)
        return {"question": question, "steps": steps, "answer": answer}

    def ask(self, question: str) -> str:
        """便捷：只返回最终答案字符串。"""
        return self.run(question)["answer"]
