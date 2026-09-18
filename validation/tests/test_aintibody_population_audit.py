from __future__ import annotations

import ast
import hashlib
import json
from pathlib import Path

import pandas as pd

from validation.external_validation.population_audit import (
    COMPOSITE_SCORE_FIELD,
    PRIMARY_SOURCE_FIELDS,
    classify_duplicate_group,
    derive_composite_status,
    run_population_audit,
)
from validation.external_validation_spec import FROZEN_RULE_FEATURES


ROOT = Path(__file__).resolve().parents[1]
PROCESSED = ROOT / "data/processed/aintibody_2026.csv"
FEATURES = ROOT / "data/features/aintibody_rule_features.csv"


def _run(tmp_path: Path):
    return run_population_audit(PROCESSED, FEATURES, tmp_path / "data", tmp_path / "reports")


def test_all_source_records_are_accounted_for_and_identity_coverage_is_exact(tmp_path):
    result = _run(tmp_path)
    audit = pd.read_csv(tmp_path / "data/aintibody_population_audit.csv", dtype=object)
    assert len(audit) == 715
    assert audit["record_id"].nunique() == 715
    assert audit["population_assignment"].value_counts().to_dict() == {
        "PRIMARY_ELIGIBLE": 517,
        "PRIMARY_INELIGIBLE": 198,
    }
    assert result["summary"]["feature_coverage"]["record_id_intersection"] == 715
    assert result["summary"]["feature_coverage"]["sequence_hash_intersection"] == 686
    assert result["summary"]["feature_coverage"]["record_id_processed_only"] == []
    assert result["summary"]["feature_coverage"]["record_id_feature_only"] == []


def test_duplicate_audit_is_deterministic_and_preserves_context_classes(tmp_path):
    result = _run(tmp_path)
    duplicates = pd.read_csv(tmp_path / "data/aintibody_duplicate_audit.csv", dtype=object)
    assert len(duplicates) == 25
    assert int(duplicates["source_record_count"].astype(int).sum()) == 54
    assert duplicates["duplicate_classification"].value_counts().to_dict() == {
        "DISTINCT_CONTEXT": 21,
        "IDENTICAL_REPLICATE": 2,
        "REPEATED_MEASUREMENT": 2,
    }
    assert result["summary"]["primary_population_rows"] == 476
    assert set(duplicates["outcomes_identical"].astype(str)) <= {"True", "False"}


def test_controls_parental_and_missing_outcomes_are_not_primary(tmp_path):
    _run(tmp_path)
    audit = pd.read_csv(tmp_path / "data/aintibody_population_audit.csv", dtype=object)
    controls = audit[audit["record_type"] == "control"]
    assert len(controls) == 6
    assert set(controls["population_assignment"]) == {"PRIMARY_INELIGIBLE"}
    parental = audit[audit["paper_id"] == "Parental"]
    assert len(parental) == 1
    assert parental.iloc[0]["population_assignment"] == "PRIMARY_INELIGIBLE"
    assert all("control" in reason or "parental" in reason for reason in controls["inclusion_reason"])


def test_repeated_measurement_helper_uses_context_and_outcome_equality_only():
    base = {
        "sequence_hash": "hash",
        "record_type": "submission",
        "challenge": "1",
        "paper_id": "paper",
        "control": "",
    }
    first = dict(base, **{field: "1" for field in PRIMARY_SOURCE_FIELDS.values()}, **{COMPOSITE_SCORE_FIELD: "2"})
    second = dict(base, **{field: "2" for field in PRIMARY_SOURCE_FIELDS.values()}, **{COMPOSITE_SCORE_FIELD: "2"})
    frame = pd.DataFrame([first, second])
    assert classify_duplicate_group(frame) == "REPEATED_MEASUREMENT"
    distinct = frame.copy()
    distinct.loc[1, "challenge"] = "2"
    assert classify_duplicate_group(distinct) == "DISTINCT_CONTEXT"


def test_composite_rule_preserves_missing_as_blocked():
    assert derive_composite_status(3) == "DEVELOPABLE"
    assert derive_composite_status(3.0) == "DEVELOPABLE"
    assert derive_composite_status(4) == "NOT_DEVELOPABLE"
    assert derive_composite_status(None) == "BLOCKED_PENDING_ENDPOINT_DEFINITION"


def test_endpoint_schema_preserves_raw_field_names_directionality_and_firewall(tmp_path):
    result = _run(tmp_path)
    schema = json.loads((tmp_path / "data/aintibody_endpoint_schema.json").read_text(encoding="utf-8"))
    mappings = {item["assay"]: item for item in schema["primary_assays"]}
    assert mappings["HIC"]["source_value_field"] == "HIC RT in gradient (min)"
    assert mappings["BVP"]["source_value_field"] == "average BVP score"
    assert mappings["AC-SINS"]["source_value_field"] == "average dPW"
    assert mappings["HIC"]["direction_of_unfavorable_value"] == "higher_unfavorable"
    assert mappings["Tm"]["direction_of_unfavorable_value"] == "lower_unfavorable"
    assert schema["composite_endpoint"]["source_score_field"] == COMPOSITE_SCORE_FIELD
    assert schema["composite_endpoint"]["original_categorical_status_field"] is None
    assert schema["frozen_feature_firewall"]["feature_values_read"] is False
    assert schema["frozen_feature_firewall"]["feature_names"] == list(FROZEN_RULE_FEATURES)
    assert schema["performance_metrics_generated"] is False
    assert result["schema"]["statistical_analysis_started"] is False


def test_primary_output_does_not_impute_missing_assay_values(tmp_path):
    _run(tmp_path)
    source = pd.read_csv(PROCESSED, dtype=object)
    primary = pd.read_csv(tmp_path / "data/aintibody_primary_population.csv", dtype=object)
    for field in PRIMARY_SOURCE_FIELDS.values():
        source_missing = int(source[field].isna().sum())
        primary_missing = int(primary[field].isna().sum())
        assert primary_missing >= 0
        assert source_missing >= 0
    assert not (primary[list(PRIMARY_SOURCE_FIELDS.values())] == "0").all(axis=None)


def test_processed_source_fields_are_preserved_and_raw_inputs_are_unchanged(tmp_path):
    raw_processed = PROCESSED.read_bytes()
    raw_workbook = (ROOT / "data/raw/aintibody_2026/41587_2026_3238_MOESM4_ESM.xlsx").read_bytes()
    processed = pd.read_csv(PROCESSED, dtype=object)
    required_preserved = set(PRIMARY_SOURCE_FIELDS.values()) | {
        "KD_SPR", "KD_KinExA", "KinExA_Screen_KD_Estimate", "Mean KD (M)",
        "total_developability_score", "source_sheet", "source_row",
    }
    assert required_preserved <= set(processed.columns)
    _run(tmp_path / "first")
    _run(tmp_path / "second")
    assert hashlib.sha256(PROCESSED.read_bytes()).digest() == hashlib.sha256(raw_processed).digest()
    assert hashlib.sha256((ROOT / "data/raw/aintibody_2026/41587_2026_3238_MOESM4_ESM.xlsx").read_bytes()).digest() == hashlib.sha256(raw_workbook).digest()
    for name in (
        "aintibody_population_audit.csv",
        "aintibody_duplicate_audit.csv",
        "aintibody_primary_population.csv",
        "aintibody_endpoint_schema.json",
    ):
        assert (tmp_path / "first/data" / name).read_bytes() == (tmp_path / "second/data" / name).read_bytes()
    assert (tmp_path / "first/reports/population_audit.md").read_bytes() == (tmp_path / "second/reports/population_audit.md").read_bytes()


def test_no_forbidden_analysis_or_model_imports_in_phase_4d1a_implementation():
    source = (ROOT / "external_validation/population_audit.py").read_text(encoding="utf-8").lower()
    tree = ast.parse(source)
    imports = [node for node in ast.walk(tree) if isinstance(node, (ast.Import, ast.ImportFrom))]
    imported = " ".join(ast.unparse(node) for node in imports)
    assert "sklearn" not in imported
    assert "scipy" not in imported
    for forbidden in ("spearman", "roc_auc", "pr_auc", "xgboost", "lightgbm"):
        assert forbidden not in source


def test_only_requested_audit_files_are_generated(tmp_path):
    _run(tmp_path)
    assert sorted(path.name for path in (tmp_path / "data").iterdir()) == [
        "aintibody_duplicate_audit.csv",
        "aintibody_endpoint_schema.json",
        "aintibody_population_audit.csv",
        "aintibody_primary_population.csv",
    ]
    assert sorted(path.name for path in (tmp_path / "reports").iterdir()) == ["population_audit.md"]
