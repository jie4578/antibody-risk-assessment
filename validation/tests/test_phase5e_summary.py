from __future__ import annotations

import csv
import json
import subprocess
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
FINAL = ROOT / "data" / "ml_benchmark" / "entity_exact_v1" / "final_test"
SUMMARY_JSON = ROOT / "phase5_frozen_summary.json"
SUMMARY_MD = ROOT / "PHASE5_ML_BENCHMARK_SUMMARY.md"
MARKER = ROOT / "PHASE5_TEST_EVALUATED.md"


def _rows(name: str) -> list[dict[str, str]]:
    with (FINAL / name).open(newline="", encoding="utf-8") as handle:
        return list(csv.DictReader(handle))


def test_frozen_summary_matches_phase5d_manifest_and_seal() -> None:
    summary = json.loads(SUMMARY_JSON.read_text(encoding="utf-8"))
    manifest = json.loads((FINAL / "final_test_manifest.json").read_text(encoding="utf-8"))
    assert summary["benchmark"] == manifest["benchmark"] == "AINTIBODY_INTERNAL_ENTITY_EXACT_V1"
    assert summary["phase5c_commit"] == manifest["phase5c_commit"]
    assert summary["test_label_sha256"] == manifest["test_label_sha256"]
    assert summary["test_evaluation_number"] == manifest["TEST_EVALUATION_NUMBER"] == 1
    assert summary["bootstrap"] == {
        "resamples": 2000,
        "seed": 20260919,
        "confidence_level": 0.95,
        "valid_n": 2000,
    }
    assert summary["test_population"]["test_n"] == manifest["test_population"]["rows"] == 95
    assert summary["selected_hyperparameters"] == {
        "continuous": manifest["selected_hyperparameters"]["continuous"],
        "classification": manifest["selected_hyperparameters"]["classification"],
    }


def test_all_phase5d_aggregate_results_are_represented() -> None:
    summary = json.loads(SUMMARY_JSON.read_text(encoding="utf-8"))
    continuous = _rows("continuous_test_results.csv")
    classification = _rows("classification_test_results.csv")
    assert len(continuous) == len(summary["continuous_results"]) == 20
    assert len(classification) == len(summary["classification_results"]) == 4
    assert {(row["endpoint"], row["feature_block"]) for row in continuous} == {
        (row["endpoint"], row["feature_block"]) for row in summary["continuous_results"]
    }
    assert {row["feature_block"] for row in classification} == {
        row["feature_block"] for row in summary["classification_results"]
    }
    frozen_continuous = {(row["endpoint"], row["feature_block"]): row for row in summary["continuous_results"]}
    for row in continuous:
        frozen = frozen_continuous[(row["endpoint"], row["feature_block"])]
        for source_name, frozen_name in (
            ("alpha", "alpha"),
            ("validation_spearman", "validation_spearman"),
            ("test_spearman", "test_spearman"),
            ("test_mae", "test_mae"),
            ("test_rmse", "test_rmse"),
            ("test_r2", "test_r2"),
        ):
            assert abs(float(row[source_name]) - float(frozen[frozen_name])) < 1e-12
        assert int(row["test_n"]) == frozen["test_n"]
    frozen_classification = {row["feature_block"]: row for row in summary["classification_results"]}
    for row in classification:
        frozen = frozen_classification[row["feature_block"]]
        for source_name, frozen_name in (
            ("C", "C"),
            ("validation_pr_auc", "validation_pr_auc"),
            ("test_pr_auc", "test_pr_auc"),
            ("validation_roc_auc", "validation_roc_auc"),
            ("test_roc_auc", "test_roc_auc"),
            ("positive_prevalence", "test_prevalence"),
        ):
            assert abs(float(row[source_name]) - float(frozen[frozen_name])) < 1e-12
        assert int(row["test_n"]) == frozen["test_n"]


def test_key_findings_match_existing_outputs() -> None:
    summary = json.loads(SUMMARY_JSON.read_text(encoding="utf-8"))
    hic_esm2 = next(row for row in summary["continuous_results"] if row["endpoint"] == "HIC" and row["feature_block"] == "ESM2")
    assert round(hic_esm2["test_spearman"], 6) == 0.834662
    assert round(hic_esm2["test_r2"], 6) == 0.625834
    assert hic_esm2["test_n"] == 72
    esm2 = next(row for row in summary["classification_results"] if row["feature_block"] == "ESM2")
    assert round(esm2["test_pr_auc"], 6) == 0.611665
    assert round(esm2["test_roc_auc"], 6) == 0.691468
    rule48 = next(row for row in summary["classification_results"] if row["feature_block"] == "RULE48")
    assert round(rule48["test_pr_auc"], 6) == 0.378145
    assert round(rule48["test_roc_auc"], 6) == 0.546627


def test_summary_has_scientific_boundaries_and_no_individual_predictions() -> None:
    summary_text = SUMMARY_MD.read_text(encoding="utf-8")
    marker_text = MARKER.read_text(encoding="utf-8")
    summary_json_text = SUMMARY_JSON.read_text(encoding="utf-8")
    assert "## Supported claims" in summary_text
    assert "## Not supported" in summary_text
    assert "family-independent" in summary_text
    assert "Phase 5 does **not** test generalization to distant antibody" in summary_text
    assert "TEST HAS BEEN OPENED" in marker_text
    assert "test_predictions_" not in summary_json_text
    assert "sequence_hash" not in summary_json_text
    assert "run_phase5d" not in summary_json_text


def test_summary_does_not_add_model_selection_or_test_iteration() -> None:
    summary = json.loads(SUMMARY_JSON.read_text(encoding="utf-8"))
    definitions = summary["model_definitions"]
    assert definitions["preprocessing_fit_population"] == "TRAIN+VALIDATION only"
    assert definitions["test_rows_filtered"] is False
    assert definitions["test_driven_iteration"] is False
    assert definitions["threshold_optimization"] is False
    assert definitions["esm_fine_tuning"] is False


def test_phase5_summary_does_not_rerun_models_and_product_science_is_unchanged() -> None:
    source_files = [SUMMARY_JSON, SUMMARY_MD, MARKER]
    assert all("run_phase5d" not in path.read_text(encoding="utf-8") for path in source_files)
    result = subprocess.run(
        ["git", "diff", "--quiet", "--", "core.py", "scoring.py", "desktop", "agent", "ml"],
        cwd=ROOT,
        check=False,
    )
    assert result.returncode == 0
