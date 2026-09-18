"""Phase 4D2 post-hoc oxidation/HIC robustness analysis.

This module is deliberately downstream of the frozen Phase 4D1B primary
population.  It estimates partial Spearman associations after rank-based
residualization on VH length, performs a fixed-seed bootstrap for the four
predefined oxidation features, and reports a limited inferential logistic
adjustment.  It does not change production rules, scoring, thresholds, or
the preregistered primary analysis.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any, Iterable, Mapping, Sequence

import numpy as np
import pandas as pd
from scipy.special import expit
from scipy.stats import norm, rankdata, spearmanr, t

from validation.benchmark.jain_spearman import benjamini_hochberg
from validation.external_validation.analyze_aintibody import (
    ASSAY_COLUMNS,
    PRIMARY_ASSAYS,
    _canonical,
    _roc_auc,
    compute_assay_results,
    load_primary_join,
)


PHASE_4D1B_CHECKPOINT = "4d843f14f673e0845361fbe30adbd3195989efcb"
FROZEN_SCIENTIFIC_BASELINE = "d1487ed74bdfc52fb0b2015a25c4e91ee90af66d"

PRIMARY_ROBUSTNESS_FEATURES = (
    "VH_oxidation_count",
    "oxidation_count_combined",
    "VH_cdr_oxidation_count",
    "cdr_oxidation_count_combined",
)
SECONDARY_ROBUSTNESS_FEATURES = (
    "VH_liability_sites",
    "liability_sites_combined",
    "VH_total_sites",
    "total_sites_combined",
)
ROBUSTNESS_FEATURES = PRIMARY_ROBUSTNESS_FEATURES + SECONDARY_ROBUSTNESS_FEATURES
PRIMARY_CONFOUNDER = "VH_length"
OPTIONAL_DESCRIPTIVE_CONTROL = "VL_length"
HIC_COLUMN = ASSAY_COLUMNS["HIC"]
PRIMARY_CLASS = "NOT_DEVELOPABLE"
NEGATIVE_CLASS = "DEVELOPABLE"
BOOTSTRAP_RESAMPLES = 2000
BOOTSTRAP_SEED = 20240914
STRATA_LABELS = ("VH_length_tertile_1", "VH_length_tertile_2", "VH_length_tertile_3")

ROBUSTNESS_COLUMNS = (
    "feature",
    "feature_group",
    "raw_rho",
    "raw_p",
    "raw_n",
    "feature_vs_vh_length_rho",
    "feature_vs_vh_length_p",
    "feature_vs_vh_length_n",
    "partial_rho",
    "partial_p",
    "partial_q",
    "n",
    "bootstrap_ci_low",
    "bootstrap_ci_high",
    "bootstrap_resamples",
    "bootstrap_seed",
)

STRATA_COLUMNS = (
    "feature",
    "tertile",
    "tertile_n",
    "n",
    "vh_length_min",
    "vh_length_max",
    "cut_low",
    "cut_high",
    "rho",
    "p_value",
    "estimability",
)

LOGISTIC_COLUMNS = (
    "model",
    "term",
    "coefficient",
    "standard_error",
    "odds_ratio",
    "ci_low",
    "ci_high",
    "p_value",
    "n",
    "converged",
    "iterations",
)


def _require_columns(frame: pd.DataFrame, columns: Iterable[str], label: str) -> None:
    missing = [column for column in columns if column not in frame.columns]
    if missing:
        raise ValueError(f"{label} missing required columns: {', '.join(missing)}")


def rank_transform(values: Sequence[float]) -> np.ndarray:
    """Return deterministic average ranks for a complete numeric vector."""

    array = np.asarray(values, dtype=float)
    if array.ndim != 1 or not np.isfinite(array).all():
        raise ValueError("rank_transform requires a one-dimensional complete vector")
    return rankdata(array, method="average")


def _spearman_pair(x: Sequence[float], y: Sequence[float]) -> dict[str, float | int]:
    left = np.asarray(x, dtype=float)
    right = np.asarray(y, dtype=float)
    if len(left) != len(right):
        raise ValueError("Spearman inputs must have equal length")
    n = int(len(left))
    rho = float("nan")
    p_value = float("nan")
    if n >= 2 and np.unique(left).size >= 2 and np.unique(right).size >= 2:
        statistic = spearmanr(left, right)
        rho = float(statistic.statistic)
        p_value = float(statistic.pvalue)
    return {"rho": rho, "p": p_value, "n": n}


def _rank_residuals(
    feature: Sequence[float], outcome: Sequence[float], confounder: Sequence[float]
) -> tuple[np.ndarray, np.ndarray]:
    ranked_feature = rank_transform(feature)
    ranked_outcome = rank_transform(outcome)
    ranked_confounder = rank_transform(confounder)
    confounder_centered = ranked_confounder - ranked_confounder.mean()
    denominator = float(np.dot(confounder_centered, confounder_centered))
    if denominator == 0:
        raise ValueError("confounder has no rank variation")
    feature_centered = ranked_feature - ranked_feature.mean()
    outcome_centered = ranked_outcome - ranked_outcome.mean()
    feature_slope = float(np.dot(confounder_centered, feature_centered) / denominator)
    outcome_slope = float(np.dot(confounder_centered, outcome_centered) / denominator)
    feature_residual = feature_centered - feature_slope * confounder_centered
    outcome_residual = outcome_centered - outcome_slope * confounder_centered
    return feature_residual, outcome_residual


def _correlation_from_residuals(left: np.ndarray, right: np.ndarray) -> float:
    left_centered = left - left.mean()
    right_centered = right - right.mean()
    denominator = float(np.sqrt(np.dot(left_centered, left_centered) * np.dot(right_centered, right_centered)))
    if denominator == 0:
        return float("nan")
    return float(np.dot(left_centered, right_centered) / denominator)


def partial_spearman(
    feature: Sequence[float], outcome: Sequence[float], confounder: Sequence[float]
) -> dict[str, float | int]:
    """Rank-transform all variables, residualize on ranked VH length, correlate residuals."""

    left = np.asarray(feature, dtype=float)
    right = np.asarray(outcome, dtype=float)
    control = np.asarray(confounder, dtype=float)
    if not (len(left) == len(right) == len(control)):
        raise ValueError("partial Spearman inputs must have equal length")
    n = int(len(left))
    partial_rho = float("nan")
    p_value = float("nan")
    if n >= 4 and np.unique(left).size >= 2 and np.unique(right).size >= 2 and np.unique(control).size >= 2:
        residual_left, residual_right = _rank_residuals(left, right, control)
        partial_rho = _correlation_from_residuals(residual_left, residual_right)
        if np.isfinite(partial_rho):
            clipped = float(np.clip(partial_rho, -1.0, 1.0))
            if abs(clipped) >= 1.0:
                p_value = 0.0
            else:
                statistic = clipped * np.sqrt((n - 3) / (1.0 - clipped * clipped))
                p_value = float(2.0 * t.sf(abs(statistic), df=n - 3))
    return {"partial_rho": partial_rho, "partial_p": p_value, "n": n}


def bootstrap_partial_ci(
    feature: Sequence[float],
    outcome: Sequence[float],
    confounder: Sequence[float],
    *,
    n_resamples: int = BOOTSTRAP_RESAMPLES,
    seed: int = BOOTSTRAP_SEED,
    chunk_size: int = 100,
) -> tuple[float, float]:
    """Return a fixed-seed percentile CI for the partial Spearman estimate."""

    x = np.asarray(feature, dtype=float)
    y = np.asarray(outcome, dtype=float)
    z = np.asarray(confounder, dtype=float)
    if not (len(x) == len(y) == len(z)):
        raise ValueError("bootstrap inputs must have equal length")
    if n_resamples <= 0:
        raise ValueError("n_resamples must be positive")
    n = len(x)
    if n < 4:
        return float("nan"), float("nan")

    rng = np.random.default_rng(seed)
    estimates: list[np.ndarray] = []
    for start in range(0, n_resamples, chunk_size):
        count = min(chunk_size, n_resamples - start)
        indices = rng.integers(0, n, size=(count, n))
        ranked_x = rankdata(x[indices], axis=1, method="average")
        ranked_y = rankdata(y[indices], axis=1, method="average")
        ranked_z = rankdata(z[indices], axis=1, method="average")
        centered_z = ranked_z - ranked_z.mean(axis=1, keepdims=True)
        denominator = np.sum(centered_z * centered_z, axis=1)
        centered_x = ranked_x - ranked_x.mean(axis=1, keepdims=True)
        centered_y = ranked_y - ranked_y.mean(axis=1, keepdims=True)
        slope_x = np.divide(
            np.sum(centered_z * centered_x, axis=1),
            denominator,
            out=np.zeros_like(denominator),
            where=denominator != 0,
        )
        slope_y = np.divide(
            np.sum(centered_z * centered_y, axis=1),
            denominator,
            out=np.zeros_like(denominator),
            where=denominator != 0,
        )
        residual_x = centered_x - slope_x[:, None] * centered_z
        residual_y = centered_y - slope_y[:, None] * centered_z
        residual_denominator = np.sqrt(
            np.sum(residual_x * residual_x, axis=1) * np.sum(residual_y * residual_y, axis=1)
        )
        values = np.divide(
            np.sum(residual_x * residual_y, axis=1),
            residual_denominator,
            out=np.full(count, np.nan, dtype=float),
            where=residual_denominator != 0,
        )
        estimates.append(values)
    all_estimates = np.concatenate(estimates)
    if not np.isfinite(all_estimates).any():
        return float("nan"), float("nan")
    return (
        float(np.nanpercentile(all_estimates, 2.5)),
        float(np.nanpercentile(all_estimates, 97.5)),
    )


def _feature_group(feature: str) -> str:
    return "primary_oxidation" if feature in PRIMARY_ROBUSTNESS_FEATURES else "secondary_liability_or_count"


def compute_hic_robustness(
    joined: pd.DataFrame,
    *,
    raw_assay_results: pd.DataFrame | None = None,
    bootstrap_resamples: int = BOOTSTRAP_RESAMPLES,
    bootstrap_seed: int = BOOTSTRAP_SEED,
) -> tuple[pd.DataFrame, pd.DataFrame]:
    """Calculate raw, length-adjusted and bootstrap HIC results."""

    _require_columns(joined, (HIC_COLUMN, PRIMARY_CONFOUNDER, *ROBUSTNESS_FEATURES), "AIntibody HIC robustness input")
    raw_lookup: dict[str, pd.Series] = {}
    if raw_assay_results is not None:
        rows = raw_assay_results.loc[
            (raw_assay_results["assay"] == "HIC") & raw_assay_results["feature"].isin(ROBUSTNESS_FEATURES)
        ]
        raw_lookup = {str(row["feature"]): row for _, row in rows.iterrows()}

    rows: list[dict[str, Any]] = []
    for feature_index, feature in enumerate(ROBUSTNESS_FEATURES):
        x = pd.to_numeric(joined[feature], errors="coerce")
        y = pd.to_numeric(joined[HIC_COLUMN], errors="coerce")
        z = pd.to_numeric(joined[PRIMARY_CONFOUNDER], errors="coerce")
        mask = x.notna() & y.notna() & z.notna()
        x_values = x.loc[mask].to_numpy(dtype=float)
        y_values = y.loc[mask].to_numpy(dtype=float)
        z_values = z.loc[mask].to_numpy(dtype=float)
        raw = raw_lookup.get(feature)
        raw_stats = (
            {"rho": float(raw["rho"]), "p": float(raw["p_value"]), "n": int(raw["n"])}
            if raw is not None
            else _spearman_pair(x_values, y_values)
        )
        feature_length = _spearman_pair(x_values, z_values)
        partial = partial_spearman(x_values, y_values, z_values)
        low, high = (float("nan"), float("nan"))
        if feature in PRIMARY_ROBUSTNESS_FEATURES:
            low, high = bootstrap_partial_ci(
                x_values,
                y_values,
                z_values,
                n_resamples=bootstrap_resamples,
                seed=bootstrap_seed + feature_index,
            )
        rows.append(
            {
                "feature": feature,
                "feature_group": _feature_group(feature),
                "raw_rho": raw_stats["rho"],
                "raw_p": raw_stats["p"],
                "raw_n": raw_stats["n"],
                "feature_vs_vh_length_rho": feature_length["rho"],
                "feature_vs_vh_length_p": feature_length["p"],
                "feature_vs_vh_length_n": feature_length["n"],
                "partial_rho": partial["partial_rho"],
                "partial_p": partial["partial_p"],
                "partial_q": float("nan"),
                "n": partial["n"],
                "bootstrap_ci_low": low,
                "bootstrap_ci_high": high,
                "bootstrap_resamples": bootstrap_resamples if feature in PRIMARY_ROBUSTNESS_FEATURES else np.nan,
                "bootstrap_seed": bootstrap_seed if feature in PRIMARY_ROBUSTNESS_FEATURES else np.nan,
            }
        )
    result = pd.DataFrame(rows, columns=ROBUSTNESS_COLUMNS)
    result["partial_q"] = benjamini_hochberg(result["partial_p"].to_numpy(dtype=float))
    hic_frame = joined.loc[pd.to_numeric(joined[HIC_COLUMN], errors="coerce").notna()].copy()
    return result, hic_frame


def assign_length_tertiles(values: Sequence[float]) -> tuple[np.ndarray, dict[str, float]]:
    """Assign deterministic tertiles using only the observed VH lengths."""

    numeric = np.asarray(values, dtype=float)
    if numeric.ndim != 1 or not np.isfinite(numeric).all():
        raise ValueError("VH length tertiles require a complete one-dimensional vector")
    low, high = (float(item) for item in np.quantile(numeric, (1 / 3, 2 / 3), method="linear"))
    if not low < high:
        raise ValueError("VH length values do not support three distinct tertiles")
    labels = pd.cut(
        pd.Series(numeric),
        bins=[-np.inf, low, high, np.inf],
        labels=STRATA_LABELS,
        include_lowest=True,
        right=True,
    ).astype(str).to_numpy()
    return labels, {"cut_low": low, "cut_high": high}


def compute_length_strata(hic_frame: pd.DataFrame) -> tuple[pd.DataFrame, dict[str, float]]:
    _require_columns(hic_frame, (HIC_COLUMN, PRIMARY_CONFOUNDER, *PRIMARY_ROBUSTNESS_FEATURES), "HIC length strata input")
    complete = hic_frame.loc[
        pd.to_numeric(hic_frame[HIC_COLUMN], errors="coerce").notna()
        & pd.to_numeric(hic_frame[PRIMARY_CONFOUNDER], errors="coerce").notna()
    ].copy()
    lengths = pd.to_numeric(complete[PRIMARY_CONFOUNDER], errors="coerce").to_numpy(dtype=float)
    labels, cuts = assign_length_tertiles(lengths)
    complete["tertile"] = labels
    rows: list[dict[str, Any]] = []
    for feature in PRIMARY_ROBUSTNESS_FEATURES:
        for label in STRATA_LABELS:
            group = complete.loc[complete["tertile"] == label]
            x = pd.to_numeric(group[feature], errors="coerce")
            y = pd.to_numeric(group[HIC_COLUMN], errors="coerce")
            mask = x.notna() & y.notna()
            x_values = x.loc[mask].to_numpy(dtype=float)
            y_values = y.loc[mask].to_numpy(dtype=float)
            stats = _spearman_pair(x_values, y_values)
            estimability = "ESTIMABLE" if np.isfinite(stats["rho"]) else "NOT_ESTIMABLE"
            rows.append(
                {
                    "feature": feature,
                    "tertile": label,
                    "tertile_n": int(len(group)),
                    "n": stats["n"],
                    "vh_length_min": float(pd.to_numeric(group[PRIMARY_CONFOUNDER], errors="coerce").min()),
                    "vh_length_max": float(pd.to_numeric(group[PRIMARY_CONFOUNDER], errors="coerce").max()),
                    "cut_low": cuts["cut_low"],
                    "cut_high": cuts["cut_high"],
                    "rho": stats["rho"],
                    "p_value": stats["p"],
                    "estimability": estimability,
                }
            )
    return pd.DataFrame(rows, columns=STRATA_COLUMNS), cuts


def _logistic_fit(x: np.ndarray, y: np.ndarray, *, max_iter: int = 100, tolerance: float = 1e-10) -> dict[str, Any]:
    """Fit an unregularized logistic model by deterministic Newton iterations."""

    beta = np.zeros(x.shape[1], dtype=float)
    converged = False
    iterations = 0
    for iterations in range(1, max_iter + 1):
        probability = expit(np.clip(x @ beta, -35.0, 35.0))
        weights = probability * (1.0 - probability)
        information = x.T @ (weights[:, None] * x)
        score = x.T @ (y - probability)
        try:
            step = np.linalg.solve(information, score)
        except np.linalg.LinAlgError:
            step = np.linalg.pinv(information) @ score
        beta = beta + step
        if float(np.max(np.abs(step))) <= tolerance:
            converged = True
            break
    probability = expit(np.clip(x @ beta, -35.0, 35.0))
    weights = probability * (1.0 - probability)
    covariance = np.linalg.pinv(x.T @ (weights[:, None] * x))
    standard_error = np.sqrt(np.maximum(np.diag(covariance), 0.0))
    return {
        "coefficient": beta,
        "standard_error": standard_error,
        "predicted": probability,
        "converged": converged,
        "iterations": iterations,
    }


def compute_classification_robustness(joined: pd.DataFrame) -> tuple[pd.DataFrame, pd.DataFrame, dict[str, Any]]:
    _require_columns(joined, ("derived_binary_status", PRIMARY_CONFOUNDER, "cdr_oxidation_count_combined"), "classification robustness input")
    labels = joined["derived_binary_status"].map(_canonical)
    eligible = joined.loc[labels.isin({PRIMARY_CLASS, NEGATIVE_CLASS})].copy()
    y_series = eligible["derived_binary_status"].map(_canonical).eq(PRIMARY_CLASS)
    model_specs = {
        "length_only": (PRIMARY_CONFOUNDER,),
        "oxidation_only": ("cdr_oxidation_count_combined",),
        "length_plus_oxidation": (PRIMARY_CONFOUNDER, "cdr_oxidation_count_combined"),
    }
    auc_rows: list[dict[str, Any]] = []
    logistic_rows: list[dict[str, Any]] = []
    adjusted: dict[str, Any] = {}
    for model_name, features in model_specs.items():
        values = eligible.loc[:, list(features)].apply(pd.to_numeric, errors="coerce")
        # Predictor completeness is the only row-level exclusion in this model;
        # outcome labels are never used to remove rows from the eligible population.
        predictor_mask = values.notna().all(axis=1)
        x_values = values.loc[predictor_mask].to_numpy(dtype=float)
        y_values = y_series.loc[predictor_mask].to_numpy(dtype=float)
        design = np.column_stack([np.ones(len(x_values)), x_values])
        fit = _logistic_fit(design, y_values)
        auc_rows.append(
            {
                "model": model_name,
                "n": int(len(y_values)),
                "positive_n": int(y_values.sum()),
                "roc_auc": _roc_auc(y_values.astype(bool), fit["predicted"]),
                "label": "POST-HOC IN-SAMPLE descriptive AUC; not external predictive performance",
            }
        )
        terms = ("intercept", *features)
        for index, term in enumerate(terms):
            coefficient = float(fit["coefficient"][index])
            standard_error = float(fit["standard_error"][index])
            if standard_error == 0 or not np.isfinite(standard_error):
                p_value = float("nan")
            else:
                p_value = float(2.0 * norm.sf(abs(coefficient / standard_error)))
            logistic_rows.append(
                {
                    "model": model_name,
                    "term": term,
                    "coefficient": coefficient,
                    "standard_error": standard_error,
                    "odds_ratio": float(np.exp(np.clip(coefficient, -700.0, 700.0))),
                    "ci_low": float(np.exp(np.clip(coefficient - 1.96 * standard_error, -700.0, 700.0))),
                    "ci_high": float(np.exp(np.clip(coefficient + 1.96 * standard_error, -700.0, 700.0))),
                    "p_value": p_value,
                    "n": int(len(y_values)),
                    "converged": fit["converged"],
                    "iterations": fit["iterations"],
                }
            )
            if model_name == "length_plus_oxidation" and term == "cdr_oxidation_count_combined":
                adjusted = logistic_rows[-1].copy()
    return pd.DataFrame(logistic_rows, columns=LOGISTIC_COLUMNS), pd.DataFrame(auc_rows), adjusted


def compute_hic_specificity(joined: pd.DataFrame, assay_results: pd.DataFrame | None = None) -> pd.DataFrame:
    results = assay_results if assay_results is not None else compute_assay_results(joined)
    selected = results.loc[results["feature"].isin(PRIMARY_ROBUSTNESS_FEATURES)].copy()
    return selected.loc[:, ["feature", "assay", "rho", "p_value", "q_value", "n", "assay_direction"]].sort_values(
        ["feature", "assay"], kind="mergesort"
    ).reset_index(drop=True)


def _fmt(value: Any, digits: int = 5) -> str:
    if value is None:
        return "NA"
    try:
        if pd.isna(value) or not np.isfinite(float(value)):
            return "NA"
    except (TypeError, ValueError):
        return str(value)
    return f"{float(value):.{digits}g}"


def _write_plot(feature: str, hic_frame: pd.DataFrame, result_row: pd.Series, path: Path) -> None:
    import matplotlib

    matplotlib.use("Agg")
    import matplotlib.pyplot as plt

    x = pd.to_numeric(hic_frame[feature], errors="coerce")
    y = pd.to_numeric(hic_frame[HIC_COLUMN], errors="coerce")
    z = pd.to_numeric(hic_frame[PRIMARY_CONFOUNDER], errors="coerce")
    mask = x.notna() & y.notna() & z.notna()
    x_values = x.loc[mask].to_numpy(dtype=float)
    y_values = y.loc[mask].to_numpy(dtype=float)
    z_values = z.loc[mask].to_numpy(dtype=float)
    residual_x, residual_y = _rank_residuals(x_values, y_values, z_values)
    annotation = (
        f"raw rho={_fmt(result_row['raw_rho'])}\n"
        f"partial rho={_fmt(result_row['partial_rho'])}\n"
        f"N={int(result_row['n'])}"
    )
    fig, axes = plt.subplots(1, 3, figsize=(15, 4.4), dpi=160)
    axes[0].scatter(x_values, y_values, s=18, alpha=0.72, color="#2b6cb0", edgecolors="none")
    axes[0].set_xlabel(feature)
    axes[0].set_ylabel("HIC RT in gradient (min)")
    axes[0].set_title("Raw feature vs HIC")
    axes[1].scatter(x_values, z_values, s=18, alpha=0.72, color="#805ad5", edgecolors="none")
    axes[1].set_xlabel(feature)
    axes[1].set_ylabel("VH length")
    axes[1].set_title("Feature vs VH length")
    axes[2].scatter(residual_x, residual_y, s=18, alpha=0.72, color="#c05621", edgecolors="none")
    axes[2].set_xlabel("Residualized feature rank")
    axes[2].set_ylabel("Residualized HIC rank")
    axes[2].set_title("Rank-residualized association")
    for axis in axes:
        axis.grid(True, alpha=0.22)
        axis.text(
            0.03,
            0.97,
            annotation,
            transform=axis.transAxes,
            va="top",
            ha="left",
            fontsize=8,
            bbox={"facecolor": "white", "alpha": 0.78, "edgecolor": "none"},
        )
    fig.suptitle(f"Phase 4D2: {feature}")
    fig.tight_layout()
    fig.savefig(path, bbox_inches="tight", metadata={"Software": "matplotlib"})
    plt.close(fig)


def _write_report(
    report_path: Path,
    summary: Mapping[str, Any],
    robustness: pd.DataFrame,
    strata: pd.DataFrame,
    specificity: pd.DataFrame,
    auc_results: pd.DataFrame,
    adjusted: Mapping[str, Any],
    plot_files: Sequence[str],
) -> None:
    lines = [
        "# AIntibody 2026 Phase 4D2 oxidation/HIC robustness analysis",
        "",
        "This is a post-hoc robustness analysis motivated by the completed Phase 4D1B result. The original Phase 4D1B external-validation result remains primary.",
        "",
        "## Frozen boundary",
        "",
        f"- Phase 4D1B checkpoint: `{PHASE_4D1B_CHECKPOINT}`.",
        f"- Frozen scientific baseline: `{FROZEN_SCIENTIFIC_BASELINE}`.",
        "- The frozen Phase 4D1B primary population and HIC definition were reused without redefinition.",
        "- No scientific rule, CDR definition, score, rule weight, or threshold was changed.",
        "- No threshold was optimized, no production ML model was trained, and no ESM/ProtT5 model was used.",
        "- No samples were removed based on outcome. Missing values were handled pairwise for the relevant statistic.",
        "",
        "## Analysis population",
        "",
        f"- Frozen primary population: **{summary['primary_population_n']}** unique VH/VL sequence rows.",
        f"- HIC-available rows used for robustness analysis: **{summary['hic_n']}**.",
        f"- HIC column: `{HIC_COLUMN}`.",
        "- Primary classification results are not used to define the HIC population.",
        "",
        "## Method",
        "",
        "- Feature/VH-length and raw feature/HIC associations use two-sided Spearman rho with pairwise complete observations.",
        "- Partial Spearman is deterministic rank residualization: rank feature, HIC, and VH length with average ranks; regress each ranked response on ranked VH length with an intercept; correlate the two residual vectors.",
        "- Partial-correlation p-values use the two-sided t statistic with df=N-3 for one adjusted variable.",
        f"- BH-FDR is applied across the **{len(ROBUSTNESS_FEATURES)}** predefined partial-correlation tests only.",
        f"- Primary bootstrap CIs use {BOOTSTRAP_RESAMPLES} resamples, a fixed base seed of {BOOTSTRAP_SEED}, and the percentile interval. Feature order offsets the seed deterministically by index.",
        "- VH-length tertiles are cut using the 1/3 and 2/3 empirical quantiles of VH length only; they are descriptive and not outcome-defined.",
        "",
        "## Feature ↔ VH length correlations",
        "",
        "| Feature | rho | p | N |",
        "|---|---:|---:|---:|",
    ]
    for _, row in robustness.iterrows():
        lines.append(f"| `{row['feature']}` | {_fmt(row['feature_vs_vh_length_rho'])} | {_fmt(row['feature_vs_vh_length_p'])} | {int(row['feature_vs_vh_length_n'])} |")

    lines.extend([
        "",
        "## Raw vs partial HIC associations",
        "",
        "| Feature | Raw rho | Partial rho | Partial p | Partial q | N | 95% bootstrap CI |",
        "|---|---:|---:|---:|---:|---:|---|",
    ])
    for _, row in robustness.iterrows():
        ci = "not calculated"
        if np.isfinite(row["bootstrap_ci_low"]):
            ci = f"[{_fmt(row['bootstrap_ci_low'])}, {_fmt(row['bootstrap_ci_high'])}]"
        lines.append(
            f"| `{row['feature']}` | {_fmt(row['raw_rho'])} | {_fmt(row['partial_rho'])} | {_fmt(row['partial_p'])} | {_fmt(row['partial_q'])} | {int(row['n'])} | {ci} |"
        )
    q_count = int((robustness["partial_q"] < 0.05).sum())
    lines.extend(["", f"- Partial q < 0.05: **{q_count}** of {len(ROBUSTNESS_FEATURES)} predefined tests."])

    lines.extend(["", "## Length-stratified sensitivity", "", f"- Cut points: VH length ≤ {_fmt(summary['length_cut_low'])}, then ≤ {_fmt(summary['length_cut_high'])}, then above the second cut.", "", "| Feature | Tertile | N | VH length range | rho |", "|---|---|---:|---|---:|"])
    for _, row in strata.iterrows():
        lines.append(f"| `{row['feature']}` | `{row['tertile']}` | {int(row['n'])} | {_fmt(row['vh_length_min'])}–{_fmt(row['vh_length_max'])} | {_fmt(row['rho'])} |")

    lines.extend(["", "## HIC specificity", "", "These are the already-defined Phase 4D1B oxidation-feature associations across the five primary assays. They are descriptive and do not redefine the robustness population.", "", "| Feature | Assay | rho | q | N |", "|---|---|---:|---:|---:|"])
    for _, row in specificity.iterrows():
        lines.append(f"| `{row['feature']}` | `{row['assay']}` | {_fmt(row['rho'])} | {_fmt(row['q_value'])} | {int(row['n'])} |")

    lines.extend(["", "## Classification confounder check", "", "The only adjusted model was `NOT_DEVELOPABLE ~ VH_length + cdr_oxidation_count_combined`. This is an inferential post-hoc adjustment, not a trained production model. Combined-model AUC is in-sample and descriptive only.", "", "| Model | N | Positive N | ROC-AUC |", "|---|---:|---:|---:|"])
    for _, row in auc_results.iterrows():
        lines.append(f"| `{row['model']}` | {int(row['n'])} | {int(row['positive_n'])} | {_fmt(row['roc_auc'])} |")
    lines.extend([
        "",
        f"- Adjusted oxidation coefficient: **{_fmt(adjusted.get('coefficient'))}**.",
        f"- Adjusted oxidation standard error: **{_fmt(adjusted.get('standard_error'))}**.",
        f"- Adjusted oxidation odds ratio: **{_fmt(adjusted.get('odds_ratio'))}**.",
        f"- Adjusted oxidation 95% CI: **[{_fmt(adjusted.get('ci_low'))}, {_fmt(adjusted.get('ci_high'))}]**.",
        f"- Adjusted oxidation p-value: **{_fmt(adjusted.get('p_value'))}**.",
        "- No threshold optimization, sign reversal, stepwise selection, regularization, interaction search, affinity leakage, or ML was used.",
        "",
        "## Scientific interpretation",
        "",
    ])
    primary = robustness.loc[robustness["feature"].isin(PRIMARY_ROBUSTNESS_FEATURES)]
    same_direction = bool(((np.sign(primary["raw_rho"]) == np.sign(primary["partial_rho"])) & (primary["partial_rho"].abs() >= 0.2)).all())
    mostly_null = bool((primary["partial_rho"].abs() < 0.1).all())
    if same_direction:
        persistence = "The primary oxidation/HIC associations remain clearly non-zero and directionally consistent after VH-length adjustment."
    elif mostly_null:
        persistence = "The primary oxidation/HIC associations become small or null after VH-length adjustment, so much of the raw association may reflect length confounding."
    else:
        persistence = "The adjusted oxidation/HIC results are mixed across predefined features, indicating feature-specific robustness rather than a uniform signal."
    attenuation = (1.0 - primary["partial_rho"].abs() / primary["raw_rho"].abs()).replace([np.inf, -np.inf], np.nan).median()
    cdr_row = robustness.loc[robustness["feature"] == "cdr_oxidation_count_combined"].iloc[0]
    lines.extend([
        f"1. Does oxidation/HIC remain after controlling VH length? {persistence}",
        f"2. How much of the raw association appears length-related? The median absolute attenuation across the four primary features is {_fmt(attenuation)}; this is a descriptive decomposition, not a causal estimate.",
        f"3. Does CDR oxidation contribute information beyond length? `cdr_oxidation_count_combined` has partial rho={_fmt(cdr_row['partial_rho'])}, p={_fmt(cdr_row['partial_p'])}, q={_fmt(cdr_row['partial_q'])}; this supports only the stated adjusted association, not causality.",
        "4. Does this strengthen or weaken the liability-screening interpretation? The analysis can refine the liability-screening interpretation for HIC, but HIC is one developability dimension and the results do not establish global developability prediction.",
        "",
        "## Reproducible outputs",
        "",
        "- `aintibody_hic_robustness.csv` contains raw, feature-length, partial, FDR, and bootstrap fields.",
        "- `aintibody_hic_length_strata.csv` contains the predefined VH-length tertile sensitivity analysis.",
        "- `aintibody_hic_specificity.csv` preserves the frozen five-assay oxidation-feature comparisons.",
        "- `aintibody_logistic_adjustment.csv` contains the three fixed inferential adjustment models.",
        f"- Residualized figures: {', '.join(plot_files)}.",
        "",
        "Post-hoc labeling is preserved in this report and output metadata. The original Phase 4D1B result remains the primary external-validation result.",
    ])
    report_path.write_text("\n".join(lines) + "\n", encoding="utf-8")


def run_hic_robustness(
    primary_path: str | Path,
    feature_path: str | Path,
    output_dir: str | Path,
    report_path: str | Path,
    *,
    bootstrap_resamples: int = BOOTSTRAP_RESAMPLES,
    bootstrap_seed: int = BOOTSTRAP_SEED,
) -> dict[str, Any]:
    output_root = Path(output_dir)
    output_root.mkdir(parents=True, exist_ok=True)
    report_file = Path(report_path)
    report_file.parent.mkdir(parents=True, exist_ok=True)
    joined, join_audit = load_primary_join(primary_path, feature_path)
    raw_assay_results = compute_assay_results(joined)
    robustness, hic_frame = compute_hic_robustness(
        joined,
        raw_assay_results=raw_assay_results,
        bootstrap_resamples=bootstrap_resamples,
        bootstrap_seed=bootstrap_seed,
    )
    strata, cuts = compute_length_strata(hic_frame)
    specificity = compute_hic_specificity(joined, raw_assay_results)
    logistic, auc_results, adjusted = compute_classification_robustness(joined)

    robustness.to_csv(output_root / "aintibody_hic_robustness.csv", index=False, na_rep="")
    strata.to_csv(output_root / "aintibody_hic_length_strata.csv", index=False, na_rep="")
    specificity.to_csv(output_root / "aintibody_hic_specificity.csv", index=False, na_rep="")
    logistic.to_csv(output_root / "aintibody_logistic_adjustment.csv", index=False, na_rep="")

    plot_files: list[str] = []
    for feature in PRIMARY_ROBUSTNESS_FEATURES:
        row = robustness.loc[robustness["feature"] == feature].iloc[0]
        filename = f"phase4d2_{feature}.png"
        _write_plot(feature, hic_frame, row, report_file.parent / filename)
        plot_files.append(filename)

    summary = {
        "analysis": "Phase 4D2 post-hoc oxidation/HIC robustness",
        "post_hoc": True,
        "primary_phase_4d1b_remains_primary": True,
        "phase_4d1b_checkpoint": PHASE_4D1B_CHECKPOINT,
        "frozen_scientific_baseline": FROZEN_SCIENTIFIC_BASELINE,
        "primary_population_n": int(len(joined)),
        "hic_n": int(len(hic_frame)),
        "hic_column": HIC_COLUMN,
        "join_audit": join_audit,
        "robustness_features": list(ROBUSTNESS_FEATURES),
        "partial_test_count": len(ROBUSTNESS_FEATURES),
        "partial_q_lt_0_05": int((robustness["partial_q"] < 0.05).sum()),
        "bootstrap_resamples": bootstrap_resamples,
        "bootstrap_seed": bootstrap_seed,
        "length_cut_low": cuts["cut_low"],
        "length_cut_high": cuts["cut_high"],
        "classification_auc": auc_results.to_dict(orient="records"),
        "adjusted_oxidation": adjusted,
        "threshold_optimization_performed": False,
        "production_ml_trained": False,
        "outcome_based_sample_removal": False,
        "affinity_used": False,
        "scientific_core_changed": False,
        "plot_files": plot_files,
    }
    (output_root / "aintibody_hic_robustness_summary.json").write_text(
        json.dumps(summary, indent=2, ensure_ascii=False, default=str) + "\n", encoding="utf-8"
    )
    _write_report(report_file, summary, robustness, strata, specificity, auc_results, adjusted, plot_files)
    return summary


def main() -> None:
    root = Path(__file__).resolve().parents[2]
    run_hic_robustness(
        root / "validation/data/external_validation/aintibody_primary_population.csv",
        root / "validation/data/features/aintibody_rule_features.csv",
        root / "validation/data/external_validation",
        root / "validation/reports/aintibody_external/hic_robustness_report.md",
    )


if __name__ == "__main__":
    main()
