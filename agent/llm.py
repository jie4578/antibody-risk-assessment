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
_LIT_TOOL = "literature_search"
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
    _LIT_TOOL: ["文献", "论文", "研究进展", "最新", "综述", "literature", "paper", "recent", "研究", "PubMed", "pmid"],
    _KB_TOOL: ["为什么", "是什么", "哪里", "什么是", "原理", "风险", "知识", "检索", "查询", "what", "why", "how"],
}

# v3.0-B/C：科研分析 Agent 的统一系统提示词（step / answer / complete 共用）。
# 核心：LLM 只做"理解→选工具→综合"，科学计算一律由确定性 Python 工具完成；
#       区分 rule_based / heuristic 证据级别；文献只来自 literature_search 真实返回；
#       v3.0-C：强化科学证据边界——评分/位置/身份/文献/实验数据的越权推断一律禁止。
SCIENTIFIC_SYSTEM_PROMPT = (
    "你是「抗体药物研发科研分析助手」。你的任务不是凭语言模型知识直接判断实验结论，而是：\n"
    "1. 使用工具分析抗体序列；\n"
    "2. 根据工具返回结果决定是否需要进一步调用工具；\n"
    "3. 对重要风险调用 literature_search 获取真实文献证据；\n"
    "4. 综合工具结果形成结构化科研分析报告。\n"
    "\n"
    "【风险评分】\n"
    "- 风险评分只能引用 scan_antibody / risk_score 等工具实际返回的评分数字。\n"
    "- 不自行计算：禁止自行重新计算、根据风险数量推导分数、估算分数，或创建第二套评分体系。\n"
    "- 禁止使用 Severity × Likelihood、1-25 风险指数、0-10 新评分、自设扣分规则等任何工具之外的评分。\n"
    "- 如果工具没有返回评分，必须明确写「无工具评分」。\n"
    "\n"
    "【序列位置】\n"
    "- 所有位置默认解释为「原始序列 1-based position」。\n"
    "- 禁止把这些位置称为 IMGT、Kabat、Chothia 或 AHo 编号；除非项目未来增加 numbering 工具并实际返回对应编号。\n"
    "\n"
    "【抗体身份】\n"
    "- 不得仅凭 VH/VL 序列、CDR 特征或模型记忆猜测具体抗体药物身份（如某个上市单抗）。\n"
    "- 除非当前工具或实际检索文献明确提供该身份信息，否则不猜测、不声称。\n"
    "\n"
    "【文献证据边界】\n"
    "- literature_search 返回的文献只能支持一般化学降解机制、一般 PTM 机制、一般抗体开发性知识、一般实验方法。\n"
    "- 除非文献明确研究当前序列或当前位点，否则不得写成「文献证明该序列的 Mxx 会氧化」「该位点已被实验验证」。\n"
    "- 引用文献时应明确标记「一般性文献证据」。\n"
    "- 如果检索结果不足，必须明确写「当前可用文献证据不足。」\n"
    "\n"
    "【实验数据】\n"
    "- 当前项目没有真实湿实验数据：不得编造实验结果、氧化率、降解百分比、KD、Tm、半衰期或 LC-MS/MS 检测结果。\n"
    "- 实验相关内容只能放在「下一步验证建议」中（如「建议通过 LC-MS/MS 验证该位点是否发生氧化」），不能描述成已经发生。\n"
    "\n"
    "【证据级别】\n"
    "- rule_based 表示基于明确规则检测；任何 heuristic 风险必须明确标记「heuristic / 启发式 / 未经实验验证」。\n"
    "- 不得把 heuristic 写成已确认风险、已证实风险、实验事实或文献已证明。\n"
    "- 文献的 PMID、PMCID、DOI、作者、期刊、年份等只能来自 literature_search 的实际返回，严禁根据模型记忆补充。\n"
    "- 如果信息不足，明确说明信息不足。\n"
    "\n"
    "【最终报告】\n"
    "最终科研报告必须区分四类信息，并固定为以下结构：\n"
    "1. 工具计算结果（A：工具实际返回的信息，如扫描/评分/突变/批量结果）\n"
    "2. 文献证据（B：literature_search 实际返回的文献，标注一般性证据）\n"
    "3. Agent 推断（C：根据 A+B 做出的推断，必须明确说明「这是推断」）\n"
    "4. 下一步验证建议（D：建议进行的实验/突变/验证，不能描述成已经发生）\n"
    "5. 证据局限性与风险声明（heuristic 未经实验验证、信息不足等）"
)


@dataclass
class ToolCall:
    """一次工具调用请求。"""
    name: str
    arguments: Dict[str, Any] = field(default_factory=dict)


@dataclass
class Observation:
    """一次工具执行的结果（含调用上下文，供真实 LLM 多轮函数调用重建消息）。"""
    tool: str
    result: str
    call_id: str = ""
    arguments: Dict[str, Any] = field(default_factory=dict)


@dataclass
class ReActStep:
    """ReAct 单步决策：要么调用一个工具(Action)，要么给出最终答案(Final Answer)。"""
    tool_call: Optional[ToolCall] = None
    final_answer: str = ""
    thought: str = ""

    @property
    def is_final(self) -> bool:
        return self.tool_call is None


class LLMBackend(Protocol):
    """LLM 后端协议：规划工具 + 单步决策(ReAct) + 生成最终答案。"""

    def plan(self, question: str, tools: List["Tool"]) -> List[ToolCall]: ...

    def step(self, question: str, observations: List[Observation], tools: List["Tool"]) -> ReActStep: ...

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

        # 2) 文献类问题 → 优先真实文献检索（literature_search）
        if _LIT_TOOL in tool_names and any(k in q for k in _KEYWORDS[_LIT_TOOL]):
            calls.append(ToolCall(_LIT_TOOL, {"query": question}))

        # 3) 知识类问题 → 内置知识库 RAG（保留为补充）
        if _KB_TOOL in tool_names and any(k in q for k in _KEYWORDS[_KB_TOOL]):
            calls.append(ToolCall(_KB_TOOL, {"question": question}))

        # 去重且按工具名稳定排序
        seen, out = set(), []
        for c in calls:
            if c.name not in seen:
                seen.add(c.name)
                out.append(c)
        return out[:3]

    def step(self, question: str, observations: List[Observation], tools: List["Tool"]) -> ReActStep:
        """Mock 的单步推进：按规划逐条执行工具；全部执行完后给出最终答案。

        这样即使离线也能演示"多步迭代"(每步只调一个工具,观察后再决定下一步)。
        """
        plan = self.plan(question, tools)
        if len(observations) < len(plan):
            call = plan[len(observations)]
            return ReActStep(tool_call=call, thought=f"Mock: 第 {len(observations) + 1}/{len(plan)} 步调用 {call.name}")
        return ReActStep(final_answer=self.answer(question, observations), thought="Mock: 已执行完规划，给出最终答案")

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

    def complete(self, prompt: str, system_prompt: Optional[str] = None) -> str:
        """离线模式：不调用真实 LLM，仅提示当前为 mock（用于 RAG 生成回答等场景）。"""
        return "（离线模式：未配置 API key，仅展示检索上下文与 prompt。在 .env 配置 DEEPSEEK_API_KEY 后此处会生成自然回答。）"


def _guess_mutation(question: str) -> str:
    """从提问中猜测突变（如 N55Q）；找不到则给示例。"""
    import re

    m = re.search(r"\b([A-Za-z])(\d+)([A-Za-z])\b", question or "")
    return m.group(0).upper() if m else "N55Q"


class _OpenAICompatBackend:
    """可选：基于 OpenAI 兼容接口（OpenAI / DeepSeek / Ollama 本地 等）的真实函数调用后端。"""

    def __init__(self, model: str, api_key_env: str, base_url: str, *, api_key: Optional[str] = None):
        try:
            from openai import OpenAI
        except Exception as e:  # pragma: no cover
            raise ImportError("需要安装 openai 包才能使用真实 LLM 后端") from e
        from config import get_env

        if api_key is None:
            api_key = get_env(api_key_env)
        if not api_key:
            raise RuntimeError(
                f"缺少 {api_key_env}。请在仓库根目录创建 .env（参考 .env.example），"
                f"写入 {api_key_env}=<your-key> 后重试。"
            )
        self._client = OpenAI(api_key=api_key, base_url=base_url)
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

    def step(self, question: str, observations: List[Observation], tools: List["Tool"]) -> ReActStep:
        """真 ReAct 单步：把问题与全部历史观察重建为多轮消息，让模型自主决定
        "继续调用工具(Action)" 还是 "给出最终答案(Final Answer)"。"""
        import json
        import uuid

        schemas = [t.to_schema() for t in tools]
        messages: List[dict] = [
            {"role": "system", "content": SCIENTIFIC_SYSTEM_PROMPT},
            {"role": "user", "content": question},
        ]
        for obs in observations:
            call_id = obs.call_id or f"call_{uuid.uuid4().hex[:8]}"
            messages.append({
                "role": "assistant",
                "content": None,
                "tool_calls": [{
                    "id": call_id,
                    "type": "function",
                    "function": {"name": obs.tool, "arguments": json.dumps(obs.arguments or {})},
                }],
            })
            messages.append({"role": "tool", "tool_call_id": call_id, "content": obs.result[:2000]})

        resp = self._client.chat.completions.create(
            model=self._model,
            messages=messages,
            tools=schemas,
            tool_choice="auto",
        )
        msg = resp.choices[0].message
        tool_calls = msg.tool_calls or []
        if tool_calls:
            tc = tool_calls[0]
            args = json.loads(tc.function.arguments or "{}")
            return ReActStep(tool_call=ToolCall(tc.function.name, args), thought=msg.content or "")
        return ReActStep(final_answer=msg.content or "", thought=msg.content or "")

    def answer(self, question: str, observations: List[Observation]) -> str:
        context = "\n".join(f"[{o.tool}] {o.result[:800]}" for o in observations)
        resp = self._client.chat.completions.create(
            model=self._model,
            messages=[
                {"role": "system", "content": SCIENTIFIC_SYSTEM_PROMPT},
                {"role": "user", "content": question},
            ],
        )
        return resp.choices[0].message.content or ""

    def complete(self, prompt: str, system_prompt: Optional[str] = None) -> str:
        """直接用 prompt 生成回答（用于 RAG 等"检索→生成"场景）。默认用科研分析系统提示词。"""
        system = system_prompt or SCIENTIFIC_SYSTEM_PROMPT
        resp = self._client.chat.completions.create(
            model=self._model,
            messages=[
                {"role": "system", "content": system},
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


class LocalOllamaLLM(_OpenAICompatBackend):
    """本地 Ollama 后端（OpenAI 兼容接口，GPU 本地推理，无需真实 API key）。

    配置（.env）:
        OLLAMA_MODEL:     模型名，默认 qwen2.5:7b
        OLLAMA_BASE_URL:  Ollama OpenAI 兼容端点，默认 http://localhost:11434/v1
    """

    def __init__(self, model: str = "", base_url: str = ""):
        from config import get_env

        model = model or get_env("OLLAMA_MODEL", "qwen2.5:7b")
        base_url = base_url or get_env("OLLAMA_BASE_URL", "http://localhost:11434/v1")
        # Ollama 不需要真实 key，传任意非空字符串即可
        super().__init__(model, "OLLAMA_API_KEY", base_url, api_key="ollama")


def get_llm(name: str = "mock", **kwargs):
    """LLM 工厂。name ∈ {mock, openai, deepseek, local}。"""
    name = (name or "mock").lower()
    if name == "mock":
        return MockLLM()
    if name in ("openai", "gpt"):
        return OpenAILLM(**kwargs)
    if name == "deepseek":
        return DeepSeekLLM(**kwargs)
    if name in ("local", "ollama"):
        return LocalOllamaLLM(**kwargs)
    raise ValueError(f"未知 LLM: {name}（可选 mock / openai / deepseek / local）")


def generate_answer(question: str, context: str, backend: str = "auto", system_prompt: Optional[str] = None) -> str:
    """基于检索上下文，用 LLM 生成一段自然回答（RAG 的"生成"环节）。

    backend: 'auto' 按 .env 自动选（deepseek / openai / mock）；也可显式指定。
    system_prompt: 可注入反幻觉等系统约束（默认用通用专家提示）。
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
    return llm.complete(prompt, system_prompt=system_prompt)
