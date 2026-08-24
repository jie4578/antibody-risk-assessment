# agent/langchain_adapter.py
# LangChain 集成适配器（可选，需安装 langchain）。
#
# 目标（对应岗位要求 #2 "熟悉 LangChain / LlamaIndex 框架的 LLM 应用与智能体开发"）：
#   把本项目 default_tools() 打包成 LangChain 工具，并装配成 LangChain ReAct Agent，
#   从而复用 LangChain 生态；同时保留本项目自研的离线 MockLLM 方案（无 key 可跑）。
#
# 使用（安装 langchain 后）：
#   from agent.langchain_adapter import build_langchain_agent, wrap_tools
#   executor = build_langchain_agent()               # 需 OPENAI_API_KEY 或传入 llm
#   executor.invoke({"input": "什么是脱酰胺化？"})

from __future__ import annotations

from typing import List, Optional


def _require_langchain():
    try:
        from langchain.agents import AgentExecutor, create_react_agent
        from langchain_core.prompts import PromptTemplate
        from langchain_core.tools import StructuredTool

        return AgentExecutor, create_react_agent, PromptTemplate, StructuredTool
    except Exception as e:  # pragma: no cover - 环境未装 langchain 时给出可读提示
        raise ImportError(
            "需要安装 langchain 才能使用该适配器：pip install langchain langchain-openai"
            "（或用 pip install '.[agent]'）"
        ) from e


def wrap_tools() -> List:
    """把 default_tools() 里的工具包装为 LangChain StructuredTool 对象。"""
    _, _, _, StructuredTool = _require_langchain()
    from .tools import default_tools

    registry = default_tools()
    out = []
    for tool in registry.list():
        out.append(
            StructuredTool.from_function(
                func=lambda _t=tool, **kwargs: _t.run(kwargs),
                name=tool.name,
                description=tool.description,
            )
        )
    return out


def build_langchain_agent(llm=None):
    """组装 LangChain ReAct Agent。

    参数:
        llm: 一个 LangChain 兼容的 chat model；为空时尝试用 langchain-openai(ChatOpenAI) 连接 OPENAI_API_KEY。
    返回:
        AgentExecutor。
    """
    AgentExecutor, create_react_agent, PromptTemplate, _ = _require_langchain()

    if llm is None:
        import os

        from langchain_openai import ChatOpenAI

        if not os.environ.get("OPENAI_API_KEY"):
            raise RuntimeError("缺少 OPENAI_API_KEY 无法构建 LangChain Agent（可传入自定义 llm）")
        llm = ChatOpenAI(model="gpt-4o-mini", temperature=0)

    tools = wrap_tools()
    prompt = PromptTemplate.from_template(
        "你是抗体可开发性专家。请根据问题调用合适工具，并基于工具结果回答。\n"
        "问题: {input}\n{agent_scratchpad}"
    )
    agent = create_react_agent(llm, tools, prompt)
    return AgentExecutor(agent=agent, tools=tools, verbose=True)
