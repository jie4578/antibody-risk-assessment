# literature/context.py
# Context Builder：把 Evidence 转成 LLM 上下文。
# Context 中显示的 metadata 必须直接来自 Evidence，绝不让 LLM 自己补 metadata。

from __future__ import annotations

from typing import List, Sequence

from .evidence import Evidence

# 反幻觉系统提示（原则 2）：LLM 只能引用本次检索返回的真实文献
EVIDENCE_SYSTEM_PROMPT = (
    "You may only cite literature returned by the literature_search tool. "
    "Never invent papers, PMID, PMCID, DOI, authors, journals, or publication years. "
    "If the retrieved evidence is insufficient, explicitly say that the available literature evidence is insufficient.\n"
    "中文：你只能引用本次检索返回的真实文献证据。不得根据模型记忆创造论文、PMID、DOI、作者、期刊或年份。"
    "如果检索结果不足以回答问题，必须明确说明证据不足，而不是补充猜测。"
)


def _field(label: str, value) -> str:
    v = "" if value is None else str(value).strip()
    return f"{label}: {v}" if v else f"{label}: "


def build_context(evidence: Sequence[Evidence], *, max_chars: int = 6000) -> str:
    """把 Evidence 列表拼成 LLM 上下文（metadata 只来自 Evidence）。"""
    parts: List[str] = []
    total = 0
    for i, ev in enumerate(evidence, start=1):
        block = "\n".join([
            f"[Evidence {i}]",
            _field("Title", ev.title),
            _field("Authors", ", ".join(ev.authors)),
            _field("Journal", ev.journal),
            _field("Year", ev.year),
            _field("PMID", ev.pmid),
            _field("PMCID", ev.pmcid),
            _field("DOI", ev.doi),
            "",
            _field("Abstract", ev.abstract),
        ])
        if total + len(block) > max_chars and parts:
            break
        parts.append(block)
        total += len(block)
    return "\n\n".join(parts)


def build_sources(evidence: Sequence[Evidence]) -> List[dict]:
    """生成面向展示的 Sources 摘要（Title/PMID/DOI/Journal/Year/Source），仅取 Evidence 字段。"""
    return [
        {
            "title": ev.title,
            "pmid": ev.pmid,
            "doi": ev.doi,
            "journal": ev.journal,
            "year": ev.year,
            "source": ev.source,
        }
        for ev in evidence
    ]
