"""Extract deterministic features from the frozen production rule system.

The extractor reads only identity and VH/VL sequence columns from a Phase 4A
processed table. Experimental assay values are deliberately not accessed.
"""

from __future__ import annotations

import json
import math
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Mapping

import pandas as pd

from core import analyze_sequence, normalize_sequence
from scoring import CDR_REGIONS, PTM_CATEGORIES, compute_risk_score
from validation.schemas.dataset_schema import clean_text, sequence_hash as make_sequence_hash

from .feature_schema import (
    ANTIBODY_COLUMNS,
    CDR_ARGS,
    CDR_REGIONS,
    CATEGORY_FIELD_MAP,
    CHAIN_COLUMNS,
    DATASET_FEATURE_FILENAMES,
    REGION_COUNT_FIELDS,
    RISK_SITE_COLUMNS,
    feature_dictionary_frame,
)


FEATURE_INPUT_COLUMNS = (
    "dataset",
    "record_id",
    "antibody_id",
    "VH",
    "VL",
    "sequence_status",
    "sequence_hash",
)


@dataclass(frozen=True)
class FeatureTables:
    chain: pd.DataFrame
    antibody: pd.DataFrame
    risk_sites: pd.DataFrame
    audit: dict[str, Any]


def _position_start(position: Any) -> int:
    try:
        return int(str(position).split("-", 1)[0])
    except (TypeError, ValueError):
        return 0


def _risk_counts(risks: list[Any]) -> dict[str, int]:
    cdr_risks = [risk for risk in risks if risk.region in CDR_REGIONS]
    counts = {
        "total_sites": len(risks),
        "cdr_sites": len(cdr_risks),
        "framework_sites": len(risks) - len(cdr_risks),
        "ptm_sites": sum(risk.category in PTM_CATEGORIES for risk in risks),
        "liability_sites": sum(risk.category not in PTM_CATEGORIES for risk in risks),
    }
    for category, field in CATEGORY_FIELD_MAP.items():
        counts[field] = sum(risk.category == category for risk in risks)
        counts[f"cdr_{field}"] = sum(risk.category == category and risk.region in CDR_REGIONS for risk in risks)
    return counts


def _safe_number(value: Any) -> Any:
    if value is None:
        return float("nan")
    try:
        if pd.isna(value):
            return float("nan")
    except (TypeError, ValueError):
        pass
    if hasattr(value, "item"):
        return value.item()
    return value


def _analyze_chain(sequence: Any, chain: str) -> dict[str, Any]:
    normalized = normalize_sequence(clean_text(sequence))
    try:
        result = analyze_sequence(normalized, *CDR_ARGS)
        score = compute_risk_score([(chain, result)])
        errors = list(result.errors)
        status = "VALID" if not errors else ("MISSING" if not normalized else "INVALID")
        analysis_status = "SUCCESS" if not errors else "FAILED"
        risks = list(result.risks) if not errors else []
    except Exception as exc:  # keep one bad record visible to the audit
        result = None
        score = None
        errors = [f"{type(exc).__name__}: {exc}"]
        status = "MISSING" if not normalized else "INVALID"
        analysis_status = "FAILED"
        risks = []

    counts = _risk_counts(risks)
    calculated_score = _safe_number(score.overall_score) if score is not None else float("nan")
    if isinstance(calculated_score, float) and math.isnan(calculated_score):
        rule_penalty = float("nan")
    else:
        rule_penalty = 100.0 - float(calculated_score)

    return {
        "sequence_length": result.sequence_length if result is not None else 0,
        "sequence_status": status,
        "analysis_status": analysis_status,
        "analysis_error": "; ".join(str(error) for error in errors),
        "calculated_score": calculated_score,
        "risk_level": score.risk_level if score is not None else "N/A",
        "rule_penalty": rule_penalty,
        **counts,
        "risks": risks,
    }


def _identity(row: Mapping[str, Any], index: int, dataset: str | None) -> dict[str, str]:
    record_id = clean_text(row.get("record_id")) or clean_text(row.get("antibody_id")) or f"row-{index + 1:06d}"
    antibody_id = clean_text(row.get("antibody_id")) or record_id
    vh = normalize_sequence(clean_text(row.get("VH")))
    vl = normalize_sequence(clean_text(row.get("VL")))
    return {
        "dataset": clean_text(row.get("dataset")) or dataset or "unknown",
        "record_id": record_id,
        "antibody_id": antibody_id,
        "sequence_hash": clean_text(row.get("sequence_hash")) or make_sequence_hash(vh, vl),
    }


def extract_features(frame: pd.DataFrame, *, dataset: str | None = None) -> FeatureTables:
    """Analyze every input record and return chain, antibody and risk tables.

    Only ``FEATURE_INPUT_COLUMNS`` are read. Extra source columns, including
    experimental assay columns, are intentionally ignored.
    """

    missing = [column for column in ("VH", "VL") if column not in frame.columns]
    if missing:
        raise ValueError(f"feature extraction requires columns: {', '.join(missing)}")

    # Select only the allow-listed identity and sequence fields. This makes
    # the experimental-label firewall structural: assay columns never enter
    # the extraction loop, even when they are present in the source table.
    input_frame = frame.loc[:, [column for column in FEATURE_INPUT_COLUMNS if column in frame.columns]].copy()

    chain_rows: list[dict[str, Any]] = []
    antibody_rows: list[dict[str, Any]] = []
    risk_rows: list[dict[str, Any]] = []

    for index, source_row in input_frame.reset_index(drop=True).iterrows():
        row = source_row.to_dict()
        identity = _identity(row, index, dataset)
        chain_results = {
            "VH": _analyze_chain(row.get("VH"), "VH"),
            "VL": _analyze_chain(row.get("VL"), "VL"),
        }
        for chain in ("VH", "VL"):
            result = chain_results[chain]
            chain_row = {
                **identity,
                "chain": chain,
                **{field: result[field] for field in CHAIN_COLUMNS if field not in identity and field not in {"chain", "risks"}},
            }
            chain_rows.append(chain_row)
            for risk in result["risks"]:
                risk_rows.append({
                    **identity,
                    "chain": chain,
                    "position": risk.position,
                    "motif": risk.motif,
                    "category": risk.category,
                    "region": risk.region,
                    "description": risk.description,
                    "context": risk.context,
                    "evidence_level": risk.evidence_level,
                })

        vh = chain_results["VH"]
        vl = chain_results["VL"]
        successful = [result["analysis_status"] == "SUCCESS" for result in (vh, vl)]
        if all(successful):
            analysis_status = "SUCCESS"
        elif any(successful):
            analysis_status = "PARTIAL"
        else:
            analysis_status = "FAILED"
        errors = [f"{chain}: {result['analysis_error']}" for chain, result in (("VH", vh), ("VL", vl)) if result["analysis_error"]]
        pair_status = clean_text(row.get("sequence_status"))
        if not pair_status:
            pair_status = "VALID" if all(result["sequence_status"] == "VALID" for result in (vh, vl)) else ("PARTIAL" if any(result["sequence_status"] == "VALID" for result in (vh, vl)) else "INVALID")

        antibody_row: dict[str, Any] = {
            **identity,
            "sequence_status": pair_status,
            "analysis_status": analysis_status,
            "analysis_error": "; ".join(errors),
        }
        for chain, result in (("VH", vh), ("VL", vl)):
            antibody_row[f"{chain}_length"] = result["sequence_length"]
            for field in ("calculated_score", "rule_penalty", *REGION_COUNT_FIELDS, *CATEGORY_FIELD_MAP.values(), *(f"cdr_{field}" for field in CATEGORY_FIELD_MAP.values())):
                antibody_row[f"{chain}_{field}"] = result[field]
        for field in ("total_sites", "cdr_sites", "framework_sites", "ptm_sites", "liability_sites", *CATEGORY_FIELD_MAP.values(), *(f"cdr_{field}" for field in CATEGORY_FIELD_MAP.values())):
            left = antibody_row[f"VH_{field}"]
            right = antibody_row[f"VL_{field}"]
            antibody_row[f"{field}_combined"] = int(left) + int(right)
        antibody_rows.append(antibody_row)

    chain = pd.DataFrame(chain_rows, columns=CHAIN_COLUMNS)
    antibody = pd.DataFrame(antibody_rows, columns=ANTIBODY_COLUMNS)
    risk_sites = pd.DataFrame(risk_rows, columns=RISK_SITE_COLUMNS)

    category_counts = risk_sites["category"].value_counts().to_dict() if not risk_sites.empty else {}
    audit = {
        "dataset": dataset or (clean_text(input_frame.iloc[0].get("dataset")) if len(input_frame) else "unknown"),
        "input_records": int(len(input_frame)),
        "output_chain_records": int(len(chain)),
        "output_antibody_records": int(len(antibody)),
        "successful_analyses": int((antibody["analysis_status"] == "SUCCESS").sum()) if len(antibody) else 0,
        "partial_analyses": int((antibody["analysis_status"] == "PARTIAL").sum()) if len(antibody) else 0,
        "failed_analyses": int((antibody["analysis_status"] == "FAILED").sum()) if len(antibody) else 0,
        "unique_sequence_hashes": int(antibody["sequence_hash"].nunique(dropna=False)) if len(antibody) else 0,
        "duplicate_sequence_records": int(antibody["sequence_hash"].duplicated(keep=False).sum()) if len(antibody) else 0,
        "duplicate_sequence_excess_rows": int(len(antibody) - antibody["sequence_hash"].nunique(dropna=False)) if len(antibody) else 0,
        "risk_site_rows": int(len(risk_sites)),
        "risk_site_counts_by_category": {str(key): int(value) for key, value in category_counts.items()},
        "feature_input_columns_used": list(FEATURE_INPUT_COLUMNS),
        "experimental_label_values_read": False,
        "chain_feature_missingness": _missingness(chain),
        "antibody_feature_missingness": _missingness(antibody),
    }
    return FeatureTables(chain=chain, antibody=antibody, risk_sites=risk_sites, audit=audit)


def _missingness(frame: pd.DataFrame) -> dict[str, dict[str, int]]:
    result: dict[str, dict[str, int]] = {}
    for column in frame.columns:
        missing = int(frame[column].isna().sum())
        result[str(column)] = {"non_missing_n": int(len(frame) - missing), "missing_n": missing}
    return result


def _audit_markdown(audit: dict[str, Any]) -> str:
    return "\n".join([
        f"# {audit['dataset']} frozen rule-feature audit",
        "",
        f"- Input records: {audit['input_records']}",
        f"- Output antibody records: {audit['output_antibody_records']}",
        f"- Output chain records: {audit['output_chain_records']}",
        f"- Successful analyses: {audit['successful_analyses']}",
        f"- Partial analyses: {audit['partial_analyses']}",
        f"- Failed analyses: {audit['failed_analyses']}",
        f"- Unique sequence hashes: {audit['unique_sequence_hashes']}",
        f"- Duplicate sequence records: {audit['duplicate_sequence_records']}",
        f"- Duplicate sequence excess rows: {audit['duplicate_sequence_excess_rows']}",
        f"- Risk-site rows: {audit['risk_site_rows']}",
        "",
        "Extraction uses only record identity and VH/VL sequences. Experimental assay values are not read and are not used for feature decisions.",
        "",
    ])


def write_feature_outputs(
    input_paths: Mapping[str, str | Path],
    *,
    output_dir: str | Path,
    report_dir: str | Path,
) -> dict[str, FeatureTables]:
    """Generate ignored feature CSVs and prediction-side audit reports."""

    output_root = Path(output_dir)
    report_root = Path(report_dir)
    output_root.mkdir(parents=True, exist_ok=True)
    report_root.mkdir(parents=True, exist_ok=True)
    results: dict[str, FeatureTables] = {}
    for dataset, input_path in input_paths.items():
        frame = pd.read_csv(input_path)
        tables = extract_features(frame, dataset=dataset)
        results[dataset] = tables
        feature_filename = DATASET_FEATURE_FILENAMES.get(dataset, f"{dataset}_rule_features.csv")
        tables.antibody.to_csv(output_root / feature_filename, index=False)
        tables.chain.to_csv(output_root / f"{dataset}_chain_rule_features.csv", index=False)
        tables.risk_sites.to_csv(output_root / f"{dataset}_risk_sites.csv", index=False)
        (report_root / f"{dataset}_feature_audit.json").write_text(json.dumps(tables.audit, indent=2, ensure_ascii=False), encoding="utf-8")
        (report_root / f"{dataset}_feature_audit.md").write_text(_audit_markdown(tables.audit), encoding="utf-8")

    if results:
        pd.concat([tables.chain for tables in results.values()], ignore_index=True).to_csv(output_root / "chain_rule_features.csv", index=False)
        pd.concat([tables.risk_sites for tables in results.values()], ignore_index=True).to_csv(output_root / "risk_sites.csv", index=False)
    feature_dictionary_frame().to_csv(output_root / "rule_feature_dictionary.csv", index=False)
    return results
