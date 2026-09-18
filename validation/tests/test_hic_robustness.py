from __future__ import annotations

import ast
from pathlib import Path

import numpy as np
import pandas as pd

from validation.benchmark.jain_spearman import benjamini_hochberg
from validation.external_validation.analyze_aintibody import (
    compute_assay_results,
    load_primary_join,
)
from validation.external_validation.analyze_hic_robustness import (
    BOOTSTRAP_SEED,
    HIC_COLUMN,
    PRIMARY_ROBUSTNESS_FEATURES,
    ROBUSTNESS_FEATURES,
    STRATA_LABELS,
    assign_length_tertiles,
    bootstrap_partial_ci,
    compute_classification_robustness,
    compute_hic_robustness,
    compute_hic_specificity,
    compute_length_strata,
    partial_spearman,
    rank_transform,
    run_hic_robustness,
)


ROOT = Path(__file__).resolve().parents[1]
PRIMARY = ROOT / "data/external_validation/aintibody_primary_population.csv"
FEATURES = ROOT / "data/features/aintibody_rule_features.csv"


def _run(tmp_path: Path):
    return run_hic_robustness(
        PRIMARY,
        FEATURES,
        tmp_path / "data",
        tmp_path / "report" / "hic_robustness_report.md",
        bootstrap_resamples=25,
        bootstrap_seed=BOOTSTRAP_SEED,
    )


def test_uses_exact_frozen_population_and_hic_pairwise_n():
    joined, _ = load_primary_join(PRIMARY, FEATURES)
    raw = compute_assay_results(joined)
    robustness, hic_frame = compute_hic_robustness(joined, raw_assay_results=raw, bootstrap_resamples=5)
    assert len(joined) == 476
    assert len(hic_frame) == 427
    assert set(robustness["n"]) == {427}
    assert set(robustness["raw_n"]) == {427}


def test_rank_transform_and_partial_spearman_are_deterministic():
    assert np.array_equal(rank_transform([2, 1, 2, 4]), np.array([2.5, 1.0, 2.5, 4.0]))
    z = np.arange(1.0, 41.0)
    feature = 0.1 * z + np.sin(z / 2.0)
    outcome = 0.2 * z + np.cos(z / 3.0)
    first = partial_spearman(feature, outcome, z)
    second = partial_spearman(feature, outcome, z)
    assert first["n"] == second["n"]
    assert np.isclose(first["partial_rho"], second["partial_rho"])
    assert np.isclose(first["partial_p"], second["partial_p"])
    assert first["n"] == 40
    assert np.isfinite(first["partial_rho"])


def test_bh_fdr_is_applied_deterministically():
    assert np.allclose(benjamini_hochberg([0.01, 0.02, 0.5]), [0.03, 0.03, 0.5])


def test_bootstrap_ci_is_fixed_seed_and_deterministic():
    z = np.arange(1.0, 31.0)
    feature = 0.1 * z + np.sin(z)
    outcome = 0.2 * z + np.cos(z / 2.0)
    first = bootstrap_partial_ci(feature, outcome, z, n_resamples=50, seed=BOOTSTRAP_SEED)
    second = bootstrap_partial_ci(feature, outcome, z, n_resamples=50, seed=BOOTSTRAP_SEED)
    assert np.allclose(first, second)
    assert first[0] <= first[1]


def test_length_tertiles_use_only_vh_length_and_are_deterministic():
    values = np.array([116, 117, 118, 119, 123, 124, 125, 126, 127], dtype=float)
    first, cuts = assign_length_tertiles(values)
    second, same_cuts = assign_length_tertiles(values)
    assert np.array_equal(first, second)
    assert cuts == same_cuts
    assert set(first) == set(STRATA_LABELS)
    assert cuts["cut_low"] < cuts["cut_high"]


def test_no_outcome_based_hic_sample_removal_and_no_feature_expansion():
    joined, _ = load_primary_join(PRIMARY, FEATURES)
    _, hic_frame = compute_hic_robustness(joined, bootstrap_resamples=5)
    assert len(hic_frame) == 427
    assert hic_frame["derived_binary_status"].notna().any()
    assert tuple(ROBUSTNESS_FEATURES) == (
        "VH_oxidation_count",
        "oxidation_count_combined",
        "VH_cdr_oxidation_count",
        "cdr_oxidation_count_combined",
        "VH_liability_sites",
        "liability_sites_combined",
        "VH_total_sites",
        "total_sites_combined",
    )
    assert set(PRIMARY_ROBUSTNESS_FEATURES).issubset(ROBUSTNESS_FEATURES)


def test_fixed_logistic_adjustment_formula_and_descriptive_auc():
    joined, _ = load_primary_join(PRIMARY, FEATURES)
    logistic, auc, adjusted = compute_classification_robustness(joined)
    assert set(auc["model"]) == {"length_only", "oxidation_only", "length_plus_oxidation"}
    assert set(logistic.loc[logistic["model"] == "length_plus_oxidation", "term"]) == {
        "intercept",
        "VH_length",
        "cdr_oxidation_count_combined",
    }
    assert adjusted["model"] == "length_plus_oxidation"
    assert adjusted["term"] == "cdr_oxidation_count_combined"
    assert all(auc["label"].str.contains("POST-HOC IN-SAMPLE"))


def test_hic_specificity_uses_frozen_five_assays():
    joined, _ = load_primary_join(PRIMARY, FEATURES)
    specificity = compute_hic_specificity(joined)
    assert set(specificity["feature"]) == set(PRIMARY_ROBUSTNESS_FEATURES)
    assert set(specificity["assay"]) == {"Tm", "Tagg", "HIC", "BVP", "AC-SINS"}
    assert len(specificity) == 20


def test_output_report_is_posthoc_and_primary_results_are_separate(tmp_path):
    _run(tmp_path)
    report = (tmp_path / "report" / "hic_robustness_report.md").read_text(encoding="utf-8")
    assert "post-hoc" in report
    assert "Phase 4D1B external-validation result remains primary" in report
    assert "No scientific rule" in report
    assert (tmp_path / "data" / "aintibody_hic_robustness.csv").exists()
    assert (tmp_path / "data" / "aintibody_hic_length_strata.csv").exists()


def test_no_ml_threshold_optimizer_or_production_scientific_imports():
    source = (ROOT / "external_validation/analyze_hic_robustness.py").read_text(encoding="utf-8").lower()
    tree = ast.parse(source)
    imports = " ".join(
        ast.unparse(node) for node in ast.walk(tree) if isinstance(node, (ast.Import, ast.ImportFrom))
    )
    assert "core" not in imports
    assert "scoring" not in imports
    assert "sklearn" not in imports
    assert "torch" not in imports
    assert "xgboost" not in imports
    assert "gridsearch" not in source
    assert "roc_curve" not in source
    assert "1 - auc" not in source


def test_strata_and_robustness_outputs_have_expected_schema(tmp_path):
    _run(tmp_path)
    robustness = pd.read_csv(tmp_path / "data" / "aintibody_hic_robustness.csv")
    strata = pd.read_csv(tmp_path / "data" / "aintibody_hic_length_strata.csv")
    assert list(robustness["feature"]) == list(ROBUSTNESS_FEATURES)
    assert set(strata["feature"]) == set(PRIMARY_ROBUSTNESS_FEATURES)
    assert set(strata["tertile"]) == set(STRATA_LABELS)
    assert (strata["n"] > 0).all()
    assert HIC_COLUMN not in robustness.columns
