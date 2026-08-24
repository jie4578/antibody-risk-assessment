# models.py
# 统一分析结果数据模型：RiskItem / AnalysisResult。
# 这是新的标准内部数据结构；旧 API（tuple / DataFrame）通过 adapter 保持兼容。

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Dict, List


@dataclass
class RiskItem:
    """单条风险基序命中。内部字段为英文，to_dict() 输出与现有 UI schema 一致的中文键。"""
    category: str = ""
    motif: str = ""
    position: str | int = ""
    region: str = ""
    description: str = ""

    def to_dict(self) -> Dict[str, Any]:
        """转换为 UI / 旧代码使用的字典（中文键与现有 schema 一致）。"""
        return {
            "类别": self.category,
            "基序": self.motif,
            "位置": self.position,
            "区域": self.region,
            "描述": self.description,
        }

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "RiskItem":
        """从旧字典（中文键）构造 RiskItem。"""
        return cls(
            category=data.get("类别", ""),
            motif=data.get("基序", ""),
            position=data.get("位置", ""),
            region=data.get("区域", ""),
            description=data.get("描述", ""),
        )


@dataclass
class AnalysisResult:
    """一次完整序列分析的统一结果，可完整表达 scan_sequence 的现有输出。"""
    sequence: str = ""
    sequence_length: int = 0
    risks: List[RiskItem] = field(default_factory=list)
    summary: str = ""
    report: str = ""
    warnings: List[str] = field(default_factory=list)
    errors: List[str] = field(default_factory=list)
    metadata: Dict[str, Any] = field(default_factory=dict)

    def to_legacy_tuple(self):
        """旧 scan_sequence API 的返回结构：(report, risks_dicts, summary)。"""
        return self.report, [r.to_dict() for r in self.risks], self.summary
