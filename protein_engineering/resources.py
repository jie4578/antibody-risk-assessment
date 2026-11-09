"""Read-only installed resources, usable from source, wheel and frozen Desktop."""
from importlib import resources
from pathlib import Path

TABLE_LABELS = {
    "enzyme_targets": "靶标", "protein_variants": "序列与变体", "samples": "样品",
    "experiment_batches": "实验批次", "assay_results": "实测结果（原始报告值）",
    "kinetic_timecourse": "原始时间序列（原件层）",
    "ai_predictions": "预测记录（仅保存，不评价）",
    "structure_assets": "结构元数据（不分析结构）", "source_manifest": "提供方来源清单",
}
DOCUMENTS = ("FOUNDATION_STATUS.md", "PROTEIN_ENGINEERING_ROADMAP.md", "PHASE0_DATA_INTAKE.md",
             "DATA_DICTIONARY.md", "ANALYSIS_REQUIREMENTS.md", "PHASE_C1_INITIAL_RATE_IMPLEMENTATION.md")


def template_bytes(kind: str) -> bytes:
    if kind not in TABLE_LABELS:
        raise ValueError("Unknown record kind")
    return resources.files("protein_engineering").joinpath("resources", "phase0", "templates", kind + "_template.csv").read_bytes()


def document_text(name: str) -> str:
    if name not in DOCUMENTS:
        raise ValueError("Unknown document")
    return resources.files("protein_engineering").joinpath("resources", "phase0", name).read_text(encoding="utf-8-sig")


def save_template(kind: str, destination) -> Path:
    """Never replace an existing file, including an experimental input file."""
    data = template_bytes(kind)
    destination = Path(destination)
    with destination.open("xb") as stream:
        stream.write(data)
    return destination
