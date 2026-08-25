# agent/tools.py
# 工具注册：把既有规则引擎 / ML / RAG 封装为 Agent 可调用的"工具"。
#
# 每个 Tool 有：name、description、parameters(JSON-schema)、func。
# ToolRegistry 负责管理 & 暴露给 LLM 调用。

from __future__ import annotations

import os
from dataclasses import dataclass, field
from typing import Any, Callable, Dict, List, Optional

# 项目根目录（便于定位 ML 产物）
_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))


@dataclass
class Tool:
    name: str
    description: str
    func: Callable[..., str]
    parameters: List[Dict[str, Any]] = field(default_factory=list)

    def to_schema(self) -> Dict[str, Any]:
        """转换为 LLM 函数调用 schema（OpenAI tools 格式）。"""
        props = {p.get("name"): {"type": p.get("type", "string"), "description": p.get("description", "")} for p in self.parameters}
        required = [p["name"] for p in self.parameters if p.get("required")]
        return {
            "type": "function",
            "function": {
                "name": self.name,
                "description": self.description,
                "parameters": {"type": "object", "properties": props, "required": required},
            },
        }

    def run(self, arguments: Dict[str, Any]) -> str:
        """用给定参数执行工具，返回字符串结果；异常被捕获并转为可读信息。"""
        try:
            result = self.func(**arguments)
            if result is None:
                return "(无输出)"
            return str(result)
        except TypeError as e:
            return f"工具 {self.name} 参数错误: {e}"
        except Exception as e:
            return f"工具 {self.name} 执行异常: {e}"


class ToolRegistry:
    def __init__(self):
        self._tools: Dict[str, Tool] = {}

    def register(self, tool: Tool) -> "ToolRegistry":
        if tool.name in self._tools:
            raise ValueError(f"工具已存在: {tool.name}")
        self._tools[tool.name] = tool
        return self

    def get(self, name: str) -> Tool:
        if name not in self._tools:
            raise KeyError(f"未知工具: {name}")
        return self._tools[name]

    def list(self) -> List[Tool]:
        return list(self._tools.values())

    def names(self) -> List[str]:
        return list(self._tools.keys())


# ---------- 工具实现（封装既有模块） ----------

def _default_cdr():
    return 31, 35, 50, 65, 99, 110


def tool_scan_antibody(sequence: str) -> str:
    """扫描抗体可变区序列的化学稳定性风险基序，并给出规则风险评分。"""
    from core import analyze_sequence
    from scoring import compute_risk_score

    seq = (sequence or "").strip().upper()
    if not seq:
        return "请提供序列（sequence）。"
    result = analyze_sequence(seq, *_default_cdr())
    if result.errors:
        return f"错误: {'；'.join(result.errors)}"
    score = compute_risk_score([("sequence", result)])
    hits = [f"{r.motif}@{r.position}({r.region})" for r in result.risks]
    return (
        f"序列长度 {result.sequence_length} aa；"
        f"规则风险评分 {score.overall_score}（{score.risk_level}）；"
        f"命中风险基序: " + ("; ".join(hits) if hits else "无")
    )


def tool_mutate_scan(sequence: str, mutation: str) -> str:
    """执行点突变并重新扫描，判断风险是否被消除。"""
    from core import mutate_and_rescan

    report, risks, summary, mutated = mutate_and_rescan(sequence, mutation, *_default_cdr())
    if "突变失败" in summary:
        return summary
    return f"突变 {mutation} 后序列: {mutated}\n{summary}\n{report.splitlines()[-2] if len(report.splitlines()) >= 2 else report}"


def tool_risk_score(sequence: str) -> str:
    """计算单条序列的规则风险评分（0-100）与风险等级。"""
    from core import analyze_sequence
    from scoring import compute_risk_score

    seq = (sequence or "").strip().upper()
    if not seq:
        return "请提供序列（sequence）。"
    result = analyze_sequence(seq, *_default_cdr())
    if result.errors:
        return f"错误: {'；'.join(result.errors)}"
    score = compute_risk_score([("sequence", result)])
    return f"风险评分 {score.overall_score}（{score.risk_level}）"


def tool_predict_risk(sequence: str) -> str:
    """用训练好的 ML 模型预测高风险概率（需先运行 python cli.py ml-train）。"""
    from ml.train import load_bundle

    cls_path = os.path.join(_ROOT, "ml", "artifacts", "cls.joblib")
    reg_path = os.path.join(_ROOT, "ml", "artifacts", "reg.joblib")
    if os.path.exists(cls_path):
        model, encoder = load_bundle(cls_path)
        proba = model.predict_proba(encoder.transform([sequence]))[:, 1][0]
        return f"ML 预测高风险概率: {proba:.4f}（分类模型）"
    if os.path.exists(reg_path):
        model, encoder = load_bundle(reg_path)
        score = model.predict(encoder.transform([sequence]))[0]
        return f"ML 预测风险分数: {float(score):.2f}（回归模型）"
    return "未找到已训练的模型。请先运行: python cli.py ml-train --n 800 --task classification --model logistic --save ml/artifacts/cls.joblib"


_RAG_CACHE: Optional["RagPipeline"] = None


def tool_rag_search(question: str) -> str:
    """从内置抗体可开发性/PTM 知识库检索与问题最相关的资料。"""
    global _RAG_CACHE
    if _RAG_CACHE is None:
        from rag import RagPipeline
        from rag.knowledge_base import KNOWLEDGE_BASE

        pipe = RagPipeline(embedder="tfidf", strategy="hybrid", top_k=3)
        pipe.index(KNOWLEDGE_BASE)
        _RAG_CACHE = pipe
    result = _RAG_CACHE.query(question)
    return result["context"] or "（未检索到相关资料）"


def tool_literature_search(query: str, max_results: int = 5, source: str = "auto") -> str:
    """从 Europe PMC / PubMed 检索真实生物医学文献，返回结构化证据。

    只返回真实 API 数据；未检索到时返回空提示；API 故障返回明确错误，不伪装成无结果。
    """
    from literature import LiteratureSearchError, search_literature

    try:
        evidence = search_literature(query, max_results=int(max_results), source=source)
    except LiteratureSearchError as e:
        return e.to_user_message()
    if not evidence:
        return "未检索到相关文献。"
    lines = []
    for i, ev in enumerate(evidence, 1):
        lines.append(
            f"[{i}] Title: {ev.title}\n"
            f"    Authors: {', '.join(ev.authors) if ev.authors else '-'}\n"
            f"    Journal: {ev.journal} ({ev.year})\n"
            f"    PMID: {ev.pmid}\n"
            f"    PMCID: {ev.pmcid or '-'}\n"
            f"    DOI: {ev.doi or '-'}\n"
            f"    Abstract: {ev.abstract[:300]}"
        )
    return "\n\n".join(lines)


def default_tools() -> ToolRegistry:
    """构建默认工具集：扫描 / 突变 / 打分 / ML 预测 / RAG / 文献检索。"""
    reg = ToolRegistry()
    reg.register(Tool(
        name="scan_antibody",
        description="扫描抗体可变区序列的化学稳定性风险基序，给出规则风险评分与命中清单。适用于「评估/分析某条序列」。",
        func=tool_scan_antibody,
        parameters=[{"name": "sequence", "type": "string", "required": True, "description": "抗体可变区氨基酸序列"}],
    ))
    reg.register(Tool(
        name="mutate_scan",
        description="对序列做点突变并重新扫描，验证风险是否被消除。适用于「把位置X突变成Y」或评估改造。",
        func=tool_mutate_scan,
        parameters=[
            {"name": "sequence", "type": "string", "required": True, "description": "原始抗体序列"},
            {"name": "mutation", "type": "string", "required": True, "description": "突变，如 N55Q"},
        ],
    ))
    reg.register(Tool(
        name="risk_score",
        description="计算单条序列的规则风险评分(0-100)与风险等级。适用于「打分/风险分」。",
        func=tool_risk_score,
        parameters=[{"name": "sequence", "type": "string", "required": True, "description": "抗体序列"}],
    ))
    reg.register(Tool(
        name="predict_risk",
        description="用训练好的 ML 模型预测高风险概率(需先 ml-train)。适用于「预测/模型预测」。",
        func=tool_predict_risk,
        parameters=[{"name": "sequence", "type": "string", "required": True, "description": "抗体序列"}],
    ))
    reg.register(Tool(
        name="rag_search",
        description="从抗体可开发性/PTM 知识库检索与问题最相关的资料。适用于「什么是/为什么/哪里」等知识问答。",
        func=tool_rag_search,
        parameters=[{"name": "question", "type": "string", "required": True, "description": "要检索的问题"}],
    ))
    reg.register(Tool(
        name="literature_search",
        description=(
            "Search real biomedical literature using Europe PMC and PubMed. "
            "Returns structured evidence obtained directly from external APIs. "
            "Never invents literature metadata."
        ),
        func=tool_literature_search,
        parameters=[
            {"name": "query", "type": "string", "required": True, "description": "生物医学检索词(由 Query Generator 生成)"},
            {"name": "max_results", "type": "integer", "required": False, "description": "最多返回条数(1-10,默认5)"},
            {"name": "source", "type": "string", "required": False, "description": "auto/europepmc/pubmed"},
        ],
    ))
    return reg
