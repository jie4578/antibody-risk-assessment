# agent/__init__.py
# LLM 智能体模块：工具调用 (Tool Calling)、记忆 (Memory)、ReAct 推理循环、多智能体编排。
#
# 目标（对应岗位要求 #2、#4）：
#   - 理解并具备 LLM 应用与智能体开发；Agent / Tool Calling / Memory 核心机制；
#   - 多智能体协作与编排（分工、任务分解、协同执行）。
#
# 设计要点：
#   - 可离线：默认 MockLLM（确定性工具规划 + 模板作答），无 key 也能演示完整 Agent 循环；
#   - 可选真实 LLM：OpenAI / DeepSeek 后端是 drop-in（接入 key 即启用真实函数调用）；
#   - 把既有规则引擎 / ML / RAG 封装为"工具"，被 Agent 调用（体现工程成果工具化）。

from .llm import MockLLM, OpenAILLM, DeepSeekLLM, get_llm, ToolCall, Observation
from .tools import Tool, ToolRegistry, default_tools
from .memory import ConversationMemory
from .agent import Agent
from .orchestrator import Orchestrator

__all__ = [
    "MockLLM",
    "OpenAILLM",
    "DeepSeekLLM",
    "get_llm",
    "ToolCall",
    "Observation",
    "Tool",
    "ToolRegistry",
    "default_tools",
    "ConversationMemory",
    "Agent",
    "Orchestrator",
]

__version__ = "0.1.0"
