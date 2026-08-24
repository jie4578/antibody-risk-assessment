# agent/orchestrator.py
# 多智能体编排：主管(lead)先分解任务，再分发给"专家智能体"协同执行并汇总。
#
# 演示多智能体协作与编排：
#   - 任务分解(dedicated agents：规则扫描 / ML 预测 / 知识检索)
#   - 各司其职 + 共享记忆(shared memory)协同
#   - 结果汇聚成一份综合回答

from __future__ import annotations

from typing import Dict, List, Optional

from .agent import Agent
from .llm import get_llm
from .memory import ConversationMemory
from .tools import ToolRegistry, default_tools


def _registry_with(*names: str) -> ToolRegistry:
    """从默认工具集中挑出指定工具，构建一个子工具注册表。"""
    base = default_tools()
    reg = ToolRegistry()
    for n in names:
        reg.register(base.get(n))
    return reg


# 专家智能体 → 其负责的工具
_SPECIALISTS: Dict[str, List[str]] = {
    "scan_agent": ["scan_antibody", "mutate_scan", "risk_score"],
    "ml_agent": ["predict_risk"],
    "knowledge_agent": ["rag_search"],
}


class Orchestrator:
    """主管/编排器。会把问题分解给相关专家智能体，再汇总。"""

    def __init__(self, lead_backend: str = "mock", worker_backend: str = "mock"):
        self.lead_backend = lead_backend
        self.worker_backend = worker_backend
        self._lead = get_llm(lead_backend)

    def _worker(self, agent_name: str, memory: ConversationMemory) -> Agent:
        tools = _registry_with(*_SPECIALISTS[agent_name])
        return Agent(backend=self.worker_backend, tools=tools, memory=memory)

    def decompose(self, question: str) -> List[str]:
        """主管(lead)依据问题决定调用哪些专家智能体。"""
        calls = self._lead.plan(question, default_tools().list())
        tool_names = {c.name for c in calls}
        active = []
        for agent_name, tool_list in _SPECIALISTS.items():
            if any(t in tool_names for t in _SPECIALISTS[agent_name]):
                active.append(agent_name)
        return active or ["knowledge_agent"]

    def run(self, question: str, *, verbose: bool = True) -> Dict[str, object]:
        memory = ConversationMemory()
        memory.add_user(question)
        active = self.decompose(question)

        results = []
        for agent_name in active:
            worker = self._worker(agent_name, memory)
            r = worker.run(question)
            results.append({"agent": agent_name, "steps": r["steps"], "answer": r["answer"]})
            if verbose:
                memory.add("info", f"[{agent_name} 完成] {r['answer'][:200]}")

        combined = self._aggregate(question, results)
        return {"question": question, "agents": active, "results": results, "answer": combined}

    def _aggregate(self, question: str, results: List[Dict[str, object]]) -> str:
        """把多个专家智能体的结果汇聚成一份综合回答（离线模板式）。"""
        lines = [f"对于「{question}」，我协调了多个专家智能体，汇总如下："]
        for r in results:
            lines.append(f"\n=== {r['agent']} ===")
            lines.append(r["answer"])
        lines.append("\n（以上为多专家协同的离线演示回复；接入真实 LLM 后可生成更连贯的结论。）")
        return "\n".join(lines)
