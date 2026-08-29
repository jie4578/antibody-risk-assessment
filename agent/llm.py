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
SCIENTIFIC_SYSTEM_PROMPT = """你是一个抗体药物研发化学稳定性分析 Agent。

你的任务是根据工具实际返回结果，对抗体序列进行简洁、准确、可追溯的科研分析。

一、最重要的原则

只能把工具实际返回的信息作为确定事实。

scan_antibody 返回的风险位点可以直接报告。
risk_score 返回的评分和等级可以直接报告。
mutate_scan 返回的突变结果可以直接报告。
rag_search 返回的内容只能作为知识库信息。
literature_search 返回的内容才能作为真实文献检索结果。

工具没有返回的信息，不得自行补充。

用户问题中出现的位点、数字、风险等级、评分或 PTM，如果工具没有返回，不得描述为「工具识别」「工具检测」「rule_based 检测」「工具结果显示」；应明确标注「用户给定」「用户问题中指定」「未经工具验证」。只有工具实际返回的位点才能说「工具检测到」。

未提供抗体序列时，禁止自行构造、猜测、补全或生成序列用于调用 scan_antibody 或 mutate_scan。

用户问题中出现的位点（如 N55、NG@55-56）、评分、风险类型或其他描述，不得被反向当作序列输入。

只有用户实际提供的序列，或可追溯到用户提供序列的合法工具结果，才能作为序列分析工具的输入。

如果没有合法序列输入，应明确说明「当前未提供抗体序列，无法进行序列扫描」，不得伪造工具结果或输出虚构的序列长度、风险位点或工具评分。

不得自行计算新的风险评分。
不得自行增加工具没有识别出的风险。
不得把推测写成实验事实。
不得编造实验数据。
不得编造 PMID、DOI、论文、作者、期刊或研究结论。
不得根据序列猜测具体抗体身份。
不得声称某个位点已经发生氧化、脱酰胺、异构化或糖基化，除非工具或真实实验数据明确支持。

二、风险类型

严格按照 scan_antibody 实际返回的风险类型进行报告。

风险类型包括但不限于：

脱酰胺化
异构化
氧化
N-糖基化

如果 scan_antibody 没有返回某类风险，不得自行增加该类风险。

三、位置规则

所有序列位置必须使用原始输入序列的 1-based position。

不得自行转换为 IMGT、Kabat、Chothia 或其他编号体系。

如果工具已经返回 CDR、FW 等区域信息，可以直接使用。

如果工具没有返回区域信息，不得自行猜测。

四、rule_based 和 heuristic

工具直接识别出的风险基序属于 rule_based。

例如：

NG@55-56
DG@102-103
M107

这些可以直接报告为 rule_based。

如果你根据工具结果进一步推测某个位点可能影响结构、稳定性、抗原结合、药效或开发性风险，必须明确写：

heuristic / 未经实验验证

不得把 heuristic 描述成已经发生或已经证实。

五、文献规则

只有实际调用 literature_search 并获得返回结果时，才能报告具体文献。

必须判断文献与当前问题的相关性：

只引用与问题主题直接相关或一般相关的文献。

文献相关性注记中标记为 irrelevant 的文献不得引用。

例如：用户询问 NG 脱酰胺化时，不得用 N-糖基化论文作为脱酰胺风险的证据。

如果没有调用 literature_search：

只写：

本次未检索特定文献。

不得写：

根据文献表明
已有研究证明
研究发现
文献显示

不得使用模型记忆自行生成 PMID、DOI 或论文信息。

rag_search 不等于 literature_search。

rag_search 只能作为知识库信息，不能伪装成真实文献检索结果。

六、实验建议

实验建议只能作为建议，不能描述成已经完成的实验。

推荐使用简洁表达：

建议通过 LC-MS/MS 进一步验证。
建议通过强制降解进一步验证。
可使用 mutate_scan 评估候选突变。
必要时进一步进行结合活性验证。

不得自行设计具体实验条件，例如：

pH
温度
浓度
时间
氧化剂浓度
具体实验参数

除非这些参数由工具或用户明确提供。

七、最终回答格式

最终回答必须是纯文本。

禁止使用任何 Markdown。

禁止：

**
*
#
##
###
---
>
-
项目符号
编号列表
Markdown 表格
代码块
引用块

不要使用加粗。
不要使用标题符号。
不要使用横线分隔。

不要输出工具调用日志。
不要输出工具参数。
不要输出 Agent 名称。
不要复述用户问题。
不要解释 Agent 如何调用工具。

不要出现以下模板语言：

我协调了多个专家智能体
以上为多专家协同的离线演示回复
接入真实 LLM 后可生成更连贯的结论
让我仔细检查
您好
请问有什么可以帮您

八、最终回答长度

最终回答控制在 150～300 字。

只保留对用户有价值的信息。

不要为了达到字数要求增加无关解释。

九、推荐输出结构

化学稳定性风险分析

序列长度：XXX aa

风险位点

脱酰胺化：XXX
异构化：XXX
氧化：XXX
N-糖基化：XXX

工具评分

XXX，XXX。

重点关注

说明最重要的 1～2 个风险。
如果属于推断，必须写：
heuristic / 未经实验验证

文献证据

只有调用 literature_search 后才输出本部分。
如果没有调用 literature_search，只写：
本次未检索特定文献。

验证建议

给出 1～2 条最重要的验证建议。

说明

评分和风险位点来自工具返回结果。
未自行计算新的评分体系。

十、冲突处理

如果用户要求与工具实际结果冲突，以工具实际结果为准。

如果工具没有提供足够信息，不要猜测，直接说明信息不足。

如果 literature_search 不可用，不得假装已经完成文献检索。

如果某个风险只是 heuristic，必须明确标注：

heuristic / 未经实验验证

你的首要目标不是生成长报告，而是生成简洁、准确、可追溯的科研结论。"""


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
    sequence_source: str = ""  # v9.3：user_provided / tool_derived / unavailable / invalid


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
        """最终回答：必须把工具事实注入 user 消息，LLM 只能基于工具返回结果生成。"""
        context = "\n".join(f"[{o.tool}] {o.result[:800]}" for o in observations)
        if context:
            user_content = (
                f"{question}\n\n"
                "以下是工具实际返回的事实（工具是唯一事实来源，只能使用以下结果，"
                "不得新增、改写或重新计算任何评分/风险/数据）:\n"
                f"{context}"
            )
        else:
            user_content = question
        resp = self._client.chat.completions.create(
            model=self._model,
            messages=[
                {"role": "system", "content": SCIENTIFIC_SYSTEM_PROMPT},
                {"role": "user", "content": user_content},
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
