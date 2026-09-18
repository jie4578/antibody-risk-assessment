from __future__ import annotations

from pathlib import Path

from validation.external_validation_spec import (
    DATASET,
    EXPECTED_DUPLICATE_GROUP_ROWS,
    EXPECTED_INPUT_RECORDS,
    EXPECTED_UNIQUE_SEQUENCE_HASHES,
    FROZEN_RULE_FEATURES,
    PHASE_4B_FEATURE_CHECKPOINT,
    PHASE_4C_BENCHMARK_CHECKPOINT,
    FROZEN_SCIENTIFIC_BASELINE,
    ML_TRAINING_PROHIBITED,
    NO_PAIRED_SCORE,
    PRIMARY_ASSAYS,
    PRIMARY_CLASSIFICATION_METRICS,
    PRIMARY_ANALYSIS_UNIT,
    THRESHOLD_OPTIMIZATION_PROHIBITED,
)


ROOT = Path(__file__).resolve().parents[1]
PROTOCOL = ROOT / "external_validation_protocol.md"


def test_protocol_records_frozen_commits_and_dataset_snapshot():
    text = PROTOCOL.read_text(encoding="utf-8")
    assert FROZEN_SCIENTIFIC_BASELINE in text
    assert PHASE_4B_FEATURE_CHECKPOINT in text
    assert PHASE_4C_BENCHMARK_CHECKPOINT in text
    assert DATASET in text
    assert f"{EXPECTED_INPUT_RECORDS} records" in text
    assert f"{EXPECTED_UNIQUE_SEQUENCE_HASHES} unique VH/VL hashes" in text
    assert f"{EXPECTED_DUPLICATE_GROUP_ROWS} duplicate-group rows" in text


def test_frozen_feature_set_is_exact_and_controls_are_explicit():
    assert len(FROZEN_RULE_FEATURES) == 48
    assert len(set(FROZEN_RULE_FEATURES)) == 48
    assert FROZEN_RULE_FEATURES[-2:] == ("VH_length", "VL_length")
    assert "VH_rule_penalty" in FROZEN_RULE_FEATURES
    assert "VL_rule_penalty" in FROZEN_RULE_FEATURES
    text = PROTOCOL.read_text(encoding="utf-8")
    for feature in FROZEN_RULE_FEATURES:
        assert feature in text
    assert "control/descriptive" in text


def test_primary_endpoints_and_statistics_are_preregistered():
    text = PROTOCOL.read_text(encoding="utf-8")
    for assay in PRIMARY_ASSAYS:
        assert assay in text
    assert PRIMARY_ANALYSIS_UNIT in text
    assert "Spearman rho" in text
    assert "q < 0.05" in text
    assert "q < 0.10" in text
    for metric in PRIMARY_CLASSIFICATION_METRICS:
        assert metric in text


def test_duplicate_policy_and_composite_endpoint_policy_are_explicit():
    text = PROTOCOL.read_text(encoding="utf-8")
    required_phrases = (
        "identical experimental values",
        "median",
        "replicate count",
        "do NOT merge",
        "exclude that sequence from PRIMARY",
        "paper-provided categorical developability status",
        "published paper rule",
        "Never overwrite original data",
    )
    for phrase in required_phrases:
        assert phrase in text


def test_no_paired_score_or_outcome_driven_optimization_is_preregistered():
    assert NO_PAIRED_SCORE is True
    assert THRESHOLD_OPTIMIZATION_PROHIBITED is True
    assert ML_TRAINING_PROHIBITED is True
    text = PROTOCOL.read_text(encoding="utf-8")
    assert "Do NOT average" in text
    assert "Do NOT optimize a new threshold" in text
    assert "Do NOT fit XGBoost" in text
    assert "Do NOT select features after viewing outcomes" in text


def test_preregistration_has_no_external_analysis_runner_or_result_files():
    assert not (ROOT / "run_external_validation.py").exists()
    audit_dir = ROOT / "data/external_validation"
    report_dir = ROOT / "reports/aintibody_external"
    if audit_dir.exists():
        allowed_outputs = {
            "aintibody_duplicate_audit.csv",
            "aintibody_endpoint_schema.json",
            "aintibody_population_audit.csv",
            "aintibody_primary_population.csv",
            "aintibody_analysis_summary.json",
            "aintibody_assay_results.csv",
            "aintibody_classification_results.csv",
            "aintibody_join_audit.json",
            "aintibody_negative_null_findings.csv",
            "aintibody_qvalue_matrix.csv",
            "aintibody_spearman_matrix.csv",
            "aintibody_top10_associations.csv",
            "aintibody_top_pr_auc.csv",
            "aintibody_top_roc_auc.csv",
            "aintibody_sensitivity_record_level_assay_results.csv",
            "aintibody_sensitivity_record_level_classification_results.csv",
            "aintibody_sensitivity_context_preserving_assay_results.csv",
            "aintibody_sensitivity_context_preserving_classification_results.csv",
            "aintibody_hic_robustness.csv",
            "aintibody_hic_length_strata.csv",
            "aintibody_hic_specificity.csv",
            "aintibody_logistic_adjustment.csv",
            "aintibody_hic_robustness_summary.json",
        }
        assert {path.name for path in audit_dir.iterdir()} <= allowed_outputs
    if report_dir.exists():
        assert {path.name for path in report_dir.iterdir()} <= {
            "population_audit.md",
            "report.md",
            "hic_robustness_report.md",
            "phase4d2_VH_oxidation_count.png",
            "phase4d2_oxidation_count_combined.png",
            "phase4d2_VH_cdr_oxidation_count.png",
            "phase4d2_cdr_oxidation_count_combined.png",
        }
