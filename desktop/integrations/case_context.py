"""Local session only. Identity relationships require an explicit user statement."""
from dataclasses import dataclass, field

RELATIONSHIPS = ("未关联", "仅同属研究案例", "用户声明属于同一分子", "用户声明属于同一实验样品")
MATERIALS = ("合成演示", "公开研究材料", "用户自有研究数据")
SOURCE_LABELS = {"sequence": "规则序列分析", "biolab": "BioLab 结果", "literature": "文献批次"}


@dataclass(frozen=True)
class CaseSource:
    identifier: str
    sha256: str
    summary: str
    origin: str
    snapshot_json: str = "{}"


@dataclass(frozen=True)
class Association:
    kind: str
    basis: str
    sources: tuple[tuple[str, CaseSource], ...]


@dataclass
class CaseContext:
    case_id: str = ""
    topic: str = ""
    material: str = ""
    notes: str = ""
    sources: dict[str, CaseSource] = field(default_factory=dict)
    association: Association | None = None
    findings: str = ""
    recommendations: str = ""
    created_at: str = ""
    updated_at: str = ""
    historical_sources: dict[str, CaseSource] = field(default_factory=dict)
    historical_association: Association | None = None
    unavailable_sources: set[str] = field(default_factory=set)
    scientific_limitations: tuple[str, ...] | None = None

    def set_source(self, name: str, source: CaseSource | None) -> bool:
        if name not in SOURCE_LABELS:
            raise ValueError("未知来源")
        if source is None and name not in self.sources:
            return False
        self.association = None
        self.unavailable_sources.discard(name)
        if source is None:
            self.sources.pop(name)
        else:
            self.sources[name] = source
        return True

    def source_status(self, name):
        if name in self.unavailable_sources:
            return "来源缺失或不可用"
        current = self.sources.get(name)
        previous = self.historical_sources.get(name)
        if current is None:
            return "未重新核验" if previous else "未接入"
        if previous is None:
            return "当前已接入（没有历史记录）"
        identity = lambda s: (s.identifier, s.sha256, s.summary, s.snapshot_json)
        return "当前来源与保存记录匹配" if identity(current) == identity(previous) else "来源发生变化"

    def associate(self, kind: str, basis: str):
        if kind not in RELATIONSHIPS[1:]:
            raise ValueError("请选择关联类型，或点击解除关联。")
        if not self.case_id or self.material not in MATERIALS or len(self.sources) < 2 or not basis.strip():
            raise ValueError("请填写案例编号、选择材料类型、接入至少两个来源并说明关联依据。")
        self.association = Association(kind, basis.strip(), tuple(sorted(self.sources.items())))
