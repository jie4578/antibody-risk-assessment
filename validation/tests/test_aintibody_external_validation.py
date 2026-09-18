from __future__ import annotations

import ast
import hashlib
from pathlib import Path

import numpy as np
import pandas as pd

from validation.external_validation.analyze_aintibody import (
    ASSAY_DIRECTIONS,
    ASSAY_COLUMNS,
    CLASSIFICATION_RESULT_COLUMNS,
    FROZEN_RULE_FEATURES,
    _pr_auc,
    _roc_auc,
    compute_assay_results,
    compute_classification_results,
    load_primary_join,
    run_external_validation,
)


ROOT = Path(__file__).resolve().parents[1]
PRIMARY = ROOT / "data/external_validation/aintibody_primary_population.csv"
FEATURES = ROOT / "data/features/aintibody_rule_features.csv"
PROCESSED = ROOT / "data/processed/aintibody_2026.csv"
POPULATION_AUDIT = ROOT / "data/external_validation/aintibody_population_audit.csv"


def _run(tmp_path: Path):
    return run_external_validation(PRIMARY, FEATURES, PROCESSED, POPULATION_AUDIT, tmp_path / "data", tmp_path / "report.md")


def test_primary_join_is_exact_and_duplicate_feature_rows_are_explicit():
    joined, audit = load_primary_join(PRIMARY, FEATURES)
    assert len(joined) == 476
    assert audit["matched_unique_feature_rows"] == 476
    assert audit["matched_raw_feature_rows"] == 479
    assert audit["duplicate_join_rows"] == 3
    assert audit["unmatched_population_rows"] == 0
    assert joined["sequence_hash"].is_unique


def test_positive_class_and_composite_boundary_are_fixed():
    joined, _ = load_primary_join(PRIMARY, FEATURES)
    classification = compute_classification_results(joined)
    labels = joined["derived_binary_status"]
    assert (labels == "DEVELOPABLE").sum() == 370
    assert (labels == "NOT_DEVELOPABLE").sum() == 103
    assert (labels == "BLOCKED_PENDING_ENDPOINT_DEFINITION").sum() == 2
    assert (labels == "BLOCKED_PENDING_REPLICATE_AGGREGATION").sum() == 1
    assert set(classification.columns) == set(CLASSIFICATION_RESULT_COLUMNS)
    assert (classification["positive_n"] == 103).all()
    assert (classification["negative_n"] == 370).all()


def test_fixed_assay_directions_and_control_labels():
    joined, _ = load_primary_join(PRIMARY, FEATURES)
    results = compute_assay_results(joined)
    assert set(results["assay_direction"]) == set(ASSAY_DIRECTIONS.values())
    assert results.loc[results["feature"].isin({"VH_length", "VL_length"}), "control_or_rule"].eq("CONTROL").all()
    assert results.loc[~results["feature"].isin({"VH_length", "VL_length"}), "control_or_rule"].eq("RULE").all()
    assert results.loc[results["feature"] == "VH_rule_penalty", "expected_risk_direction"].tolist()[:5] == ["negative", "negative", "positive", "positive", "positive"]


def test_pairwise_missing_values_and_bh_results_are_deterministic():
    joined, _ = load_primary_join(PRIMARY, FEATURES)
    first = compute_assay_results(joined)
    second = compute_assay_results(joined)
    pd.testing.assert_frame_equal(first, second)
    synthetic = pd.DataFrame({
        "derived_binary_status": ["DEVELOPABLE"] * 4,
        **{feature: [1, 2, np.nan, 4] for feature in FROZEN_RULE_FEATURES},
        "Tm, C": [4, np.nan, 2, 1],
        "Tagg, C": [4, np.nan, 2, 1],
        "HIC RT in gradient (min)": [4, np.nan, 2, 1],
        "average BVP score": [4, np.nan, 2, 1],
        "average dPW": [4, np.nan, 2, 1],
    })
    result = compute_assay_results(synthetic)
    row = result.loc[(result["feature"] == FROZEN_RULE_FEATURES[0]) & (result["assay"] == "Tm")].iloc[0]
    assert row["n"] == 2
    assert np.isclose(row["rho"], -1.0)


def test_auc_implementations_are_deterministic_and_do_not_flip_values():
    labels = np.array([False, True, False, True])
    scores = np.array([0.7, 0.8, 1.0, 1.1])
    assert _roc_auc(labels, scores) == _roc_auc(labels, scores)
    assert _pr_auc(labels, scores) == _pr_auc(labels, scores)
    assert np.isclose(_roc_auc(labels, scores), 0.75)
    assert 0.0 <= _pr_auc(labels, scores) <= 1.0


def test_no_threshold_optimizer_sign_flip_paired_score_or_ml_in_implementation():
    source = (ROOT / "external_validation/analyze_aintibody.py").read_text(encoding="utf-8").lower()
    tree = ast.parse(source)
    imports = " ".join(ast.unparse(node) for node in ast.walk(tree) if isinstance(node, (ast.Import, ast.ImportFrom)))
    assert "sklearn" not in imports
    assert "torch" not in imports
    assert "xgboost" not in imports
    assert "paired_rule_penalty" not in source
    assert "mean_score" not in source
    assert "youden" not in source
    assert "roc_curve" not in source
    assert "gridsearch" not in source
    assert "1 - auc" not in source


def test_classification_direction_is_predeclared_and_scores_are_not_posthoc_flipped():
    joined, _ = load_primary_join(PRIMARY, FEATURES)
    result = compute_classification_results(joined)
    score_rows = result[result["feature"].isin({"VH_calculated_score", "VL_calculated_score"})]
    penalty_rows = result[result["feature"].isin({"VH_rule_penalty", "VL_rule_penalty"})]
    control_rows = result[result["control_or_rule"] == "CONTROL"]
    assert set(score_rows["predictor_direction"]) == {"lower_more_risk"}
    assert set(penalty_rows["predictor_direction"]) == {"higher_more_risk"}
    assert set(control_rows["predictor_direction"]) == {"control_raw"}
    assert not result["notes"].str.contains("1-AUC", regex=False).any()


def test_primary_and_sensitivity_outputs_are_separate_and_negative_findings_preserved(tmp_path):
    _run(tmp_path)
    output = tmp_path / "data"
    assert (output / "aintibody_assay_results.csv").exists()
    assert (output / "aintibody_classification_results.csv").exists()
    assert (output / "aintibody_negative_null_findings.csv").exists()
    assert (output / "aintibody_sensitivity_record_level_assay_results.csv").exists()
    assert (output / "aintibody_sensitivity_context_preserving_assay_results.csv").exists()
    primary = pd.read_csv(output / "aintibody_assay_results.csv")
    negative = pd.read_csv(output / "aintibody_negative_null_findings.csv")
    assert len(primary) == 48 * 5
    assert len(negative) > 0
    assert "SPR" not in " ".join(primary.columns)
    assert "KD" not in " ".join(primary.columns)


def test_full_external_output_is_byte_deterministic_and_raw_inputs_unchanged(tmp_path):
    processed_hash = hashlib.sha256(PROCESSED.read_bytes()).digest()
    first = tmp_path / "first"
    second = tmp_path / "second"
    _run(first)
    _run(second)
    assert hashlib.sha256(PROCESSED.read_bytes()).digest() == processed_hash
    names = sorted(path.name for path in (first / "data").iterdir())
    assert names == sorted(path.name for path in (second / "data").iterdir())
    for name in names:
        assert (first / "data" / name).read_bytes() == (second / "data" / name).read_bytes()
    assert (first / "report.md").read_bytes() == (second / "report.md").read_bytes()
