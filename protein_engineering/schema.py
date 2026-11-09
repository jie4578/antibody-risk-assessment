"""Template schemas, identity and data-quality checks; no measured values made up."""
from dataclasses import dataclass
from decimal import Decimal, InvalidOperation
from datetime import datetime, timedelta
from functools import lru_cache
import csv
import io
import re

from .resources import template_bytes
from .sequences import normalize_sequence


@dataclass(frozen=True)
class TableSpec:
    id_field: str
    required: tuple[str, ...]
    references: tuple[tuple[str, str], ...] = ()


SPECS = {
    "enzyme_targets": TableSpec("target_id", ("target_id", "target_name")),
    "protein_variants": TableSpec("variant_id", ("variant_id", "target_id", "variant_name", "variant_role", "sequence"),
        (("target_id", "enzyme_targets"), ("parent_variant_id", "protein_variants"), ("reference_variant_id", "protein_variants"))),
    "samples": TableSpec("sample_id", ("sample_id", "variant_id"), (("variant_id", "protein_variants"),)),
    "experiment_batches": TableSpec("batch_id", ("batch_id", "assay_id", "assay_type"), (("wt_control_sample_id", "samples"),)),
    "assay_results": TableSpec("result_id", ("result_id", "batch_id", "sample_id", "metric_name"), (("batch_id", "experiment_batches"), ("sample_id", "samples"))),
    "kinetic_timecourse": TableSpec("observation_id", ("observation_id", "batch_id", "sample_id", "time_value", "time_unit"), (("batch_id", "experiment_batches"), ("sample_id", "samples"))),
    "ai_predictions": TableSpec("prediction_id", ("prediction_id", "variant_id", "predicted_metric"), (("variant_id", "protein_variants"),)),
    "structure_assets": TableSpec("structure_id", ("structure_id", "variant_id", "structure_source"), (("variant_id", "protein_variants"),)),
    "source_manifest": TableSpec("source_file_id", ("source_file_id", "file_name")),
}
NUMERIC_FIELDS = frozenset("concentration_value purity_percent storage_temperature_c freeze_thaw_cycles temperature_c pH cofactor_concentration enzyme_concentration reaction_volume substrate_concentration time_value raw_signal blank_signal corrected_signal product_concentration metric_value predicted_value rank_within_design uncertainty_value confidence_value design_round".split())
UNIT_PAIRS = (("concentration_value", "concentration_unit"), ("cofactor_concentration", "cofactor_concentration_unit"),
              ("enzyme_concentration", "enzyme_concentration_unit"), ("reaction_volume", "reaction_volume_unit"),
              ("substrate_concentration", "substrate_concentration_unit"), ("time_value", "time_unit"),
              ("raw_signal", "signal_unit"), ("blank_signal", "signal_unit"), ("corrected_signal", "signal_unit"),
              ("product_concentration", "product_concentration_unit"),
              ("metric_value", "metric_unit"), ("predicted_value", "predicted_unit"))


@dataclass(frozen=True)
class Issue:
    row: int
    field: str
    code: str
    message: str
    severity: str = "ERROR"


@lru_cache(maxsize=9)
def columns(kind):
    if kind not in SPECS:
        raise ValueError("Unknown record kind")
    return tuple(next(csv.reader(io.StringIO(template_bytes(kind).decode("utf-8-sig")))))


def normalize_fields(kind, original, row=1):
    spec = SPECS[kind]
    fields = {key: (None if value is None or isinstance(value, str) and not value.strip() else value)
              for key, value in original.items()}
    for key in columns(kind):
        fields.setdefault(key, None)
    issues = []
    def error(field, code, message):
        issues.append(Issue(row, field, code, message))
    for key in spec.required:
        if fields.get(key) is None:
            error(key, "REQUIRED", "缺少必填字段")
    for key, value in list(fields.items()):
        if value is None:
            continue
        if key.endswith("_id") or key in {"variant_role", "numbering_reference"}:
            if not isinstance(value, str):
                error(key, "TEXT_ID_REQUIRED", "ID/角色必须为文本；不能猜测 Excel 数字 ID 的前导零")
            else:
                fields[key] = value.strip()
        if key in NUMERIC_FIELDS:
            try:
                if isinstance(value, bool) or not Decimal(str(value)).is_finite():
                    raise InvalidOperation
            except (InvalidOperation, ValueError):
                error(key, "FINITE_NUMBER_REQUIRED", "数值必须有限且不含单位；缺失请留空，不填 NaN/Infinity")
        if key.endswith("_utc"):
            try:
                timestamp = datetime.fromisoformat(str(value).replace("Z", "+00:00"))
                if timestamp.utcoffset() != timedelta(0):
                    raise ValueError
            except (ValueError, TypeError):
                error(key, "UTC_REQUIRED", "必须使用带 Z 或 +00:00 的 ISO 8601 UTC；不推测原时区")
    for value_field, unit_field in UNIT_PAIRS:
        if value_field in fields and fields[value_field] is not None and not fields.get(unit_field):
            error(unit_field, "UNIT_REQUIRED", "有数值时必须明确原始单位（无量纲请写 dimensionless）")
        elif value_field in fields and fields[value_field] is not None and not isinstance(fields.get(unit_field), str):
            error(unit_field, "TEXT_UNIT_REQUIRED", "单位必须为明确文本，不把数值或布尔值猜测成单位")
    if kind == "protein_variants":
        if fields.get("variant_role") not in {"WT", "DESIGNED", "CONTROL", "REFERENCE", "OTHER"}:
            error("variant_role", "ROLE", "请选择 WT/DESIGNED/CONTROL/REFERENCE/OTHER，不自动推断角色")
        if fields.get("sequence") is not None:
            try:
                sequence = normalize_sequence(fields["sequence"])
                if sequence.status == "INVALID":
                    error("sequence", "INVALID_SEQUENCE", "序列含无效字符或为空；不删除 gap/stop，不推测残基")
                fields["sequence"] = sequence.normalized
                supplied = fields.get("sequence_sha256")
                if supplied and (not isinstance(supplied, str) or supplied.lower() != sequence.sha256):
                    error("sequence_sha256", "HASH_MISMATCH", "提供的序列 SHA256 与规范化序列不符")
                fields["sequence_sha256"] = sequence.sha256
                fields["sequence_status"] = sequence.status
                fields["normalization_notes"] = list(sequence.notes)
                if sequence.notes:
                    issues.append(Issue(row, "sequence", "NORMALIZATION", ", ".join(sequence.notes), "WARNING"))
            except ValueError as exc:
                error("sequence", "INVALID_SEQUENCE", str(exc))
        if fields.get("mutation_notation_as_reported"):
            issues.append(Issue(row, "mutation_notation_as_reported", "UNVERIFIED_MUTATION", "仅保存原始突变标注，尚未比对/验证编号", "WARNING"))
    if kind == "source_manifest":
        supplied = fields.get("sha256")
        if supplied and (not isinstance(supplied, str) or not re.fullmatch(r"[a-fA-F0-9]{64}", supplied)):
            error("sha256", "INVALID_HASH", "提供方文件哈希须为 64 位十六进制")
        issues.append(Issue(row, "sha256", "REPORTED_PROVENANCE", "提供方清单仅作为报告值保存；不替代导入原件的实算 SHA256", "WARNING"))
    missing_value = {"assay_results": "metric_value", "kinetic_timecourse": "raw_signal", "ai_predictions": "predicted_value"}.get(kind)
    if missing_value and fields.get(missing_value) is None:
        issues.append(Issue(row, missing_value, "MISSING_VALUE", "未提供数值，仍保存缺失记录；不会补零或借用其他证据层的数值", "WARNING"))
    return fields, issues
