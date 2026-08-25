# agent/llm.py
# LLM 后端抽象：统一的 plan / answer 接口，让 Agent 循环与具体模型解耦。
#
#  - MockLLM:   离线、确定性。用关键词意图匹配"规划"工具调用，用模板生成最终答案，
#               用于演示完整 Agent 循环（无需 API key / 网络）。
#  - OpenAILLM / DeepSeekLLM: 可选的真实函数调用后端（接入 key 即启用，drop-in）。

from __future__ import annotations

import os
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional, Protocol

# 常用抗体/风险场景关键词 → 工具意图
_KB_TOOL = "rag_search"
_SCAN_TOOL = "scan_antibody"
_MUT_TOOL = "mutate_scan"
_SCORE_TOOL = "risk_score"
_PREDICT_TOOL = "predict_risk"

# 用于离线规划的关键词
_KEYWORDS = {
    _SCAN_TOOL: ["扫描", "分析", "评估序列", "这条序列", "基序", "scan", "analyze", "评估抗体"],
    _MUT_TOOL: ["突变", "mutat", "n55q", "改造"],
    _SCORE_TOOL: ["打分", "风险分", "分数", "score"],
    _PREDICT_TOOL: ["预测", "predict", "ml", "模型"],
    _KB_TOOL: ["为什么", "是什么", "哪里", "什么是", "原理", "风险", "知识", "检索", "查询", "what", "why", "how"],
}


@dataclass
class ToolCall:
    """一次工具调用请求。"""
    name: str
    arguments: Dict[str, Any] = field(default_factory=dict)


@dataclass
class Observation:
    """一次工具执行的结果。"""
    tool: str
    result: str


class LLMBackend(Protocol):
    """LLM 后端协议：规划要调用的工具 + 生成最终答案。"""

    def plan(self, question: str, tools: List["Tool"]) -> List[ToolCall]: ...

    def answer(self, question: str, observations: List[Observation]) -> str: ...


def _looks_like_sequence(text: str) -> Optional[str]:
    """从文本中抽出一段抗体序列（连续的 20 种大写氨基酸）。"""
    import re

    m = re.search(r"([ACDEFGHIKLMNPQRSTVWY]{40,})", (text or "").upper())
    return m.group(1) if m else None


class MockLLM:
    """离线 Mock：基于关键词把问题映射到工具调用，并生成模板式最终答案。"""

    def plan(self, question: str, tools: List["Tool"]) -> List[ToolCall]:
        calls: List[ToolCall] = []
        tool_names = {t.name for t in tools}
        q = (question or "").lower()
        seq = _looks_like_sequence(question)

        # 1) 只有文本里确实含抗体序列时，才触发序列类工具（扫描/突变/打分/ML预测）
        if seq and _SCAN_TOOL in tool_names:
            calls.append(ToolCall(_SCAN_TOOL, {"sequence": seq}))
        if seq and _MUT_TOOL in tool_names and any(k in q for k in _KEYWORDS[_MUT_TOOL]):
            calls.append(ToolCall(_MUT_TOOL, {"sequence": seq, "mutation": _guess_mutation(question)}))
        if seq and _SCORE_TOOL in tool_names and any(k in q for k in _KEYWORDS[_SCORE_TOOL]):
            calls.append(ToolCall(_SCORE_TOOL, {"sequence": seq}))
        if seq and _PREDICT_TOOL in tool_names and any(k in q for k in _KEYWORDS[_PREDICT_TOOL]):
            calls.append(ToolCall(_PREDICT_TOOL, {"sequence": seq}))

        # 2) 知识类问题 → RAG
        if _KB_TOOL in tool_names and any(k in q for k in _KEYWORDS[_KB_TOOL]):
            calls.append(ToolCall(_KB_TOOL, {"question": question}))

        # 去重且按工具名稳定排序
        seen, out = set(), []
        for c in calls:
            if c.name not in seen:
                seen.add(c.name)
                out.append(c)
        return out[:3]

    def answer(self, question: str, observations: List[Observation]) -> str:
        if not observations:
            return "我没有找到合适的工具来回答这个问题。可以换成「扫描某条序列」或「什么是脱酰胺化」之类的提问。"
        lines = [f"根据我的工具分析，回答你的问题「{question}」："]
        for obs in observations:
            if obs.tool == _KB_TOOL:
                lines.append(f"[知识检索] {obs.result[:400]}")
            else:
                lines.append(f"[{obs.tool} 结果] {obs.result[:300]}")
        lines.append("（以上为基于离线规则/Mock 的演示性回复；接入真实 LLM 后由模型生成更自然的回答。）")
        return "\n".join(lines)

    def complete(self, prompt: str) -> str:
        """离线模式：不调用真实 LLM，仅提示当前为 mock（用于 RAG 生成回答等场景）。"""
        return "（离线模式：未配置 API key，仅展示检索上下文与 prompt。在 .env 配置 DEEPSEEK_API_KEY 后此处会生成自然回答。）"


def _guess_mutation(question: str) -> str:
    """从提问中猜测突变（如 N55Q）；找不到则给示例。"""
    import re

    m = re.search(r"\b([A-Za-z])(\d+)([A-Za-z])\b", question or "")
    return m.group(0).upper() if m else "N55Q"


class _OpenAICompatBackend:
    """可选：基于 OpenAI 兼容接口（OpenAI / DeepSeek 等）的真实函数调用后端。"""

    def __init__(self, model: str, api_key_env: str, base_url: str):
        try:
            from openai import OpenAI
        except Exception as e:  # pragma: no cover
            raise ImportError("需要安装 openai 包才能使用真实 LLM 后端") from e
        from config import get_env

        key = get_env(api_key_env)
        if not key:
            raise RuntimeError(
                f"缺少 {api_key_env}。请在仓库根目录创建 .env（参考 .env.example），"
                f"写入 {api_key_env}=<your-key> 后重试。"
            )
        self._client = OpenAI(api_key=key, base_url=base_url)
        self._model = model

    def plan(self, question: str, tools: List["Tool"]) -> List[ToolCall]:
        schemas = [t.to_schema() for t in tools]
        resp = self._client.chat.completions.create(
            model=self._model,
            messages=[{"role": "user", "content": question}],
            tools=schemas,
            tool_choice="auto",
        )
        calls: List[ToolCall] = []
        msg = resp.choices[0].message
        for tc in (msg.tool_calls or []):
            import json

            args = json.loads(tc.function.arguments or "{}")
            calls.append(ToolCall(tc.function.name, args))
        return calls

    def answer(self, question: str, observations: List[Observation]) -> str:
        context = "\n".join(f"[{o.tool}] {o.result[:800]}" for o in observations)
        resp = self._client.chat.completions.create(
            model=self._model,
            messages=[
                {"role": "system", "content": "你是抗体可开发性专家。请基于工具结果简要回答；资料不足就说明，不要编造。"},
                {"role": "user", "content": question},
            ],
        )
        return resp.choices[0].message.content or ""

    def complete(self, prompt: str) -> str:
        """直接用 prompt 生成回答（用于 RAG 等"检索→生成"场景）。"""
        resp = self._client.chat.completions.create(
            model=self._model,
            messages=[
                {"role": "system", "content": "你是抗体可开发性专家。请基于参考资料回答用户问题；资料不足就明确说明，不要编造。"},
                {"role": "user", "content": prompt},
            ],
        )
        return resp.choices[0].message.content or ""


class OpenAILLM(_OpenAICompatBackend):
    def __init__(self, model: str = "gpt-4o-mini"):
        super().__init__(model, "OPENAI_API_KEY", "https://api.openai.com/v1")


class DeepSeekLLM(_OpenAICompatBackend):
    def __init__(self, model: str = "deepseek-chat"):
        super().__init__(model, "DEEPSEEK_API_KEY", "https://api.deepseek.com")


def get_llm(name: str = "mock", **kwargs):
    """LLM 工厂。name ∈ {mock, openai, deepseek}。"""
    name = (name or "mock").lower()
    if name == "mock":
        return MockLLM()
    if name in ("openai", "gpt"):
        return OpenAILLM(**kwargs)
    if name == "deepseek":
        return DeepSeekLLM(**kwargs)
    raise ValueError(f"未知 LLM: {name}（可选 mock / openai / deepseek）")


def generate_answer(question: str, context: str, backend: str = "auto") -> str:
    """基于检索上下文，用 LLM 生成一段自然回答（RAG 的"生成"环节）。

    backend: 'auto' 按 .env 自动选（deepseek / openai / mock）；也可显式指定。
    """
    if backend == "auto":
        from config import auto_llm_backend

        backend = auto_llm_backend()
    llm = get_llm(backend)
    prompt = (
        "你是一个抗体可开发性领域专家。请基于以下参考资料回答用户问题；"
        "参考资料不足就明确说明，不要编造。\n\n"
        f"【参考资料】\n{context.strip() or '（无）'}\n\n"
        f"【用户问题】\n{question}"
    )
    return llm.complete(prompt)
