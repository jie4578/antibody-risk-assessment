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

    def set_source(self, name: str, source: CaseSource | None) -> bool:
        if name not in SOURCE_LABELS:
            raise ValueError("未知来源")
        if source is None and name not in self.sources:
            return False
        self.association = None
        if source is None:
            self.sources.pop(name)
        else:
            self.sources[name] = source
        return True

    def associate(self, kind: str, basis: str):
        if kind not in RELATIONSHIPS[1:]:
            raise ValueError("请选择关联类型，或点击解除关联。")
        if not self.case_id or self.material not in MATERIALS or len(self.sources) < 2 or not basis.strip():
            raise ValueError("请填写案例编号、选择材料类型、接入至少两个来源并说明关联依据。")
        self.association = Association(kind, basis.strip(), tuple(sorted(self.sources.items())))
