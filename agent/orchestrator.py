# agent/orchestrator.py
# 多智能体编排（v5）：
#   - 主管(lead)先分解任务，确定哪些专家参与；
#   - 专家智能体只负责"选择并执行工具、收集结构化事实"(run_collect)，不生成长篇报告；
#   - 最终回答由 Final Agent 基于全部工具事实生成一次，并经过工具事实边界守卫。
# 这样避免"中间 Agent 长篇报告污染最终回答"与"工具事实被 LLM 二次改写"。

from __future__ import annotations

from typing import Dict, List

from .agent import Agent, enforce_claim_boundaries, enforce_fact_boundary
from .literature_relevance import build_literature_note, build_user_assertion_note
from .llm import Observation, get_llm
from .tools import ToolRegistry, default_tools


def _registry_with(*names: str) -> ToolRegistry:
    """从默认工具集中挑出指定工具，构建一个子工具注册表。"""
    base = default_tools()
    reg = ToolRegistry()
    for n in names:
        reg.register(base.get(n))
    return reg


# 专家智能体 → 其负责的工具（literature_search 归入 knowledge_agent）
_SPECIALISTS: Dict[str, List[str]] = {
    "scan_agent": ["scan_antibody", "mutate_scan", "risk_score"],
    "ml_agent": ["predict_risk"],
    "knowledge_agent": ["rag_search", "literature_search"],
}


class Orchestrator:
    """主管/编排器：分解任务 → 专家收集工具事实 → Final Agent 一次性生成回答。"""

    def __init__(self, lead_backend: str = "mock", worker_backend: str = "mock"):
        self.lead_backend = lead_backend
        self.worker_backend = worker_backend
        self._lead = get_llm(lead_backend)

    def _worker(self, agent_name: str) -> Agent:
        tools = _registry_with(*_SPECIALISTS[agent_name])
        return Agent(backend=self.worker_backend, tools=tools)

    def decompose(self, question: str) -> List[str]:
        """主管(lead)依据问题决定调用哪些专家智能体。"""
        calls = self._lead.plan(question, default_tools().list())
        tool_names = {c.name for c in calls}
        active = []
        for agent_name, tool_list in _SPECIALISTS.items():
            if any(t in tool_names for t in _SPECIALISTS[agent_name]):
                active.append(agent_name)
        return active or ["knowledge_agent"]

    def run(self, question: str) -> Dict[str, object]:
        """执行编排：收集全部工具事实 → Final Agent 生成一次最终回答。"""
        active = self.decompose(question)

        results = []
        all_observations = []
        for agent_name in active:
            worker = self._worker(agent_name)
            facts = worker.run_collect(question)  # 只收集工具事实，不生成报告
            results.append({"agent": agent_name, "steps": facts["steps"], "answer": ""})
            all_observations.extend(facts["observations"])

        # 最终回答：只用工具事实生成一次（事实边界守卫兜底，防止越权数据）
        final_llm = get_llm(self.worker_backend)
        # v7/v8：文献相关性注记 + 用户给定位点注记（未经工具确认的位点不得冒充工具事实）
        facts_for_answer = list(all_observations)
        lit_note = build_literature_note(question, all_observations)
        if lit_note:
            facts_for_answer.append(Observation("literature_relevance", lit_note))
        user_note = build_user_assertion_note(question, all_observations)
        if user_note:
            facts_for_answer.append(Observation("fact_source", user_note))
        answer = final_llm.answer(question, facts_for_answer)
        answer = enforce_fact_boundary(final_llm, question, all_observations, answer)
        # v9.2：post-hoc 位点声称 + PMID/DOI 引用校验
        answer = enforce_claim_boundaries(final_llm, question, all_observations, answer, rewrite_facts=facts_for_answer)

        return {
            "question": question,
            "agents": active,
            "results": results,
            "tool_facts": [{"tool": o.tool, "result": o.result} for o in all_observations],
            "answer": answer,
        }
