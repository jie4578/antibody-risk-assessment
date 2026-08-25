# literature/evidence.py
# Evidence 数据模型：一次文献检索返回的单条结构化证据。
#
# 反幻觉铁律：所有字段必须来自真实 API 响应；缺失字段为 None/""，
# 绝不允许 LLM 根据模型记忆补全任何字段。

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional


@dataclass
class Evidence:
    """单条文献证据。字段语义与来源：

    - source:    "europepmc" | "pubmed"（来自哪个 API）
    - 其余字段:   直接映射自 API 响应；缺失为 None/空。
    """

    evidence_id: str = ""
    title: str = ""
    authors: List[str] = field(default_factory=list)
    journal: str = ""
    year: Optional[int] = None
    pmid: str = ""
    pmcid: str = ""
    doi: str = ""
    abstract: str = ""
    is_open_access: bool = False
    full_text_available: bool = False
    source: str = ""
    retrieved_at: str = ""
    partial: bool = False  # True = 存在缺失字段（仍可能有效）

    # ---------- 序列化 ----------
    def to_dict(self) -> Dict[str, Any]:
        return {
            "evidence_id": self.evidence_id,
            "title": self.title,
            "authors": list(self.authors),
            "journal": self.journal,
            "year": self.year,
            "pmid": self.pmid,
            "pmcid": self.pmcid,
            "doi": self.doi,
            "abstract": self.abstract,
            "is_open_access": self.is_open_access,
            "full_text_available": self.full_text_available,
            "source": self.source,
            "retrieved_at": self.retrieved_at,
            "partial": self.partial,
        }

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "Evidence":
        return cls(
            evidence_id=str(data.get("evidence_id") or ""),
            title=str(data.get("title") or ""),
            authors=list(data.get("authors") or []),
            journal=str(data.get("journal") or ""),
            year=data.get("year"),
            pmid=str(data.get("pmid") or ""),
            pmcid=str(data.get("pmcid") or ""),
            doi=str(data.get("doi") or ""),
            abstract=str(data.get("abstract") or ""),
            is_open_access=bool(data.get("is_open_access", False)),
            full_text_available=bool(data.get("full_text_available", False)),
            source=str(data.get("source") or ""),
            retrieved_at=str(data.get("retrieved_at") or ""),
            partial=bool(data.get("partial", False)),
        )

    # ---------- 有效性 ----------
    def is_valid(self) -> bool:
        """最低有效条件：title + abstract，或 title + pmid。不满足则丢弃。"""
        has_title = bool(self.title.strip())
        has_abstract = bool(self.abstract.strip())
        has_pmid = bool(self.pmid.strip())
        if not has_title:
            return False
        return has_abstract or has_pmid

    def citation_key(self) -> str:
        """用于去重的稳定键：优先 pmid，其次 pmcid，其次 doi。"""
        for key in (self.pmid, self.pmcid, self.doi):
            if key:
                return key
        return self.evidence_id

    def __repr__(self) -> str:  # pragma: no cover - 调试用
        return f"Evidence(pmid={self.pmid or '-'}, title={self.title[:40]!r}, source={self.source})"
