"""AIntibody Phase 4D1A population and endpoint schema audit.

The implementation deliberately does not compute any relationship between
frozen rule features and experimental outcomes.  The feature table is read
only for identity/hash coverage checks.  Experimental values are used only to
classify eligibility, audit duplicate equality, and define the pre-registered
endpoint representation.
"""

from __future__ import annotations

import json
from collections import Counter
from pathlib import Path
from typing import Any, Iterable

import pandas as pd

from validation.external_validation_spec import (
    DATASET,
    EXPECTED_DUPLICATE_GROUP_ROWS,
    EXPECTED_INPUT_RECORDS,
    EXPECTED_UNIQUE_SEQUENCE_HASHES,
    FROZEN_RULE_FEATURES,
    PRIMARY_ANALYSIS_UNIT,
    PRIMARY_ASSAYS,
)
from validation.schemas.dataset_schema import clean_text, is_missing, json_safe, missing_summary


PRIMARY_SOURCE_FIELDS = {
    "Tm": "Tm, C",
    "Tagg": "Tagg, C",
    "HIC": "HIC RT in gradient (min)",
    "BVP": "average BVP score",
    "AC-SINS": "average dPW",
}
PRIMARY_STATUS_FIELDS = {
    "Tm": "construct performance, Tm",
    "Tagg": "construct performance, Tagg",
    "HIC": "construct performance, HIC RT",
    "BVP": "construct performance, BVP",
    "AC-SINS": "construct performance, AC-SINS",
}
COMPOSITE_SCORE_FIELD = "total_developability_score"
AFFINITY_FIELDS = (
    "KD_SPR",
    "KD_KinExA",
    "KinExA_Screen_KD_Estimate",
    "Mean KD (M)",
)

CONTEXT_FIELDS = (
    "challenge",
    "record_type",
    "control",
    "paper_id",
    "group",
    "company_group",
    "challenge_sequence",
    "cluster",
    "bucket",
    "organization",
)

DUPLICATE_OUTCOME_FIELDS = tuple(PRIMARY_SOURCE_FIELDS.values()) + (
    COMPOSITE_SCORE_FIELD,
) + tuple(PRIMARY_STATUS_FIELDS.values())

REQUIRED_PROCESSED_FIELDS = {
    "record_id",
    "paper_id",
    "challenge",
    "record_type",
    "VH",
    "VL",
    "sequence_status",
    "sequence_hash",
    "source_sheet",
    "source_row",
    "control",
    *CONTEXT_FIELDS,
    *DUPLICATE_OUTCOME_FIELDS,
    *AFFINITY_FIELDS,
}

SOURCE_WORKBOOKS = (
    "validation/data/raw/aintibody_2026/41587_2026_3238_MOESM3_ESM.xlsx",
    "validation/data/raw/aintibody_2026/41587_2026_3238_MOESM4_ESM.xlsx",
)
SOURCE_SHEETS = (
    "Supplementary Table 1",
    "Supplementary Table 2",
    "Supplementary Table 3",
    "Supplementary Table 4",
    "Supplementary Table 5",
    "Dataset 1",
    "Dataset 2",
    "Dataset 3",
)
OFFICIAL_SOURCE = {
    "article_title": "A blinded, prospective benchmark of in silico antibody discovery anchored to experimental affinity and developability",
    "doi": "10.1038/s41587-026-03238-6",
    "url": "https://www.nature.com/articles/s41587-026-03238-6",
    "publisher": "Nature Biotechnology",
}


def _has_value(value: Any) -> bool:
    return not is_missing(value) and clean_text(value) != ""


def _canonical(value: Any) -> str:
    return "<MISSING>" if not _has_value(value) else clean_text(value)


def _numeric(value: Any) -> float | None:
    if not _has_value(value):
        return None
    converted = pd.to_numeric(pd.Series([value]), errors="coerce").iloc[0]
    if pd.isna(converted):
        return None
    return float(converted)


def _values_equal(left: Any, right: Any) -> bool:
    left_number, right_number = _numeric(left), _numeric(right)
    if left_number is not None and right_number is not None:
        return left_number == right_number
    return _canonical(left) == _canonical(right)


def _context_signature(row: pd.Series) -> tuple[str, ...]:
    return tuple(_canonical(row.get(field)) for field in CONTEXT_FIELDS)


def _outcomes_equal(frame: pd.DataFrame) -> bool:
    if frame.empty:
        return True
    first = frame.iloc[0]
    return all(
        _values_equal(first.get(field), row.get(field))
        for _, row in frame.iloc[1:].iterrows()
        for field in DUPLICATE_OUTCOME_FIELDS
    )


def classify_duplicate_group(frame: pd.DataFrame) -> str:
    """Classify a duplicate hash without using frozen feature values."""

    if len(frame) < 2:
        return "SINGLETON"
    if not all(_has_value(row.get("record_type")) for _, row in frame.iterrows()):
        return "AMBIGUOUS"
    signatures = {_context_signature(row) for _, row in frame.iterrows()}
    if len(signatures) > 1:
        return "DISTINCT_CONTEXT"
    if _outcomes_equal(frame):
        return "IDENTICAL_REPLICATE"
    return "REPEATED_MEASUREMENT"


def _outcome_available(row: pd.Series) -> bool:
    return any(_has_value(row.get(field)) for field in PRIMARY_SOURCE_FIELDS.values()) or _has_value(row.get(COMPOSITE_SCORE_FIELD))


def classify_population_record(row: pd.Series) -> tuple[str, str]:
    """Return a deterministic population assignment and an audit reason."""

    record_type = _canonical(row.get("record_type")).lower()
    paper_id = _canonical(row.get("paper_id")).lower()
    if record_type not in {"submission", "control"}:
        return "AMBIGUOUS", "unrecognized source record_type"
    if record_type == "control" or paper_id == "parental":
        return "PRIMARY_INELIGIBLE", "control or parental record"
    if _canonical(row.get("sequence_status")) != "VALID" or not _has_value(row.get("VH")) or not _has_value(row.get("VL")):
        return "PRIMARY_INELIGIBLE", "missing or invalid VH/VL sequence"
    if not _has_value(row.get("challenge")):
        return "PRIMARY_INELIGIBLE", "submission has no challenge identity"
    if not _outcome_available(row):
        return "PRIMARY_INELIGIBLE", "no measured primary developability outcome"
    return "PRIMARY_ELIGIBLE", "challenge submission with valid VH/VL and measured developability outcome"


def load_inputs(processed_path: str | Path, feature_path: str | Path) -> tuple[pd.DataFrame, pd.DataFrame, dict[str, Any]]:
    """Load normalized records and identity-only feature coverage."""

    processed = pd.read_csv(processed_path, dtype=object)
    # Restrict the feature table to identity columns. No frozen feature value
    # can enter this population/schema audit by accident.
    features = pd.read_csv(feature_path, dtype=object, usecols=["record_id", "sequence_hash"])
    missing = sorted(REQUIRED_PROCESSED_FIELDS - set(processed.columns))
    if missing:
        raise ValueError(f"processed table is missing required fields: {missing}")
    for name, frame in (("processed", processed), ("features", features)):
        if "record_id" not in frame.columns or "sequence_hash" not in frame.columns:
            raise ValueError(f"{name} table lacks identity columns")
        if frame["record_id"].map(clean_text).duplicated().any():
            raise ValueError(f"{name} table contains duplicate record_id values")
    processed_ids = set(processed["record_id"].map(clean_text))
    feature_ids = set(features["record_id"].map(clean_text))
    processed_hashes = set(processed["sequence_hash"].map(clean_text))
    feature_hashes = set(features["sequence_hash"].map(clean_text))
    coverage = {
        "processed_records": len(processed),
        "feature_records": len(features),
        "record_id_intersection": len(processed_ids & feature_ids),
        "record_id_processed_only": sorted(processed_ids - feature_ids),
        "record_id_feature_only": sorted(feature_ids - processed_ids),
        "sequence_hash_intersection": len(processed_hashes & feature_hashes),
        "sequence_hash_processed_only": sorted(processed_hashes - feature_hashes),
        "sequence_hash_feature_only": sorted(feature_hashes - processed_hashes),
        "feature_columns_read": ["record_id", "sequence_hash"],
    }
    return processed, features, coverage


def _duplicate_groups(processed: pd.DataFrame) -> dict[str, pd.DataFrame]:
    groups = {}
    for sequence_hash, frame in processed.groupby("sequence_hash", dropna=False, sort=True):
        key = clean_text(sequence_hash)
        if key and len(frame) > 1:
            groups[key] = frame.sort_values("record_id", kind="stable").reset_index(drop=True)
    return groups


def _json(value: Any) -> str:
    return json.dumps(value, ensure_ascii=False, sort_keys=True, default=str)


def _group_assay_availability(frame: pd.DataFrame) -> dict[str, int]:
    return {
        assay: int(frame[field].map(_has_value).sum())
        for assay, field in PRIMARY_SOURCE_FIELDS.items()
    } | {"composite_score": int(frame[COMPOSITE_SCORE_FIELD].map(_has_value).sum())}


def _resolve_duplicate_group(frame: pd.DataFrame) -> tuple[str, list[str], list[str]]:
    eligible = frame[frame["population_assignment"] == "PRIMARY_ELIGIBLE"]
    if eligible.empty:
        return "INELIGIBLE", [], []
    if len(eligible) == 1:
        return "SINGLETON", [clean_text(eligible.iloc[0]["record_id"])], []
    classification = classify_duplicate_group(eligible)
    ids = [clean_text(value) for value in eligible["record_id"].tolist()]
    if classification in {"DISTINCT_CONTEXT", "AMBIGUOUS"}:
        return classification, [], ids
    representative = sorted(ids)[0]
    return classification, [representative], [record_id for record_id in ids if record_id != representative]


def build_audits(processed: pd.DataFrame, feature_coverage: dict[str, Any]) -> tuple[pd.DataFrame, pd.DataFrame, pd.DataFrame, dict[str, Any]]:
    assignments = processed.apply(classify_population_record, axis=1, result_type="expand")
    assignments.columns = ["population_assignment", "inclusion_reason"]
    audited = processed.copy()
    audited = pd.concat([audited, assignments], axis=1)
    audited["developability_available"] = audited.apply(_outcome_available, axis=1)
    audited["primary_assay_available"] = audited.apply(
        lambda row: any(_has_value(row.get(field)) for field in PRIMARY_SOURCE_FIELDS.values()), axis=1
    )
    audited["composite_score_available"] = audited[COMPOSITE_SCORE_FIELD].map(_has_value)

    # Coverage sets are intentionally recomputed by identity only.  The
    # caller may use these booleans for an audit without importing feature data.
    feature_ids = set(feature_coverage.get("_feature_ids", set()))
    feature_hashes = set(feature_coverage.get("_feature_hashes", set()))
    audited["feature_record_id_match"] = audited["record_id"].map(clean_text).isin(feature_ids)
    audited["feature_sequence_hash_match"] = audited["sequence_hash"].map(clean_text).isin(feature_hashes)

    groups = _duplicate_groups(audited)
    group_classifications: dict[str, str] = {}
    group_resolutions: dict[str, tuple[str, list[str], list[str]]] = {}
    duplicate_rows = []
    for sequence_hash, frame in groups.items():
        classification = classify_duplicate_group(frame)
        resolution, included_ids, excluded_ids = _resolve_duplicate_group(frame)
        group_classifications[sequence_hash] = classification
        group_resolutions[sequence_hash] = (resolution, included_ids, excluded_ids)
        duplicate_rows.append(
            {
                "dataset": DATASET,
                "sequence_hash": sequence_hash,
                "source_record_count": len(frame),
                "record_ids": _json(sorted(clean_text(value) for value in frame["record_id"])),
                "record_type_values": _json(sorted({_canonical(value) for value in frame["record_type"]})),
                "challenge_values": _json(sorted({_canonical(value) for value in frame["challenge"]})),
                "context_signatures": _json(sorted({_context_signature(row) for _, row in frame.iterrows()})),
                "contexts_equivalent": len({_context_signature(row) for _, row in frame.iterrows()}) == 1,
                "outcomes_identical": _outcomes_equal(frame),
                "outcome_fields_compared": _json(list(DUPLICATE_OUTCOME_FIELDS)),
                "duplicate_classification": classification,
                "primary_record_ids": _json(sorted(clean_text(value) for value in frame.loc[frame["population_assignment"] == "PRIMARY_ELIGIBLE", "record_id"])),
                "primary_record_count": int((frame["population_assignment"] == "PRIMARY_ELIGIBLE").sum()),
                "primary_resolution": resolution,
                "included_representative_ids": _json(included_ids),
                "excluded_record_ids": _json(excluded_ids),
                "assay_availability": _json(_group_assay_availability(frame)),
            }
        )

    audited["duplicate_group_size"] = audited["sequence_hash"].map(
        audited["sequence_hash"].map(clean_text).value_counts().to_dict()
    ).fillna(1).astype(int)
    audited["duplicate_classification"] = audited["sequence_hash"].map(clean_text).map(group_classifications).fillna("SINGLETON")
    audited["primary_duplicate_classification"] = "SINGLETON"
    audited["duplicate_resolution_role"] = audited["population_assignment"].map(
        {"PRIMARY_ELIGIBLE": "PRIMARY_INCLUDED", "PRIMARY_INELIGIBLE": "INELIGIBLE", "AMBIGUOUS": "AMBIGUOUS"}
    ).fillna("AMBIGUOUS")
    for sequence_hash, (resolution, included_ids, excluded_ids) in group_resolutions.items():
        mask = audited["sequence_hash"].map(clean_text) == sequence_hash
        audited.loc[mask, "primary_duplicate_classification"] = resolution
        for record_id in included_ids:
            audited.loc[mask & audited["record_id"].map(clean_text).eq(record_id), "duplicate_resolution_role"] = "PRIMARY_INCLUDED"
        for record_id in excluded_ids:
            audited.loc[mask & audited["record_id"].map(clean_text).eq(record_id), "duplicate_resolution_role"] = (
                "PRIMARY_EXCLUDED_DISTINCT_CONTEXT" if resolution in {"DISTINCT_CONTEXT", "AMBIGUOUS"} else "PRIMARY_REPLICATE_COLLAPSED"
            )

    population_columns = [
        "dataset", "record_id", "antibody_id", "paper_id", "challenge", "organization", "record_type",
        "VH", "VL", "sequence_status", "sequence_hash", "population_assignment", "inclusion_reason",
        "developability_available", "primary_assay_available", "composite_score_available",
        "duplicate_group_size", "duplicate_classification", "primary_duplicate_classification",
        "duplicate_resolution_role", "feature_record_id_match", "feature_sequence_hash_match",
    ]
    population_audit = audited[population_columns].copy()

    primary_rows = []
    eligible = audited[audited["population_assignment"] == "PRIMARY_ELIGIBLE"]
    for sequence_hash, frame in eligible.groupby("sequence_hash", sort=True):
        frame = frame.sort_values("record_id", kind="stable").reset_index(drop=True)
        resolution, included_ids, _ = group_resolutions.get(clean_text(sequence_hash), ("SINGLETON", [clean_text(frame.iloc[0]["record_id"])], []))
        if not included_ids:
            continue
        source_ids = [clean_text(value) for value in frame["record_id"].tolist()]
        representative = sorted(included_ids)[0]
        row: dict[str, Any] = {
            "dataset": DATASET,
            "sequence_hash": clean_text(sequence_hash),
            "representative_record_id": representative,
            "source_record_count": len(frame),
            "source_record_ids": _json(source_ids),
            "duplicate_resolution": resolution,
            "VH": clean_text(frame.iloc[0]["VH"]),
            "VL": clean_text(frame.iloc[0]["VL"]),
            "record_type": _json(sorted({_canonical(value) for value in frame["record_type"]})),
            "challenge": _json(sorted({_canonical(value) for value in frame["challenge"]})),
            "original_status": "",
            "original_status_source": "No composite categorical status field is present in Supplementary Data 3",
            "aggregation_method": "none" if len(frame) == 1 else "median for continuous assay fields; composite score retained only when equal",
            "replicate_count": len(frame),
        }
        assay_metadata = {}
        for assay, source_field in PRIMARY_SOURCE_FIELDS.items():
            numbers = [value for value in (_numeric(item) for item in frame[source_field]) if value is not None]
            median = float(pd.Series(numbers).median()) if numbers else None
            row[source_field] = median
            assay_metadata[assay] = {
                "source_field": source_field,
                "status_field": PRIMARY_STATUS_FIELDS[assay],
                "n": len(numbers),
                "min": min(numbers) if numbers else None,
                "max": max(numbers) if numbers else None,
                "median": median,
            }
            statuses = sorted({_canonical(value) for value in frame[PRIMARY_STATUS_FIELDS[assay]] if _has_value(value)})
            row[f"{assay}_original_status"] = "; ".join(statuses)
        composite_numbers = [value for value in (_numeric(item) for item in frame[COMPOSITE_SCORE_FIELD]) if value is not None]
        composite_equal = len(set(composite_numbers)) <= 1
        row[COMPOSITE_SCORE_FIELD] = composite_numbers[0] if composite_numbers and composite_equal else None
        row["composite_source_value_count"] = len(composite_numbers)
        row["composite_source_values_equal"] = composite_equal
        row["composite_source_values_json"] = _json(composite_numbers)
        row["derived_binary_status"] = derive_composite_status(row[COMPOSITE_SCORE_FIELD]) if composite_equal else "BLOCKED_PENDING_REPLICATE_AGGREGATION"
        row["derivation_rule"] = "published total_developability_score <= 3 => DEVELOPABLE; > 3 => NOT_DEVELOPABLE; missing/ambiguous => blocked"
        row["assay_metadata_json"] = _json(assay_metadata)
        primary_rows.append(row)
    primary_population = pd.DataFrame(primary_rows)

    summary = {
        "dataset": DATASET,
        "source_workbooks": list(SOURCE_WORKBOOKS),
        "source_sheets": list(SOURCE_SHEETS),
        "source_sheet_used": "Dataset 3",
        "input_records": len(processed),
        "unique_record_ids": int(processed["record_id"].map(clean_text).nunique()),
        "unique_antibody_ids": int(processed["antibody_id"].map(clean_text).nunique()),
        "unique_sequence_hashes": int(processed["sequence_hash"].map(clean_text).nunique()),
        "duplicate_group_rows": int(sum(len(frame) for frame in groups.values())),
        "duplicate_group_count": len(groups),
        "population_counts": {str(key): int(value) for key, value in audited["population_assignment"].value_counts().to_dict().items()},
        "record_type_counts": {str(key): int(value) for key, value in audited["record_type"].map(_canonical).value_counts().to_dict().items()},
        "parental_marker_count": int(audited["paper_id"].map(lambda value: _canonical(value).lower() == "parental").sum()),
        "primary_population_rows": len(primary_population),
        "primary_population_unique_hashes": int(primary_population["sequence_hash"].nunique()) if not primary_population.empty else 0,
        "duplicate_classification_counts": Counter(row["duplicate_classification"] for row in duplicate_rows),
        "feature_coverage": {key: value for key, value in feature_coverage.items() if not key.startswith("_")},
        "primary_assay_source_fields": dict(PRIMARY_SOURCE_FIELDS),
        "primary_assay_missingness_source": {field: value for field, value in missing_summary(processed[list(PRIMARY_SOURCE_FIELDS.values())]).items()},
        "primary_assay_missingness_population": {field: value for field, value in missing_summary(audited.loc[audited["population_assignment"] == "PRIMARY_ELIGIBLE", list(PRIMARY_SOURCE_FIELDS.values())]).items()},
        "primary_assay_missingness_unique_population": {field: value for field, value in missing_summary(primary_population[list(PRIMARY_SOURCE_FIELDS.values())]).items()} if not primary_population.empty else {},
        "no_statistical_performance_output": True,
    }
    return population_audit, pd.DataFrame(duplicate_rows), primary_population, summary


def derive_composite_status(score: Any) -> str:
    value = _numeric(score)
    if value is None:
        return "BLOCKED_PENDING_ENDPOINT_DEFINITION"
    return "DEVELOPABLE" if value <= 3 else "NOT_DEVELOPABLE"


def endpoint_schema(summary: dict[str, Any]) -> dict[str, Any]:
    return {
        "dataset": DATASET,
        "official_source": OFFICIAL_SOURCE,
        "source_workbook": SOURCE_WORKBOOKS[-1],
        "source_sheet": "Dataset 3",
        "analysis_unit": PRIMARY_ANALYSIS_UNIT,
        "population_definition": "Eligible AIntibody challenge antibody submissions with valid VH/VL sequences and at least one measured primary developability outcome.",
        "record_type_policy": {
            "submission": "eligible only when challenge identity, valid VH/VL, and a primary outcome are present",
            "control": "excluded from the primary population; retained in the record-level audit",
            "parental_marker": "paper_id == Parental is excluded as a control/parental record",
            "reference_or_other": "no separate source category was present in the normalized Dataset 3 record_type field",
        },
        "primary_assays": [
            {
                "assay": assay,
                "source_value_field": field,
                "source_status_field": PRIMARY_STATUS_FIELDS[assay],
                "direction_of_unfavorable_value": "lower_unfavorable" if assay in {"Tm", "Tagg"} else "higher_unfavorable",
                "source_note": (
                    "The normalized workbook field is preserved exactly as average dPW; the paper describes the AC-SINS endpoint in its dPW-adjusted form."
                    if assay == "AC-SINS" else ""
                ),
            }
            for assay, field in PRIMARY_SOURCE_FIELDS.items()
        ],
        "composite_endpoint": {
            "source_score_field": COMPOSITE_SCORE_FIELD,
            "original_categorical_status_field": None,
            "published_rule": "total_developability_score <= 3 is DEVELOPABLE; > 3 is NOT_DEVELOPABLE (fail/questionable composite outcome)",
            "missing_or_ambiguous_policy": "do not derive; retain missing and mark blocked",
            "derived_status_function": "derive_composite_status",
        },
        "affinity_fields_secondary": list(AFFINITY_FIELDS),
        "duplicate_policy": {
            "identical_replicate": "retain deterministic representative and record source IDs",
            "repeated_measurement": "aggregate continuous primary assay fields by median; preserve replicate metadata; retain composite score only when equal",
            "distinct_context": "do not merge; exclude the sequence hash from the primary unique population",
            "ambiguous": "do not resolve silently; exclude from the primary unique population",
        },
        "frozen_feature_firewall": {
            "feature_names": list(FROZEN_RULE_FEATURES),
            "feature_values_read": False,
            "identity_coverage_only": True,
            "record_id_coverage": summary["feature_coverage"].get("record_id_intersection"),
            "sequence_hash_coverage": summary["feature_coverage"].get("sequence_hash_intersection"),
        },
        "missing_data_policy": "preserve missing values; no imputation or zero filling",
        "performance_metrics_generated": False,
        "statistical_analysis_started": False,
    }


def _render_report(summary: dict[str, Any], duplicate_audit: pd.DataFrame, schema: dict[str, Any]) -> str:
    population = summary["population_counts"]
    duplicate_counts = dict(summary["duplicate_classification_counts"])
    lines = [
        "# AIntibody 2026 Phase 4D1A population and endpoint schema audit",
        "",
        "This report freezes population and endpoint handling only. It contains no feature/outcome association or classification result.",
        "",
        "## Source and record identity",
        "",
        f"- Official article: [{OFFICIAL_SOURCE['article_title']}]({OFFICIAL_SOURCE['url']})",
        f"- DOI: `{OFFICIAL_SOURCE['doi']}`",
        f"- Source sheet used: `{summary['source_sheet_used']}`",
        f"- Normalized input records: **{summary['input_records']}**",
        f"- Unique record IDs: **{summary['unique_record_ids']}**",
        f"- Unique antibody IDs: **{summary['unique_antibody_ids']}**",
        f"- Unique VH/VL sequence hashes: **{summary['unique_sequence_hashes']}**",
        f"- Duplicate-group rows: **{summary['duplicate_group_rows']}** across **{summary['duplicate_group_count']}** hashes",
        "",
        "## Population assignment",
        "",
        f"- PRIMARY_ELIGIBLE: **{population.get('PRIMARY_ELIGIBLE', 0)}** source records",
        f"- PRIMARY_INELIGIBLE: **{population.get('PRIMARY_INELIGIBLE', 0)}** source records",
        f"- AMBIGUOUS: **{population.get('AMBIGUOUS', 0)}** source records",
        f"- Primary unique-sequence rows after preregistered duplicate handling: **{summary['primary_population_rows']}**",
        f"- Exact source record types: `{json.dumps(summary['record_type_counts'], ensure_ascii=False, sort_keys=True)}`",
        f"- `paper_id == Parental` marker rows: **{summary['parental_marker_count']}**",
        "- No separate source category named `reference` or `other` was present in the normalized record-type field; no such category was invented.",
        "",
        "## Duplicate audit",
        "",
        f"- IDENTICAL_REPLICATE groups: **{duplicate_counts.get('IDENTICAL_REPLICATE', 0)}**",
        f"- REPEATED_MEASUREMENT groups: **{duplicate_counts.get('REPEATED_MEASUREMENT', 0)}**",
        f"- DISTINCT_CONTEXT groups: **{duplicate_counts.get('DISTINCT_CONTEXT', 0)}**",
        f"- AMBIGUOUS groups: **{duplicate_counts.get('AMBIGUOUS', 0)}**",
        "- Identical replicates use a deterministic representative; repeated measurements use median only for continuous primary assay fields; distinct contexts are not merged.",
        "",
        "## Primary endpoint schema",
        "",
    ]
    for item in schema["primary_assays"]:
        lines.append(
            f"- **{item['assay']}**: value `{item['source_value_field']}`; status `{item['source_status_field']}`; direction `{item['direction_of_unfavorable_value']}`."
        )
    lines.extend([
        f"- Composite source field: `{COMPOSITE_SCORE_FIELD}`.",
        "- No composite categorical status column was present in the normalized source table.",
        "- Published composite rule: score <= 3 is DEVELOPABLE; score > 3 is NOT_DEVELOPABLE; missing or ambiguous scores remain blocked.",
        "- Affinity fields are preserved as secondary fields and are not used to redefine the primary developability endpoint.",
        "",
        "## Missingness and firewall",
        "",
        f"- Source primary-assay missingness: `{json.dumps(summary['primary_assay_missingness_source'], ensure_ascii=False, sort_keys=True)}`",
        f"- Primary-population primary-assay missingness: `{json.dumps(summary['primary_assay_missingness_population'], ensure_ascii=False, sort_keys=True)}`",
        f"- Unique-primary-population primary-assay missingness: `{json.dumps(summary['primary_assay_missingness_unique_population'], ensure_ascii=False, sort_keys=True)}`",
        "- The frozen feature file was checked only for record_id and sequence_hash coverage; feature values were not read, joined, ranked, or analyzed.",
        "- No correlation, classification, threshold optimization, ML, or other outcome-performance output was generated.",
        "",
        "## Audit artifacts",
        "",
        "- `aintibody_population_audit.csv`: one row per normalized source record.",
        "- `aintibody_duplicate_audit.csv`: one row per duplicate sequence-hash group; no raw outcome values are emitted.",
        "- `aintibody_primary_population.csv`: deterministic unique-sequence population after the preregistered duplicate policy.",
        "- `aintibody_endpoint_schema.json`: machine-readable field mapping, directionality, endpoint and firewall rules.",
    ])
    return "\n".join(lines) + "\n"


def run_population_audit(processed_path: str | Path, feature_path: str | Path, output_dir: str | Path, report_dir: str | Path) -> dict[str, Any]:
    processed, features, coverage = load_inputs(processed_path, feature_path)
    coverage["_feature_ids"] = set(features["record_id"].map(clean_text))
    coverage["_feature_hashes"] = set(features["sequence_hash"].map(clean_text))
    population_audit, duplicate_audit, primary_population, summary = build_audits(processed, coverage)
    schema = endpoint_schema(summary)
    output_path = Path(output_dir)
    report_path = Path(report_dir)
    output_path.mkdir(parents=True, exist_ok=True)
    report_path.mkdir(parents=True, exist_ok=True)
    population_audit.to_csv(output_path / "aintibody_population_audit.csv", index=False)
    duplicate_audit.to_csv(output_path / "aintibody_duplicate_audit.csv", index=False)
    primary_population.to_csv(output_path / "aintibody_primary_population.csv", index=False)
    (output_path / "aintibody_endpoint_schema.json").write_text(json.dumps(schema, indent=2, ensure_ascii=False, default=str) + "\n", encoding="utf-8")
    (report_path / "population_audit.md").write_text(_render_report(summary, duplicate_audit, schema), encoding="utf-8")
    return {"summary": summary, "schema": schema}


def main() -> None:
    root = Path(__file__).resolve().parents[2]
    run_population_audit(
        root / "validation/data/processed/aintibody_2026.csv",
        root / "validation/data/features/aintibody_rule_features.csv",
        root / "validation/data/external_validation",
        root / "validation/reports/aintibody_external",
    )


if __name__ == "__main__":
    main()
