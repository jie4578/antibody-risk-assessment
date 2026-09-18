"""Phase 4D1B AIntibody external validation analysis.

This module is intentionally downstream of the frozen Phase 4D1A population
and endpoint audit.  It reads the exact frozen feature set, performs identity-
checked joins, and calculates only the preregistered association and
classification statistics.  It does not alter production rules, select
features, optimize thresholds, train models, or use affinity endpoints.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any, Iterable, Mapping, Sequence

import numpy as np
import pandas as pd
from scipy.stats import rankdata, spearmanr

from validation.benchmark.jain_spearman import benjamini_hochberg, effect_size_label
from validation.external_validation.population_audit import (
    COMPOSITE_SCORE_FIELD,
    CONTEXT_FIELDS,
    PRIMARY_SOURCE_FIELDS,
    _canonical,
    _has_value,
    _numeric,
    derive_composite_status,
)
from validation.external_validation_spec import (
    DATASET,
    FROZEN_RULE_FEATURES,
    PRIMARY_ANALYSIS_UNIT,
    PRIMARY_ASSAYS,
)


ASSAY_COLUMNS = {
    "Tm": "Tm, C",
    "Tagg": "Tagg, C",
    "HIC": "HIC RT in gradient (min)",
    "BVP": "average BVP score",
    "AC-SINS": "average dPW",
}
ASSAY_DIRECTIONS = {
    "Tm": "lower_unfavorable",
    "Tagg": "lower_unfavorable",
    "HIC": "higher_unfavorable",
    "BVP": "higher_unfavorable",
    "AC-SINS": "higher_unfavorable",
}
CONTROL_FEATURES = ("VH_length", "VL_length")
CALCULATED_SCORE_FEATURES = ("VH_calculated_score", "VL_calculated_score")
PRIMARY_POSITIVE_CLASS = "NOT_DEVELOPABLE"
PRIMARY_NEGATIVE_CLASS = "DEVELOPABLE"

ASSAY_RESULT_COLUMNS = (
    "feature",
    "assay",
    "rho",
    "abs_rho",
    "p_value",
    "q_value",
    "n",
    "assay_direction",
    "expected_risk_direction",
    "direction_consistent",
    "effect_size_label",
    "control_or_rule",
)
CLASSIFICATION_RESULT_COLUMNS = (
    "feature",
    "n",
    "positive_n",
    "negative_n",
    "positive_prevalence",
    "roc_auc",
    "pr_auc",
    "predictor_direction",
    "control_or_rule",
    "notes",
)


def _require_columns(frame: pd.DataFrame, columns: Iterable[str], label: str) -> None:
    missing = [column for column in columns if column not in frame.columns]
    if missing:
        raise ValueError(f"{label} missing required columns: {', '.join(missing)}")


def _same_value(left: Any, right: Any) -> bool:
    left_number, right_number = _numeric(left), _numeric(right)
    if left_number is not None and right_number is not None:
        return left_number == right_number
    return _canonical(left) == _canonical(right)


def _require_unique_feature_values(features: pd.DataFrame) -> pd.DataFrame:
    """Collapse deterministic duplicate feature rows by sequence hash."""

    rows: list[dict[str, Any]] = []
    for sequence_hash, group in features.groupby("sequence_hash", sort=True, dropna=False):
        key = _canonical(sequence_hash)
        if key == "<MISSING>":
            raise ValueError("feature table contains a missing sequence_hash")
        first = group.iloc[0]
        for feature in FROZEN_RULE_FEATURES:
            if not all(_same_value(first[feature], value) for value in group[feature].iloc[1:]):
                raise ValueError(f"feature values disagree for sequence_hash {key}: {feature}")
        rows.append({"sequence_hash": key, **{feature: first[feature] for feature in FROZEN_RULE_FEATURES}})
    return pd.DataFrame(rows, columns=("sequence_hash", *FROZEN_RULE_FEATURES))


def load_feature_map(feature_path: str | Path) -> tuple[pd.DataFrame, dict[str, Any]]:
    features = pd.read_csv(feature_path, dtype=object, usecols=("record_id", "sequence_hash", *FROZEN_RULE_FEATURES))
    _require_columns(features, ("record_id", "sequence_hash", *FROZEN_RULE_FEATURES), "AIntibody feature table")
    feature_map = _require_unique_feature_values(features)
    return feature_map, {
        "raw_feature_rows": int(len(features)),
        "raw_feature_unique_record_ids": int(features["record_id"].nunique()),
        "raw_feature_unique_hashes": int(features["sequence_hash"].map(_canonical).nunique()),
        "unique_feature_hash_rows": int(len(feature_map)),
    }


def load_primary_join(primary_path: str | Path, feature_path: str | Path) -> tuple[pd.DataFrame, dict[str, Any]]:
    """Load the frozen 4D1A population and perform an identity-checked join."""

    primary = pd.read_csv(primary_path, dtype=object)
    _require_columns(
        primary,
        ("sequence_hash", "representative_record_id", "derived_binary_status", *ASSAY_COLUMNS.values()),
        "AIntibody primary population",
    )
    if len(primary) != 476:
        raise ValueError(f"primary population rows {len(primary)} != expected 476")
    primary["sequence_hash"] = primary["sequence_hash"].map(_canonical)
    if primary["sequence_hash"].duplicated().any():
        raise ValueError("primary population must contain one row per sequence_hash")

    feature_map, feature_audit = load_feature_map(feature_path)
    primary_hashes = set(primary["sequence_hash"])
    raw_features = pd.read_csv(feature_path, dtype=object, usecols=("record_id", "sequence_hash"))
    raw_features["sequence_hash"] = raw_features["sequence_hash"].map(_canonical)
    matching_raw = raw_features.loc[raw_features["sequence_hash"].isin(primary_hashes)]
    matched_hashes = set(feature_map["sequence_hash"]) & primary_hashes
    unmatched_population = sorted(primary_hashes - set(feature_map["sequence_hash"]))
    unmatched_features = sorted(set(feature_map["sequence_hash"]) - primary_hashes)
    duplicate_join_rows = int(matching_raw["sequence_hash"].value_counts().sub(1).clip(lower=0).sum())
    if unmatched_population:
        raise ValueError(f"primary population has unmatched feature hashes: {unmatched_population}")

    joined = primary.merge(feature_map, on="sequence_hash", how="left", validate="one_to_one", indicator=True)
    if len(joined) != len(primary) or not joined["_merge"].eq("both").all():
        raise ValueError("AIntibody primary feature join lost or duplicated population rows")
    joined = joined.drop(columns=["_merge"])
    audit = {
        "population_rows": int(len(primary)),
        "matched_unique_feature_rows": int(len(matched_hashes)),
        "matched_raw_feature_rows": int(len(matching_raw)),
        "unmatched_population_rows": int(len(unmatched_population)),
        "unmatched_feature_hashes": int(len(unmatched_features)),
        "duplicate_join_rows": duplicate_join_rows,
        "join_key": "sequence_hash",
        "feature_values_consistent_within_hash": True,
        **feature_audit,
    }
    return joined, audit


def _expected_direction(feature: str, assay: str) -> str:
    if feature in CONTROL_FEATURES:
        return "not_applicable"
    assay_is_lower_unfavorable = ASSAY_DIRECTIONS[assay] == "lower_unfavorable"
    positive = not assay_is_lower_unfavorable
    if feature in CALCULATED_SCORE_FEATURES:
        positive = not positive
    return "positive" if positive else "negative"


def _direction_consistency(feature: str, assay: str, rho: float) -> str:
    if feature in CONTROL_FEATURES:
        return "NOT_APPLICABLE"
    if not np.isfinite(rho):
        return "NOT_ESTIMABLE"
    expected = _expected_direction(feature, assay)
    if rho == 0:
        return "False"
    return str((rho > 0) == (expected == "positive"))


def compute_assay_results(joined: pd.DataFrame) -> pd.DataFrame:
    _require_columns(joined, ("derived_binary_status", *ASSAY_COLUMNS.values(), *FROZEN_RULE_FEATURES), "joined AIntibody primary table")
    rows: list[dict[str, Any]] = []
    for feature in FROZEN_RULE_FEATURES:
        x = pd.to_numeric(joined[feature], errors="coerce")
        for assay in PRIMARY_ASSAYS:
            assay_column = ASSAY_COLUMNS[assay]
            y = pd.to_numeric(joined[assay_column], errors="coerce")
            mask = x.notna() & y.notna()
            n = int(mask.sum())
            rho = float("nan")
            p_value = float("nan")
            if n >= 2 and x.loc[mask].nunique() >= 2 and y.loc[mask].nunique() >= 2:
                statistic = spearmanr(x.loc[mask].to_numpy(dtype=float), y.loc[mask].to_numpy(dtype=float))
                rho = float(statistic.statistic)
                p_value = float(statistic.pvalue)
            rows.append({
                "feature": feature,
                "assay": assay,
                "rho": rho,
                "abs_rho": abs(rho) if np.isfinite(rho) else float("nan"),
                "p_value": p_value,
                "q_value": float("nan"),
                "n": n,
                "assay_direction": ASSAY_DIRECTIONS[assay],
                "expected_risk_direction": _expected_direction(feature, assay),
                "direction_consistent": _direction_consistency(feature, assay, rho),
                "effect_size_label": effect_size_label(abs(rho) if np.isfinite(rho) else float("nan")),
                "control_or_rule": "CONTROL" if feature in CONTROL_FEATURES else "RULE",
            })
    result = pd.DataFrame(rows, columns=ASSAY_RESULT_COLUMNS)
    result["q_value"] = benjamini_hochberg(result["p_value"].to_numpy(dtype=float))
    return result


def _fixed_predictor_direction(feature: str) -> str:
    if feature in CONTROL_FEATURES:
        return "control_raw"
    if feature in CALCULATED_SCORE_FEATURES:
        return "lower_more_risk"
    return "higher_more_risk"


def _oriented_predictor_values(feature: str, values: pd.Series) -> pd.Series:
    # This orientation is fixed from feature semantics before AIntibody
    # outcomes are read. It is not a post-hoc 1-AUC transformation.
    numeric = pd.to_numeric(values, errors="coerce")
    if feature in CALCULATED_SCORE_FEATURES:
        return -numeric
    return numeric


def _roc_auc(y_true: np.ndarray, scores: np.ndarray) -> float:
    positive = y_true.astype(bool)
    p_count = int(positive.sum())
    n_count = int((~positive).sum())
    if p_count == 0 or n_count == 0:
        return float("nan")
    ranks = rankdata(scores, method="average")
    return float((ranks[positive].sum() - p_count * (p_count + 1) / 2) / (p_count * n_count))


def _pr_auc(y_true: np.ndarray, scores: np.ndarray) -> float:
    positive = y_true.astype(bool)
    p_count = int(positive.sum())
    if p_count == 0:
        return float("nan")
    order = np.argsort(-scores, kind="mergesort")
    sorted_scores = scores[order]
    sorted_positive = positive[order]
    total_true_positive = 0
    total_seen = 0
    value = 0.0
    index = 0
    while index < len(sorted_scores):
        end = index + 1
        while end < len(sorted_scores) and sorted_scores[end] == sorted_scores[index]:
            end += 1
        group_positive = int(sorted_positive[index:end].sum())
        total_true_positive += group_positive
        total_seen += end - index
        if group_positive:
            value += (total_true_positive / total_seen) * (group_positive / p_count)
        index = end
    return float(value)


def _classification_input(joined: pd.DataFrame) -> pd.DataFrame:
    labels = joined["derived_binary_status"].map(lambda value: _canonical(value))
    return joined.loc[labels.isin({PRIMARY_POSITIVE_CLASS, PRIMARY_NEGATIVE_CLASS})].copy()


def classification_balance(joined: pd.DataFrame) -> dict[str, Any]:
    eligible = _classification_input(joined)
    labels = eligible["derived_binary_status"].map(_canonical)
    positive_n = int(labels.eq(PRIMARY_POSITIVE_CLASS).sum())
    negative_n = int(labels.eq(PRIMARY_NEGATIVE_CLASS).sum())
    total = positive_n + negative_n
    return {
        "classification_n": total,
        "developable_n": negative_n,
        "not_developable_n": positive_n,
        "positive_prevalence": (positive_n / total) if total else float("nan"),
        "blocked_endpoint_rows": int(len(joined) - total),
    }


def compute_classification_results(joined: pd.DataFrame) -> pd.DataFrame:
    _require_columns(joined, ("derived_binary_status", *FROZEN_RULE_FEATURES), "joined AIntibody primary table")
    eligible = _classification_input(joined)
    labels = eligible["derived_binary_status"].map(_canonical).eq(PRIMARY_POSITIVE_CLASS).to_numpy(dtype=bool)
    rows: list[dict[str, Any]] = []
    for feature in FROZEN_RULE_FEATURES:
        values = _oriented_predictor_values(feature, eligible[feature])
        mask = values.notna()
        scores = values.loc[mask].to_numpy(dtype=float)
        y_true = labels[mask.to_numpy()]
        n = int(len(scores))
        positive_n = int(y_true.sum())
        negative_n = int(n - positive_n)
        roc_auc = _roc_auc(y_true, scores) if n else float("nan")
        pr_auc = _pr_auc(y_true, scores) if n else float("nan")
        rows.append({
            "feature": feature,
            "n": n,
            "positive_n": positive_n,
            "negative_n": negative_n,
            "positive_prevalence": positive_n / n if n else float("nan"),
            "roc_auc": roc_auc,
            "pr_auc": pr_auc,
            "predictor_direction": _fixed_predictor_direction(feature),
            "control_or_rule": "CONTROL" if feature in CONTROL_FEATURES else "RULE",
            "notes": (
                "fixed lower-is-more-risk orientation from calculated_score semantics"
                if feature in CALCULATED_SCORE_FEATURES
                else "no post-hoc sign flip; no pre-registered fixed threshold, threshold metrics NOT_APPLICABLE"
            ),
        })
    return pd.DataFrame(rows, columns=CLASSIFICATION_RESULT_COLUMNS)


def rank_classification_results(results: pd.DataFrame, metric: str, limit: int = 10) -> pd.DataFrame:
    return results.sort_values(
        [metric, "feature"],
        ascending=[False, True],
        na_position="last",
        kind="mergesort",
    ).head(limit).reset_index(drop=True)


def _assay_missingness(joined: pd.DataFrame) -> dict[str, int]:
    return {assay: int(pd.to_numeric(joined[column], errors="coerce").notna().sum()) for assay, column in ASSAY_COLUMNS.items()}


def _summary_for_frame(joined: pd.DataFrame, assay_results: pd.DataFrame, classification_results: pd.DataFrame) -> dict[str, Any]:
    balance = classification_balance(joined)
    return {
        "rows": int(len(joined)),
        "assay_available_n": _assay_missingness(joined),
        **balance,
        "feature_assay_comparisons": int(len(assay_results)),
        "fdr_q_lt_0_05": int((assay_results["q_value"] < 0.05).sum()),
        "fdr_q_lt_0_10": int((assay_results["q_value"] < 0.10).sum()),
        "moderate_associations": int(((assay_results["abs_rho"] >= 0.40) & (assay_results["abs_rho"] < 0.60)).sum()),
        "strong_associations": int(((assay_results["abs_rho"] >= 0.60) & (assay_results["abs_rho"] < 0.80)).sum()),
        "very_strong_associations": int((assay_results["abs_rho"] >= 0.80).sum()),
        "direction_consistent_significant": int(
            ((assay_results["q_value"] < 0.05) & assay_results["direction_consistent"].eq("True")).sum()
        ),
        "classification_predictors": int(len(classification_results)),
        "threshold_metrics": "NOT_APPLICABLE for all predictors; no frozen predictor threshold exists",
    }


def _context_preserving_frame(source: pd.DataFrame, eligible_ids: set[str]) -> pd.DataFrame:
    eligible = source.loc[source["record_id"].map(_canonical).isin(eligible_ids)].copy()
    eligible["_context_signature"] = eligible.apply(lambda row: tuple(_canonical(row.get(field)) for field in CONTEXT_FIELDS), axis=1)
    rows: list[dict[str, Any]] = []
    for (sequence_hash, context_signature), group in eligible.groupby(["sequence_hash", "_context_signature"], sort=True, dropna=False):
        row: dict[str, Any] = {
            "sequence_hash": _canonical(sequence_hash),
            "derived_binary_status": None,
            "source_record_count": len(group),
        }
        for assay_column in PRIMARY_SOURCE_FIELDS.values():
            values = [value for value in (_numeric(item) for item in group[assay_column]) if value is not None]
            row[assay_column] = float(pd.Series(values).median()) if values else None
        scores = [value for value in (_numeric(item) for item in group[COMPOSITE_SCORE_FIELD]) if value is not None]
        row[COMPOSITE_SCORE_FIELD] = scores[0] if scores and len(set(scores)) == 1 else None
        row["derived_binary_status"] = (
            derive_composite_status(row[COMPOSITE_SCORE_FIELD])
            if scores and len(set(scores)) == 1
            else "BLOCKED_PENDING_REPLICATE_AGGREGATION" if scores else "BLOCKED_PENDING_ENDPOINT_DEFINITION"
        )
        rows.append(row)
    return pd.DataFrame(rows)


def load_sensitivity_frames(
    processed_path: str | Path,
    feature_path: str | Path,
    population_audit_path: str | Path,
) -> tuple[pd.DataFrame, pd.DataFrame, dict[str, Any]]:
    source = pd.read_csv(processed_path, dtype=object)
    population_audit = pd.read_csv(population_audit_path, dtype=object)
    _require_columns(source, ("record_id", "sequence_hash", COMPOSITE_SCORE_FIELD, *PRIMARY_SOURCE_FIELDS.values()), "processed source")
    _require_columns(population_audit, ("record_id", "population_assignment"), "population audit")
    eligible_ids = set(population_audit.loc[population_audit["population_assignment"] == "PRIMARY_ELIGIBLE", "record_id"].map(_canonical))
    feature_map, _ = load_feature_map(feature_path)
    eligible_source = source.loc[source["record_id"].map(_canonical).isin(eligible_ids)].copy()
    eligible_source["derived_binary_status"] = eligible_source[COMPOSITE_SCORE_FIELD].map(derive_composite_status)
    record_level = eligible_source.merge(feature_map, on="sequence_hash", how="left", validate="many_to_one")
    context_frame = _context_preserving_frame(source, eligible_ids).merge(feature_map, on="sequence_hash", how="left", validate="many_to_one")
    if record_level["sequence_hash"].isna().any() or context_frame["sequence_hash"].isna().any():
        raise ValueError("sensitivity feature join has unmatched sequence hashes")
    return record_level, context_frame, {
        "record_level_rows": int(len(record_level)),
        "context_preserving_rows": int(len(context_frame)),
        "eligible_source_ids": int(len(eligible_ids)),
    }


def _write_matrix(results: pd.DataFrame, value_column: str, path: Path) -> None:
    matrix = results.pivot(index="feature", columns="assay", values=value_column).reindex(index=FROZEN_RULE_FEATURES, columns=PRIMARY_ASSAYS)
    matrix.index.name = "feature"
    matrix.to_csv(path)


def _negative_findings(assay_results: pd.DataFrame, classification_results: pd.DataFrame) -> pd.DataFrame:
    rows: list[dict[str, Any]] = []
    for _, row in assay_results.loc[(assay_results["q_value"] >= 0.10) | assay_results["q_value"].isna()].iterrows():
        rows.append({
            "result_type": "continuous_assay",
            "feature": row["feature"],
            "assay": row["assay"],
            "metric": "rho",
            "value": row["rho"],
            "q_value": row["q_value"],
            "n": row["n"],
            "note": "non-significant or not estimable; retained",
        })
    for _, row in classification_results.iterrows():
        rows.append({
            "result_type": "composite_classification",
            "feature": row["feature"],
            "assay": "composite",
            "metric": "roc_auc",
            "value": row["roc_auc"],
            "q_value": float("nan"),
            "n": row["n"],
            "note": "complete predictor result retained; AUC below or near 0.5 is not reversed",
        })
    return pd.DataFrame(rows, columns=("result_type", "feature", "assay", "metric", "value", "q_value", "n", "note"))


def _fmt(value: Any, digits: int = 4) -> str:
    if value is None or (isinstance(value, float) and not np.isfinite(value)):
        return "NA"
    try:
        if pd.isna(value):
            return "NA"
    except (TypeError, ValueError):
        pass
    return f"{float(value):.{digits}g}" if isinstance(value, (float, int, np.number)) else str(value)


def _report(
    output_path: Path,
    summary: dict[str, Any],
    join_audit: dict[str, Any],
    assay_results: pd.DataFrame,
    classification_results: pd.DataFrame,
    top10: pd.DataFrame,
    roc_rank: pd.DataFrame,
    pr_rank: pd.DataFrame,
    sensitivity_summaries: Mapping[str, Mapping[str, Any]],
) -> None:
    lines = [
        "# AIntibody 2026 Phase 4D1B independent external validation",
        "",
        "This report is generated after the preregistered population and endpoint schema audit. It reports frozen-rule associations and discrimination metrics without tuning the rule system.",
        "",
        "## Frozen boundary",
        "",
        "- Preregistration checkpoint: `a2b986167cdfd606d4b4d6ddb9ce8f7668ad8806`.",
        "- Population audit checkpoint: `30b7bb7e5eb6d9105bd37075064574880efd7bb9`.",
        "- Frozen scientific baseline: `d1487ed74bdfc52fb0b2015a25c4e91ee90af66d`.",
        "- No rule/scoring tuning, threshold optimization, sign flipping after results, paired VH/VL score invention, or ML training was performed.",
        "",
        "## Primary population and join",
        "",
        f"- Primary analysis unit: `{PRIMARY_ANALYSIS_UNIT}`.",
        f"- Primary unique-sequence N: **{summary['rows']}**.",
        f"- Matched unique feature rows: **{join_audit['matched_unique_feature_rows']}**.",
        f"- Raw feature rows matching the primary hashes: **{join_audit['matched_raw_feature_rows']}**.",
        f"- Duplicate join rows retained only after equality verification: **{join_audit['duplicate_join_rows']}**.",
        f"- Unmatched population rows: **{join_audit['unmatched_population_rows']}**.",
        "- No silent population row loss occurred.",
        "",
        "## Experimental endpoints",
        "",
        *[f"- `{assay}` available N: **{summary['assay_available_n'][assay]}**; direction: `{ASSAY_DIRECTIONS[assay]}`." for assay in PRIMARY_ASSAYS],
        f"- Composite classification N: **{summary['classification_n']}**.",
        f"- DEVELOPABLE N: **{summary['developable_n']}**.",
        f"- NOT_DEVELOPABLE N: **{summary['not_developable_n']}**.",
        f"- Positive prevalence: **{_fmt(summary['positive_prevalence'], 5)}**.",
        f"- Positive class was fixed before analysis: `{PRIMARY_POSITIVE_CLASS}`.",
        f"- Blocked composite rows were excluded without imputation: **{summary['blocked_endpoint_rows']}**.",
        "- SPR, KinExA and KD fields were not used in primary analysis.",
        "",
        "## Continuous assay results",
        "",
        f"- Feature × assay comparisons: **{summary['feature_assay_comparisons']}**.",
        f"- FDR q < 0.05: **{summary['fdr_q_lt_0_05']}**.",
        f"- FDR q < 0.10: **{summary['fdr_q_lt_0_10']}**.",
        f"- Moderate associations: **{summary['moderate_associations']}**.",
        f"- Strong associations: **{summary['strong_associations']}**.",
        f"- Very strong associations: **{summary['very_strong_associations']}**.",
        f"- Direction-consistent significant associations: **{summary['direction_consistent_significant']}**.",
        "- All pairwise missing values were excluded only from the relevant comparison.",
        "",
        "### Top 10 continuous associations",
        "",
        "| Rank | Feature | Assay | rho | q | N | Direction consistent |",
        "|---:|---|---|---:|---:|---:|---|",
    ]
    for rank, (_, row) in enumerate(top10.iterrows(), 1):
        lines.append(f"| {rank} | `{row['feature']}` | `{row['assay']}` | {_fmt(row['rho'])} | {_fmt(row['q_value'])} | {int(row['n'])} | {row['direction_consistent']} |")
    if top10.empty:
        lines.append("No estimable associations.")

    lines.extend(["", "## Composite classification results", "", "ROC-AUC and PR-AUC were calculated independently for every frozen predictor. Predictor orientation was fixed before calculation; AUC values below 0.5 were retained.", "", "### Top ROC-AUC predictors", ""])
    for rank, (_, row) in enumerate(roc_rank.iterrows(), 1):
        lines.append(f"{rank}. `{row['feature']}`: ROC-AUC={_fmt(row['roc_auc'])}, PR-AUC={_fmt(row['pr_auc'])}, N={int(row['n'])}, {row['control_or_rule']}, direction={row['predictor_direction']}")
    lines.extend(["", "### Top PR-AUC predictors", ""])
    for rank, (_, row) in enumerate(pr_rank.iterrows(), 1):
        lines.append(f"{rank}. `{row['feature']}`: PR-AUC={_fmt(row['pr_auc'])}, ROC-AUC={_fmt(row['roc_auc'])}, N={int(row['n'])}, {row['control_or_rule']}, direction={row['predictor_direction']}")

    def feature_metric(feature: str, metric: str) -> str:
        rows = classification_results.loc[classification_results["feature"] == feature, metric]
        return _fmt(rows.iloc[0]) if not rows.empty else "NA"

    rule_rows = classification_results.loc[classification_results["control_or_rule"] == "RULE"].sort_values(["roc_auc", "feature"], ascending=[False, True], na_position="last", kind="mergesort")
    pr_rule_rows = classification_results.loc[classification_results["control_or_rule"] == "RULE"].sort_values(["pr_auc", "feature"], ascending=[False, True], na_position="last", kind="mergesort")
    control_rows = classification_results.loc[classification_results["control_or_rule"] == "CONTROL"].sort_values(["roc_auc", "feature"], ascending=[False, True], na_position="last", kind="mergesort")
    pr_control_rows = classification_results.loc[classification_results["control_or_rule"] == "CONTROL"].sort_values(["pr_auc", "feature"], ascending=[False, True], na_position="last", kind="mergesort")
    lines.extend([
        "",
        "### Required predictors and controls",
        "",
        f"- VH_rule_penalty ROC-AUC: **{feature_metric('VH_rule_penalty', 'roc_auc')}**; PR-AUC: **{feature_metric('VH_rule_penalty', 'pr_auc')}**.",
        f"- VL_rule_penalty ROC-AUC: **{feature_metric('VL_rule_penalty', 'roc_auc')}**; PR-AUC: **{feature_metric('VL_rule_penalty', 'pr_auc')}**.",
        f"- Best rule-feature ROC-AUC: **{rule_rows.iloc[0]['feature'] if not rule_rows.empty else 'NA'}** ({_fmt(rule_rows.iloc[0]['roc_auc']) if not rule_rows.empty else 'NA'}).",
        f"- Best rule-feature PR-AUC: **{pr_rule_rows.iloc[0]['feature'] if not pr_rule_rows.empty else 'NA'}** ({_fmt(pr_rule_rows.iloc[0]['pr_auc']) if not pr_rule_rows.empty else 'NA'}).",
        f"- Best control ROC-AUC: **{control_rows.iloc[0]['feature'] if not control_rows.empty else 'NA'}** ({_fmt(control_rows.iloc[0]['roc_auc']) if not control_rows.empty else 'NA'}).",
        f"- Best control PR-AUC: **{pr_control_rows.iloc[0]['feature'] if not pr_control_rows.empty else 'NA'}** ({_fmt(pr_control_rows.iloc[0]['pr_auc']) if not pr_control_rows.empty else 'NA'}).",
        "- Sequence length controls are reported separately and are not hidden if comparable to rule predictors.",
        "- No frozen predictor had a genuine pre-existing endpoint threshold; sensitivity, specificity, precision, recall and F1 are `NOT_APPLICABLE`.",
        "",
        "## Sensitivity analyses",
        "",
    ])
    for name, item in sensitivity_summaries.items():
        lines.append(f"- `{name}`: rows={item['rows']}, classification N={item['classification_n']}, DEVELOPABLE N={item['developable_n']}, NOT_DEVELOPABLE N={item['not_developable_n']}.")
    lines.extend([
        "- Primary results remain the unique-sequence, preregistered population results.",
        "- Record-level and context-preserving duplicate-aware results are separate sensitivity outputs and do not replace primary results.",
        "- Controls and parentals remain excluded from the primary benchmark; no outcome-driven inclusion was performed.",
        "",
        "## Jain comparison",
        "",
        "Phase 4C Jain contained 576 feature-assay comparisons, with 0 q < 0.05, 0 moderate/strong/very strong associations. AIntibody results are an independent dataset-specific assessment; they are not used to tune either dataset.",
        "",
        "## Interpretation and limitations",
        "",
        "1. Independent AIntibody validation supports only the specific frozen associations and discrimination metrics reported in the CSV outputs.",
        "2. It does not establish clinical utility, causal relationships, therapeutic efficacy, or a general developability predictor.",
        "3. Results that are weak, null, direction-opposed, or below chance are preserved.",
        "4. Agreement with Jain would reinforce limited broad-developability scope; disagreement would indicate dataset- or assay-dependent behavior, not permission to tune the rules.",
        "5. The current system is best described as liability screening. Broad developability prediction is not established by this analysis alone.",
        "6. Correlation does not establish causation. AUC does not establish clinical utility. Liability screening and broad developability prediction are distinct.",
        "",
        "## Reproducibility outputs",
        "",
        "- `aintibody_assay_results.csv`: complete frozen feature × assay results.",
        "- `aintibody_classification_results.csv`: complete frozen predictor classification results.",
        "- `aintibody_spearman_matrix.csv` and `aintibody_qvalue_matrix.csv`: deterministic matrices.",
        "- `aintibody_top10_associations.csv`, ranking tables, and negative/null findings preserve deterministic summaries.",
        "- Sensitivity output files are prefixed `aintibody_sensitivity_` and are kept separate from primary results.",
    ])
    output_path.write_text("\n".join(lines) + "\n", encoding="utf-8")


def _write_analysis_set(output_dir: Path, prefix: str, joined: pd.DataFrame) -> tuple[pd.DataFrame, pd.DataFrame, dict[str, Any], pd.DataFrame, pd.DataFrame, pd.DataFrame]:
    assay_results = compute_assay_results(joined)
    classification_results = compute_classification_results(joined)
    summary = _summary_for_frame(joined, assay_results, classification_results)
    top10 = assay_results.loc[assay_results["rho"].notna()].sort_values(
        ["abs_rho", "q_value", "feature", "assay"], ascending=[False, True, True, True], na_position="last", kind="mergesort"
    ).head(10).loc[:, ["feature", "assay", "rho", "q_value", "n", "direction_consistent"]].reset_index(drop=True)
    roc_rank = rank_classification_results(classification_results, "roc_auc")
    pr_rank = rank_classification_results(classification_results, "pr_auc")
    assay_results.to_csv(output_dir / f"{prefix}assay_results.csv", index=False)
    classification_results.to_csv(output_dir / f"{prefix}classification_results.csv", index=False)
    return assay_results, classification_results, summary, top10, roc_rank, pr_rank


def run_external_validation(
    primary_path: str | Path,
    feature_path: str | Path,
    processed_path: str | Path,
    population_audit_path: str | Path,
    output_dir: str | Path,
    report_path: str | Path,
) -> dict[str, Any]:
    output_root = Path(output_dir)
    output_root.mkdir(parents=True, exist_ok=True)
    Path(report_path).parent.mkdir(parents=True, exist_ok=True)
    primary, join_audit = load_primary_join(primary_path, feature_path)

    # Primary analysis is completed and written first. Sensitivity analyses are
    # explicitly separate and cannot overwrite primary result files.
    assay_results, classification_results, summary, top10, roc_rank, pr_rank = _write_analysis_set(output_root, "aintibody_", primary)
    _write_matrix(assay_results, "rho", output_root / "aintibody_spearman_matrix.csv")
    _write_matrix(assay_results, "q_value", output_root / "aintibody_qvalue_matrix.csv")
    top10.to_csv(output_root / "aintibody_top10_associations.csv", index=False)
    roc_rank.to_csv(output_root / "aintibody_top_roc_auc.csv", index=False)
    pr_rank.to_csv(output_root / "aintibody_top_pr_auc.csv", index=False)
    negative = _negative_findings(assay_results, classification_results)
    negative.to_csv(output_root / "aintibody_negative_null_findings.csv", index=False)

    record_level, context_preserving, sensitivity_input_audit = load_sensitivity_frames(processed_path, feature_path, population_audit_path)
    sensitivity_summaries: dict[str, dict[str, Any]] = {}
    for name, frame in (("record_level", record_level), ("context_preserving", context_preserving)):
        prefix = f"aintibody_sensitivity_{name}_"
        sens_assay, sens_class, sens_summary, _, _, _ = _write_analysis_set(output_root, prefix, frame)
        sensitivity_summaries[name] = sens_summary

    summary.update({
        "dataset": DATASET,
        "join_audit": join_audit,
        "sensitivity_input_audit": sensitivity_input_audit,
        "sensitivity_summaries": sensitivity_summaries,
        "positive_class": PRIMARY_POSITIVE_CLASS,
        "threshold_optimization_performed": False,
        "sign_flipping_performed": False,
        "paired_vh_vl_score_invented": False,
        "affinity_used_in_primary_analysis": False,
        "ml_introduced": False,
        "negative_results_preserved": True,
        "primary_population_frozen": True,
        "duplicate_handling_frozen": True,
        "endpoint_schema_frozen": True,
    })
    (output_root / "aintibody_join_audit.json").write_text(json.dumps({"primary": join_audit, "sensitivity": sensitivity_input_audit}, indent=2, ensure_ascii=False, default=str) + "\n", encoding="utf-8")
    (output_root / "aintibody_analysis_summary.json").write_text(json.dumps(summary, indent=2, ensure_ascii=False, default=str) + "\n", encoding="utf-8")
    _report(Path(report_path), summary, join_audit, assay_results, classification_results, top10, roc_rank, pr_rank, sensitivity_summaries)
    return {"summary": summary, "join_audit": join_audit, "sensitivity_input_audit": sensitivity_input_audit}


def main() -> None:
    root = Path(__file__).resolve().parents[2]
    output_dir = root / "validation/data/external_validation"
    run_external_validation(
        root / "validation/data/external_validation/aintibody_primary_population.csv",
        root / "validation/data/features/aintibody_rule_features.csv",
        root / "validation/data/processed/aintibody_2026.csv",
        root / "validation/data/external_validation/aintibody_population_audit.csv",
        output_dir,
        root / "validation/reports/aintibody_external/report.md",
    )


if __name__ == "__main__":
    main()
