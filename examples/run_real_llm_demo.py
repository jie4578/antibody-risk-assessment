# examples/run_real_llm_demo.py
# 真实 LLM 端到端演示：Agent(函数调用) + 多智能体 + LangChain agent。
#
# 前置：在仓库根目录创建 .env 并填入 DEEPSEEK_API_KEY（参考 .env.example / docs/REAL_LLM_SETUP.md）。
# 运行：
#   python examples/run_real_llm_demo.py
# 未配置 key 时脚本给出指引并退出（不报错）。

import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

SEQ = (
    "EVQLVESGGGLVQPGGSLRLSCAASGFNIKDTYIHWVRQAPGKGLEWVARIYPTNGYTRYADSVKG"
    "RFTISADTSKNTAYLQMNSLRAEDTAVYYCSRWGGDGFYAMDYWGQGTLVTVSS"
)


def _require_key() -> None:
    from config import get_env

    if not get_env("DEEPSEEK_API_KEY"):
        print("未检测到 DEEPSEEK_API_KEY。")
        print("步骤: copy .env.example .env → 填入 key → 重试(详见 docs/REAL_LLM_SETUP.md)")
        sys.exit(0)


def demo_agent() -> None:
    """1) 真实 LLM + 函数调用：Agent 回答知识问题。"""
    from agent import Agent

    print("\n===== 1/3 Agent(真实 DeepSeek 函数调用) =====")
    agent = Agent(backend="deepseek")
    r = agent.run("什么是脱酰胺化？为什么需要关注？")
    for s in r["steps"]:
        print(f"  -> 调用工具 [{s['tool']}]")
    print("\n回答:\n" + r["answer"])


def demo_orchestrator() -> None:
    """2) 真实 LLM 多智能体编排。"""
    from agent import Orchestrator

    print("\n===== 2/3 Orchestrator(真实 LLM 多智能体) =====")
    orch = Orchestrator(lead_backend="deepseek", worker_backend="deepseek")
    res = orch.run(f"评估这条序列的风险，并告诉我脱酰胺化为什么重要：{SEQ}")
    print(f"选择专家: {res['agents']}")
    print("\n汇总回答:\n" + res["answer"][:800])


def demo_langchain() -> None:
    """3) LangChain agent(1.x 走 langgraph)端到端调用工具。"""
    print("\n===== 3/3 LangChain agent(端到端) =====")
    from agent.langchain_adapter import build_langchain_agent

    agent = build_langchain_agent(backend="deepseek")
    question = "什么是脱酰胺化？请检索知识库回答。"
    result = agent.invoke({"messages": [("user", question)]})
    print("问题:", question)
    # langgraph 返回的 messages 最后一跳是 AI 回答
    msgs = result.get("messages", [])
    if msgs:
        print("\n回答:\n" + str(msgs[-1].content)[:800])
    else:
        print("返回:", str(result)[:500])


def main() -> None:
    _require_key()
    demo_agent()
    demo_orchestrator()
    demo_langchain()
    print("\n完成! 真实 LLM + LangChain 端到端跑通。")


if __name__ == "__main__":
    main()
