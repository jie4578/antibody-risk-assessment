from __future__ import annotations

import inspect
from pathlib import Path

import numpy as np
import pandas as pd
import pytest

from validation.benchmark import jain_spearman
from validation.benchmark.jain_spearman import (
    BENCHMARK_FEATURES,
    JAIN_ASSAYS,
    SCORE_FEATURES,
    assay_missingness,
    benjamini_hochberg,
    compute_spearman_results,
    effect_size_label,
    load_assay_directions,
    load_jain_inputs,
    rank_top_associations,
)


ROOT = Path(__file__).resolve().parents[1]


def test_exact_jain_join_has_137_rows_and_no_duplicate_inflation():
    joined, audit = load_jain_inputs(ROOT / "data/processed/jain_137.csv", ROOT / "data/features/jain_rule_features.csv")
    assert len(joined) == 137
    assert audit["matched_rows"] == 137
    assert audit["unmatched_experimental_rows"] == 0
    assert audit["unmatched_feature_rows"] == 0
    assert joined["record_id"].is_unique
    assert joined["antibody_id"].is_unique


def test_join_rejects_duplicate_ids_without_inflation(tmp_path):
    experimental = pd.DataFrame({"record_id": ["A", "A"], "antibody_id": ["A", "A"], **{assay: [1.0, 2.0] for assay in JAIN_ASSAYS}})
    features = pd.DataFrame({"record_id": ["A"], "antibody_id": ["A"], **{feature: [1.0] for feature in BENCHMARK_FEATURES}})
    exp_path, feature_path = tmp_path / "exp.csv", tmp_path / "features.csv"
    experimental.to_csv(exp_path, index=False)
    features.to_csv(feature_path, index=False)
    with pytest.raises(ValueError, match="record_id must be unique"):
        load_jain_inputs(exp_path, feature_path, expected_rows=None)


def test_all_12_assays_are_actual_source_columns_and_directionality_is_unknown():
    experimental = pd.read_csv(ROOT / "data/processed/jain_137.csv")
    assert all(assay in experimental.columns for assay in JAIN_ASSAYS)
    directions = load_assay_directions(ROOT / "data/processed/jain_data_dictionary.csv")
    assert list(directions) == list(JAIN_ASSAYS)
    assert set(directions.values()) == {"UNKNOWN"}


def test_pairwise_missing_values_are_not_imputed():
    joined = pd.DataFrame({
        "feature": [1.0, 2.0, np.nan, 4.0],
        "assay": [4.0, np.nan, 2.0, 1.0],
    })
    source = pd.DataFrame({
        "feature_a": joined["feature"],
        "assay_a": joined["assay"],
    })
    directions = {"Assay": "UNKNOWN"}
    fake = pd.DataFrame({"feature_a": source["feature_a"], "Assay": source["assay_a"]})
    result = compute_spearman_results(
        pd.DataFrame({**{feature: fake["feature_a"] for feature in BENCHMARK_FEATURES}, **{assay: fake["Assay"] for assay in JAIN_ASSAYS}}),
        {assay: "UNKNOWN" for assay in JAIN_ASSAYS},
    )
    row = result.loc[(result["feature"] == BENCHMARK_FEATURES[0]) & (result["assay"] == JAIN_ASSAYS[0])].iloc[0]
    assert row["n"] == 2
    assert np.isclose(row["rho"], -1.0)


def test_spearman_and_p_value_match_scipy_for_known_values():
    joined = pd.DataFrame({
        **{feature: [1.0, 2.0, 3.0, 4.0, 5.0] for feature in BENCHMARK_FEATURES},
        **{assay: [5.0, 4.0, 3.0, 2.0, 1.0] for assay in JAIN_ASSAYS},
    })
    result = compute_spearman_results(joined, {assay: "UNKNOWN" for assay in JAIN_ASSAYS})
    row = result.iloc[0]
    expected = jain_spearman.spearmanr([1, 2, 3, 4, 5], [5, 4, 3, 2, 1])
    assert row["rho"] == expected.statistic
    assert row["p_value"] == expected.pvalue
    assert row["n"] == 5


def test_bh_fdr_is_monotone_and_preserves_missing():
    q = benjamini_hochberg([0.01, 0.04, 0.20, np.nan])
    assert np.isnan(q[3])
    assert np.all(q[:3] >= np.array([0.01, 0.04, 0.20]) * 0.0)
    assert q[0] <= q[1] <= q[2]
    assert np.all(q[:3] <= 1.0)


def test_every_result_reports_n_and_directional_interpretation_is_blocked_when_unknown():
    joined, _ = load_jain_inputs(ROOT / "data/processed/jain_137.csv", ROOT / "data/features/jain_rule_features.csv")
    result = compute_spearman_results(joined, {assay: "UNKNOWN" for assay in JAIN_ASSAYS})
    assert len(result) == len(BENCHMARK_FEATURES) * 12
    assert result["n"].notna().all()
    assert set(result["interpretation_allowed"]) == {"association_only"}
    assert result["assay_direction"].notna().all()


def test_top10_order_is_deterministic_and_weak_findings_are_retained():
    joined, _ = load_jain_inputs(ROOT / "data/processed/jain_137.csv", ROOT / "data/features/jain_rule_features.csv")
    directions = {assay: "UNKNOWN" for assay in JAIN_ASSAYS}
    first = compute_spearman_results(joined, directions)
    second = compute_spearman_results(joined, directions)
    pd.testing.assert_frame_equal(first, second)
    top = rank_top_associations(first)
    assert len(top) == 10
    expected_top = first.loc[first["rho"].notna()].sort_values(
        ["abs_rho", "q_value", "feature", "assay"],
        ascending=[False, True, True, True],
        kind="mergesort",
    ).head(10)
    assert list(zip(top["feature"], top["assay"])) == list(zip(expected_top["feature"], expected_top["assay"]))
    weak = first.loc[first["abs_rho"] < 0.20]
    assert len(weak) > 0
    assert set(top.columns) == {"feature", "assay", "rho", "p_value", "q_value", "n", "assay_direction"}


def test_score_semantics_and_control_features_are_separate():
    assert SCORE_FEATURES == ("VH_calculated_score", "VL_calculated_score", "VH_rule_penalty", "VL_rule_penalty")
    assert "VH_length" not in SCORE_FEATURES
    assert effect_size_label(0.19) == "very weak"
    assert effect_size_label(0.20) == "weak"
    assert effect_size_label(0.40) == "moderate"
    assert effect_size_label(0.60) == "strong"
    assert effect_size_label(0.80) == "very strong"


def test_missingness_reports_all_assays():
    joined, _ = load_jain_inputs(ROOT / "data/processed/jain_137.csv", ROOT / "data/features/jain_rule_features.csv")
    missing = assay_missingness(joined)
    assert list(missing) == list(JAIN_ASSAYS)
    assert all(item["total_n"] == 137 for item in missing.values())
    assert all(item["missing_n"] == 0 for item in missing.values())


def test_benchmark_module_has_no_external_dataset_reference():
    source = inspect.getsource(jain_spearman).lower()
    assert "aintibody" not in source
    assert "total_developability_score" not in source
