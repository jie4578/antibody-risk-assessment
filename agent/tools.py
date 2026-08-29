# agent/tools.py
# 工具注册：把既有规则引擎 / ML / RAG 封装为 Agent 可调用的"工具"。
#
# 每个 Tool 有：name、description、parameters(JSON-schema)、func。
# ToolRegistry 负责管理 & 暴露给 LLM 调用。

from __future__ import annotations

import os
import re
from dataclasses import dataclass, field
from typing import Any, Callable, Dict, List, Optional

# 项目根目录（便于定位 ML 产物）
_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))

# ---------- v9.3：工具输入来源边界（确定性） ----------
_AMINO_ACIDS = frozenset("ACDEFGHIKLMNPQRSTVWY")
_MIN_SEQUENCE_LEN = 5  # 最小可接受序列长度（含短肽测试用例如 AAANVSTT）
SEQUENCE_TOOLS = ("scan_antibody", "mutate_scan")  # 需要用户序列输入的工具


def extract_user_sequence(user_query: str) -> str:
    """从用户输入中提取一段抗体序列（仅含 20 种标准氨基酸）。

    找不到或不可靠 → 返回空串。位点（N55 / NG@55-56）不是序列。
    """
    q = str(user_query or "")
    best = ""
    for token in re.split(r"[\s,，;；、]+", q):
        token = token.strip().upper()
        if len(token) < _MIN_SEQUENCE_LEN or any(c not in _AMINO_ACIDS for c in token):
            continue
        if len(token) > len(best):
            best = token
    return best


def sequence_source_of(user_query: str, sequence: str) -> str:
    """判定序列来源：user_provided / unavailable / invalid。

    - 序列必须是标准氨基酸字符串、长度达标、且能在用户问题中逐字找到；
    - 用户只给位点/评分/风险描述 → unavailable（不是序列）；
    - Agent 自行构造、不在用户问题中的序列 → invalid。
    """
    s = str(sequence or "").strip().upper()
    if not s:
        return "unavailable"
    if len(s) < _MIN_SEQUENCE_LEN or any(c not in _AMINO_ACIDS for c in s):
        return "invalid"
    q = str(user_query or "").upper()
    if s in q:
        return "user_provided"
    return "invalid"


def blocked_sequence_message(tool: str, source: str) -> str:
    """工具因序列来源不合法被阻止时的结构化返回（不伪造 scan 结果）。"""
    return (
        f"工具调用被阻止：未提供可验证的用户抗体序列（sequence_source={source}）。"
        f"未提供抗体序列，无法进行{'序列扫描' if tool == 'scan_antibody' else '突变扫描'}。"
        f"请提供抗体序列后再调用 {tool}。"
    )


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
    """扫描抗体可变区序列的化学稳定性风险基序，并给出规则风险评分。

    输出为结构化文本（确定性，直接供 LLM 消费）：
      序列长度 / 规则风险评分(风险等级) / 命中清单（每条含类别、基序、位置、区域）。
    """
    from core import analyze_sequence
    from scoring import compute_risk_score

    seq = (sequence or "").strip().upper()
    if not seq:
        return "请提供序列（sequence）。"
    result = analyze_sequence(seq, *_default_cdr())
    if result.errors:
        return f"错误: {'；'.join(result.errors)}"
    score = compute_risk_score([("sequence", result)])
    hits = [
        f"[{r.category}] {r.motif}@{r.position}({r.region})"
        + ("[heuristic,未经实验验证]" if r.evidence_level == "heuristic" else "")
        for r in result.risks
    ]
    return (
        f"序列长度 {result.sequence_length} aa；"
        f"规则风险评分 {score.overall_score}（{score.risk_level}）；"
        f"命中风险基序: " + ("; ".join(hits) if hits else "无")
    )


def _to_risk_items(risks):
    """把核心层返回的风险条目统一为 RiskItem 对象（兼容 dict 与对象两种返回结构）。"""
    from models import RiskItem

    items = []
    for r in risks or []:
        if isinstance(r, RiskItem):
            items.append(r)
        elif isinstance(r, dict):
            items.append(RiskItem.from_dict(r))
        else:
            items.append(r)
    return items


def tool_mutate_scan(sequence: str, mutation: str) -> str:
    """执行点突变并重新扫描，给出突变前后风险对比（确定性结构化文本）。

    注意：core.mutate_and_rescan 返回的 risks 为 dict（scan_sequence 的 to_dict 结构），
    统一转成 RiskItem 后再取 category/motif 等属性，避免类型崩溃。
    """
    from collections import Counter

    from core import analyze_sequence, mutate_and_rescan

    report, risks, summary, mutated = mutate_and_rescan(sequence, mutation, *_default_cdr())
    if "突变失败" in summary:
        return summary
    before_items = _to_risk_items(analyze_sequence(sequence, *_default_cdr()).risks)
    after_items = _to_risk_items(risks)
    before = dict(Counter(r.category for r in before_items))
    after = dict(Counter(r.category for r in after_items))
    hits = "; ".join(f"[{r.category}] {r.motif}@{r.position}({r.region})" for r in after_items) if after_items else "无"
    return (
        f"突变 {mutation} 成功 → 新序列: {mutated}\n"
        f"突变前风险类别计数: {before}\n"
        f"突变后风险类别计数: {after}\n"
        f"突变后命中: {hits}"
    )


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


def tool_batch_analysis(csv_path: str = "", csv_text: str = "") -> str:
    """批量分析抗体序列（CSV 文件路径 或 内联 CSV 文本），返回逐行结构化摘要。

    输入二选一：
      csv_path: 本地 CSV/XLSX/FASTA 文件路径
      csv_text: 内联 CSV 文本（含 antibody_id,VH,VL 表头）
    输出：每行 antibody_id / analysis_status / 风险计数 / risk_score / risk_level / warnings。
    """
    import io

    import pandas as pd

    from batch_analysis import batch_analysis as run_batch

    if csv_path and not csv_text:
        from input_parser import load_batch_input

        df = load_batch_input(csv_path)
    elif csv_text and not csv_path:
        df = pd.read_csv(io.StringIO(csv_text))
    else:
        return "请提供 csv_path（文件路径）或 csv_text（内联 CSV 文本），二选一。"
    missing = [c for c in ("antibody_id", "VH", "VL") if c not in df.columns]
    if missing:
        return f"CSV 缺少必需列: {', '.join(missing)}"
    result = run_batch(df)
    lines = [f"批量分析 {len(result)} 条记录:"]
    for _, row in result.iterrows():
        warn = f" | warnings: {row['warnings']}" if row["warnings"] else ""
        lines.append(
            f"- {row['antibody_id']}: status={row['analysis_status']} "
            f"PTM={row['PTM_risk_count']} liability={row['liability_risk_count']} "
            f"total={row['total_risk_count']} risk_score={row['risk_score']} "
            f"risk_level={row['risk_level']}{warn}"
        )
    return "\n".join(lines)


def default_tools() -> ToolRegistry:
    """构建默认工具集：扫描 / 突变 / 打分 / ML 预测 / RAG / 文献检索 / 批量分析。"""
    reg = ToolRegistry()
    reg.register(Tool(
        name="scan_antibody",
        description="扫描抗体可变区序列的化学稳定性风险基序（脱酰胺/异构化/氧化/N-糖基化/O-糖基化热点），给出规则风险评分与命中清单。适用于「评估/分析某条序列/糖基化风险」。",
        func=tool_scan_antibody,
        parameters=[{"name": "sequence", "type": "string", "required": True, "description": "抗体可变区氨基酸序列"}],
    ))
    reg.register(Tool(
        name="mutate_scan",
        description="对序列做点突变并重新扫描，输出突变前后风险类别对比。适用于「把位置X突变成Y」「突变后风险是否消除」。",
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
            "用于检索真实科学文献（Europe PMC / PubMed），返回 PMID、DOI、摘要等真实证据。"
            "当序列扫描发现重要 PTM、chemical liability 或其他需要证据支持的风险时，可调用该工具获取文献证据。"
            "Returns structured evidence obtained directly from external APIs. Never invents literature metadata."
        ),
        func=tool_literature_search,
        parameters=[
            {"name": "query", "type": "string", "required": True, "description": "生物医学检索词(由 Query Generator 生成)"},
            {"name": "max_results", "type": "integer", "required": False, "description": "最多返回条数(1-10,默认5)"},
            {"name": "source", "type": "string", "required": False, "description": "auto/europepmc/pubmed"},
        ],
    ))
    reg.register(Tool(
        name="batch_analysis",
        description="批量分析抗体序列 CSV（本地文件路径或内联 CSV 文本），逐条返回状态/PTM/liability/风险评分。适用于「批量分析」「分析这个 CSV」。",
        func=tool_batch_analysis,
        parameters=[
            {"name": "csv_path", "type": "string", "required": False, "description": "本地 CSV/XLSX/FASTA 文件路径"},
            {"name": "csv_text", "type": "string", "required": False, "description": "内联 CSV 文本（表头 antibody_id,VH,VL）"},
        ],
    ))
    return reg
