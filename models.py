# models.py
# 统一分析结果数据模型：RiskItem / AnalysisResult。
# 这是新的标准内部数据结构；旧 API（tuple / DataFrame）通过 adapter 保持兼容。

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Dict, List


@dataclass
class RiskItem:
    """单条风险基序命中。内部字段为英文，to_dict() 输出与现有 UI schema 一致的中文键。

    新增字段（v2.0）：
        context:        命中位点周围 ±3 aa 的序列上下文（N-糖基化 / O-糖基化）
        evidence_level: 证据级别：rule_based(规则) / heuristic(启发式，未经实验验证)
    旧 API 兼容：to_dict() 仍只输出原 5 个中文键；新字段通过 to_detail_dict() 输出。
    """
    category: str = ""
    motif: str = ""
    position: str | int = ""
    region: str = ""
    description: str = ""
    context: str = ""
    evidence_level: str = "rule_based"

    def to_dict(self) -> Dict[str, Any]:
        """转换为 UI / 旧代码使用的字典（中文键与现有 schema 一致，保持 5 键不变）。"""
        return {
            "类别": self.category,
            "基序": self.motif,
            "位置": self.position,
            "区域": self.region,
            "描述": self.description,
        }

    def to_detail_dict(self) -> Dict[str, Any]:
        """输出完整字段（含 context / evidence_level），供新功能展示使用。"""
        return {
            "类别": self.category,
            "基序": self.motif,
            "位置": self.position,
            "区域": self.region,
            "描述": self.description,
            "上下文": self.context,
            "证据级别": self.evidence_level,
        }

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "RiskItem":
        """从旧字典（中文键）构造 RiskItem；兼容含/不含新字段的数据。"""
        return cls(
            category=data.get("类别", ""),
            motif=data.get("基序", ""),
            position=data.get("位置", ""),
            region=data.get("区域", ""),
            description=data.get("描述", ""),
            context=data.get("上下文", ""),
            evidence_level=data.get("证据级别", "rule_based"),
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
