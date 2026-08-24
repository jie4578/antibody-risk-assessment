# agent/langchain_adapter.py
# LangChain 集成适配器（可选，需安装 langchain）。
#
# 目标：把本项目 default_tools() 打包成 LangChain 工具，并装配成 LangChain Agent，
#   从而复用 LangChain 生态；同时保留本项目自研的离线 MockLLM 方案（无 key 可跑）。
#
# 兼容两代 langchain API：
#   - langchain 0.x：create_react_agent + AgentExecutor
#   - langchain 1.x：langgraph.prebuilt.create_react_agent（编译后的图）
#
# 使用（安装 langchain 后）：
#   from agent.langchain_adapter import build_langchain_agent, wrap_tools
#   agent = build_langchain_agent()               # 需 OPENAI_API_KEY 或传入 llm
#   agent.invoke({"messages": [("user", "什么是脱酰胺化？")]})

from __future__ import annotations

from typing import List, Optional


def _require_langchain():
    """导入 langchain 相关组件，兼容 0.x(AgentExecutor) 与 1.x(LangGraph) 两代 API。"""
    try:
        from langchain_core.prompts import PromptTemplate
        from langchain_core.tools import StructuredTool
    except Exception as e:  # pragma: no cover
        raise ImportError(
            "需要安装 langchain 才能使用该适配器：pip install langchain langchain-openai"
            "（或用 pip install '.[agent]'）"
        ) from e

    executor_cls = None
    react_factory = None
    try:  # langchain 0.x：AgentExecutor + create_react_agent
        from langchain.agents import AgentExecutor, create_react_agent

        executor_cls, react_factory = AgentExecutor, create_react_agent
    except Exception:
        pass
    if react_factory is None:
        try:  # langchain 1.x：LangGraph 的 create_react_agent（随 langchain 依赖自动安装）
            from langgraph.prebuilt import create_react_agent

            react_factory = create_react_agent
        except Exception as e:  # pragma: no cover
            raise ImportError("未找到 create_react_agent（需要 langchain>=0.1 或 langgraph）") from e
    return executor_cls, react_factory, PromptTemplate, StructuredTool


def _make_args_schema(tool):
    """根据工具的 parameters 构造 pydantic args schema，让 LangChain 能正确解析参数。"""
    from pydantic import Field, create_model

    fields = {}
    for p in tool.parameters:
        name = p["name"]
        desc = p.get("description", "")
        if p.get("required"):
            fields[name] = (str, Field(description=desc))
        else:
            fields[name] = (Optional[str], Field(default=None, description=desc))
    return create_model(f"{tool.name}Args", **fields)


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
                args_schema=_make_args_schema(tool),
            )
        )
    return out


def build_langchain_agent(llm=None):
    """组装 LangChain Agent。

    参数:
        llm: 一个 LangChain 兼容的 chat model；为空时尝试用 langchain-openai(ChatOpenAI) 连接 OPENAI_API_KEY。
    返回:
        langchain 0.x → AgentExecutor；langchain 1.x → 编译后的 LangGraph ReAct agent。
    """
    executor_cls, react_factory, PromptTemplate, _ = _require_langchain()

    if llm is None:
        import os

        from langchain_openai import ChatOpenAI

        if not os.environ.get("OPENAI_API_KEY"):
            raise RuntimeError("缺少 OPENAI_API_KEY 无法构建 LangChain Agent（可传入自定义 llm）")
        llm = ChatOpenAI(model="gpt-4o-mini", temperature=0)

    tools = wrap_tools()
    if executor_cls is not None:  # langchain 0.x
        prompt = PromptTemplate.from_template(
            "你是抗体可开发性专家。请根据问题调用合适工具，并基于工具结果回答。\n"
            "问题: {input}\n{agent_scratchpad}"
        )
        agent = react_factory(llm, tools, prompt)
        return executor_cls(agent=agent, tools=tools, verbose=True)
    # langchain 1.x (LangGraph)
    return react_factory(llm, tools)
