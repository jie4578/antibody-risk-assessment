# agent/agent.py
# ReAct 工具调用智能体：plan → act(调用工具) → observe → answer。
# 演示 Agent / Tool Calling / Memory 的核心循环；默认用 MockLLM 离线运行。

from __future__ import annotations

from typing import List, Optional

from .llm import LLMBackend, Observation, get_llm
from .memory import ConversationMemory
from .tools import ToolRegistry, default_tools


class Agent:
    """
    工具调用智能体。

    参数:
        backend:   'mock' | 'openai' | 'deepseek'，或一个 LLMBackend 实例。
        tools:     ToolRegistry；默认 default_tools()。
        memory:    ConversationMemory；默认新建（可跨轮共享）。
        max_steps: 单次最多调用的工具数。
    """

    def __init__(
        self,
        backend="mock",
        tools: Optional[ToolRegistry] = None,
        memory: Optional[ConversationMemory] = None,
        max_steps: int = 5,
    ):
        self.llm: LLMBackend = get_llm(backend) if isinstance(backend, str) else backend
        self.tools = tools if tools is not None else default_tools()
        self.memory = memory if memory is not None else ConversationMemory()
        self.max_steps = max_steps

    def plan(self, question: str) -> List:
        """返回该问题下要调用的工具调用列表（供外部预览）。"""
        return self.llm.plan(question, self.tools.list())

    def run(self, question: str, *, remember_facts: bool = True) -> dict:
        """执行一次问答：规划 → 依次调用工具 → 观察 → 生成最终答案。"""
        self.memory.add_user(question)
        steps = []
        observations: List[Observation] = []

        for call in self.plan(question)[: self.max_steps]:
            tool = self.tools.get(call.name)
            result = tool.run(call.arguments)
            obs = Observation(call.name, result)
            observations.append(obs)
            self.memory.add_observation(call.name, result)
            steps.append({"tool": call.name, "arguments": call.arguments, "result": result})
            if remember_facts and (result.startswith("风险评分") or result.startswith("ML 预测")):
                self.memory.remember(result[:160])

        answer = self.llm.answer(question, observations)
        self.memory.add_assistant(answer)
        return {"question": question, "steps": steps, "answer": answer}

    def ask(self, question: str) -> str:
        """便捷：只返回最终答案字符串。"""
        return self.run(question)["answer"]
