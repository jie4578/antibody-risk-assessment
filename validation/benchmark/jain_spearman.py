"""Jain-only retrospective Spearman benchmark for frozen rule features.

This module intentionally has no path or import for the external validation
dataset. It reads one Jain processed table, one Jain rule-feature table and
the Jain assay dictionary. Experimental values are used only as benchmark
outcomes, never for feature construction, filtering or threshold selection.
"""

from __future__ import annotations

import json
import math
from pathlib import Path
from typing import Any, Mapping, Sequence

import numpy as np
import pandas as pd
from scipy.stats import spearmanr

from validation.features.feature_schema import CATEGORY_FIELD_MAP


JAIN_ASSAYS = (
    "HEK Titer (mg/L)",
    "Fab Tm by DSF (°C)",
    "SGAC-SINS AS100 ((NH4)2SO4 mM)",
    "HIC Retention Time (Min)a",
    "SMAC Retention Time (Min)a",
    "Slope for Accelerated Stability",
    "Poly-Specificity Reagent (PSR) SMP Score (0-1)",
    "Affinity-Capture Self-Interaction Nanoparticle Spectroscopy (AC-SINS) ∆λmax (nm) Average",
    "CIC Retention Time (Min)",
    "CSI-BLI Delta Response (nm)",
    "ELISA",
    "BVP ELISA",
)

SCORE_FEATURES = (
    "VH_calculated_score",
    "VL_calculated_score",
    "VH_rule_penalty",
    "VL_rule_penalty",
)

COUNT_FEATURES = (
    "VH_total_sites",
    "VL_total_sites",
    "total_sites_combined",
    "VH_cdr_sites",
    "VL_cdr_sites",
    "cdr_sites_combined",
    "VH_ptm_sites",
    "VL_ptm_sites",
    "ptm_sites_combined",
    "VH_liability_sites",
    "VL_liability_sites",
    "liability_sites_combined",
    *(f"VH_{field}" for field in CATEGORY_FIELD_MAP.values()),
    *(f"VL_{field}" for field in CATEGORY_FIELD_MAP.values()),
    *(f"{field}_combined" for field in CATEGORY_FIELD_MAP.values()),
    *(f"VH_cdr_{field}" for field in CATEGORY_FIELD_MAP.values()),
    *(f"VL_cdr_{field}" for field in CATEGORY_FIELD_MAP.values()),
    *(f"cdr_{field}_combined" for field in CATEGORY_FIELD_MAP.values()),
)

CONTROL_FEATURES = ("VH_length", "VL_length")
BENCHMARK_FEATURES = (*SCORE_FEATURES, *COUNT_FEATURES, *CONTROL_FEATURES)

ALLOWED_DIRECTIONS = {
    "higher_unfavorable",
    "lower_unfavorable",
    "context_dependent",
    "UNKNOWN",
}

RESULT_COLUMNS = (
    "feature",
    "assay",
    "rho",
    "abs_rho",
    "p_value",
    "q_value",
    "n",
    "effect_size_label",
    "assay_direction",
    "interpretation_allowed",
)


def _cell(value: Any) -> str:
    if value is None:
        return ""
    try:
        if pd.isna(value):
            return ""
    except (TypeError, ValueError):
        pass
    return str(value).strip()


def _require_columns(frame: pd.DataFrame, columns: Sequence[str], label: str) -> None:
    missing = [column for column in columns if column not in frame.columns]
    if missing:
        raise ValueError(f"{label} missing required columns: {', '.join(missing)}")


def load_jain_inputs(
    experimental_path: str | Path,
    feature_path: str | Path,
    *,
    expected_rows: int | None = 137,
) -> tuple[pd.DataFrame, dict[str, Any]]:
    """Join Jain assay and rule-feature records with one-to-one safeguards."""

    experimental = pd.read_csv(experimental_path)
    features = pd.read_csv(feature_path)
    _require_columns(experimental, ("record_id", "antibody_id", *JAIN_ASSAYS), "Jain experimental table")
    _require_columns(features, ("record_id", "antibody_id", *BENCHMARK_FEATURES), "Jain feature table")

    experimental_ids = experimental["record_id"].map(_cell)
    feature_ids = features["record_id"].map(_cell)
    duplicate_experimental = sorted(experimental_ids[experimental_ids.duplicated(keep=False)].unique().tolist())
    duplicate_features = sorted(feature_ids[feature_ids.duplicated(keep=False)].unique().tolist())
    if duplicate_experimental or duplicate_features:
        raise ValueError("Jain record_id must be unique in both benchmark inputs")

    exp = experimental.copy()
    feat = features.copy()
    exp["_join_record_id"] = experimental_ids
    feat["_join_record_id"] = feature_ids
    merged = exp.merge(
        feat,
        on="_join_record_id",
        how="outer",
        indicator=True,
        suffixes=("_assay", "_feature"),
        validate="one_to_one",
    )
    matched = merged.loc[merged["_merge"] == "both"].copy()
    experimental_only = sorted(merged.loc[merged["_merge"] == "left_only", "_join_record_id"].tolist())
    feature_only = sorted(merged.loc[merged["_merge"] == "right_only", "_join_record_id"].tolist())

    if experimental_only or feature_only:
        raise ValueError(f"Jain join has unmatched records: experimental_only={experimental_only}, feature_only={feature_only}")
    if expected_rows is not None and len(matched) != expected_rows:
        raise ValueError(f"Jain matched rows {len(matched)} != expected {expected_rows}")

    for row in matched.itertuples(index=False):
        assay_id = _cell(getattr(row, "antibody_id_assay"))
        feature_id = _cell(getattr(row, "antibody_id_feature"))
        if assay_id != feature_id:
            raise ValueError(f"Jain antibody_id mismatch for record_id {_cell(getattr(row, '_join_record_id'))}")

    joined = pd.DataFrame({
        "record_id": matched["_join_record_id"].tolist(),
        "antibody_id": matched["antibody_id_feature"].map(_cell).tolist(),
        **{column: matched[column].tolist() for column in JAIN_ASSAYS},
        **{column: matched[column].tolist() for column in BENCHMARK_FEATURES},
    })
    audit = {
        "experimental_rows": int(len(experimental)),
        "feature_rows": int(len(features)),
        "matched_rows": int(len(joined)),
        "unmatched_experimental_rows": int(len(experimental_only)),
        "unmatched_feature_rows": int(len(feature_only)),
        "duplicate_experimental_ids": duplicate_experimental,
        "duplicate_feature_ids": duplicate_features,
        "join_key": "record_id",
        "antibody_id_cross_checked": True,
    }
    return joined, audit


def load_assay_directions(dictionary_path: str | Path) -> dict[str, str]:
    """Read only the local Jain data dictionary's documented direction field."""

    dictionary = pd.read_csv(dictionary_path)
    _require_columns(dictionary, ("original_name", "direction_of_unfavorable_value"), "Jain data dictionary")
    directions: dict[str, str] = {}
    for assay in JAIN_ASSAYS:
        rows = dictionary.loc[dictionary["original_name"].map(_cell) == assay]
        if len(rows) != 1:
            raise ValueError(f"Jain data dictionary must contain exactly one entry for assay: {assay}")
        direction = _cell(rows.iloc[0]["direction_of_unfavorable_value"]) or "UNKNOWN"
        if direction not in ALLOWED_DIRECTIONS:
            direction = "UNKNOWN"
        directions[assay] = direction
    return directions


def benjamini_hochberg(p_values: Sequence[float]) -> np.ndarray:
    """Return BH-adjusted q-values, preserving NaN for non-estimable tests."""

    values = np.asarray(p_values, dtype=float)
    q_values = np.full(values.shape, np.nan, dtype=float)
    valid = np.isfinite(values)
    if not valid.any():
        return q_values
    indices = np.flatnonzero(valid)
    order = indices[np.argsort(values[valid], kind="mergesort")]
    ranked = values[order] * len(order) / np.arange(1, len(order) + 1, dtype=float)
    adjusted = np.minimum.accumulate(ranked[::-1])[::-1]
    q_values[order] = np.minimum(adjusted, 1.0)
    return q_values


def effect_size_label(abs_rho: float) -> str:
    if not np.isfinite(abs_rho):
        return "not estimable"
    if abs_rho < 0.20:
        return "very weak"
    if abs_rho < 0.40:
        return "weak"
    if abs_rho < 0.60:
        return "moderate"
    if abs_rho < 0.80:
        return "strong"
    return "very strong"


def compute_spearman_results(
    joined: pd.DataFrame,
    directions: Mapping[str, str],
) -> pd.DataFrame:
    """Calculate pairwise-complete Spearman rho and two-sided p-values."""

    _require_columns(joined, (*JAIN_ASSAYS, *BENCHMARK_FEATURES), "Joined Jain benchmark table")
    rows: list[dict[str, Any]] = []
    for feature in BENCHMARK_FEATURES:
        x = pd.to_numeric(joined[feature], errors="coerce")
        for assay in JAIN_ASSAYS:
            y = pd.to_numeric(joined[assay], errors="coerce")
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
                "effect_size_label": effect_size_label(abs(rho) if np.isfinite(rho) else float("nan")),
                "assay_direction": directions[assay],
                "interpretation_allowed": "directional_association" if directions[assay] != "UNKNOWN" else "association_only",
            })
    result = pd.DataFrame(rows, columns=RESULT_COLUMNS)
    result["q_value"] = benjamini_hochberg(result["p_value"].to_numpy(dtype=float))
    return result


def rank_top_associations(results: pd.DataFrame, limit: int = 10) -> pd.DataFrame:
    ranked = results.loc[results["rho"].notna()].copy()
    ranked = ranked.sort_values(
        ["abs_rho", "q_value", "feature", "assay"],
        ascending=[False, True, True, True],
        na_position="last",
        kind="mergesort",
    )
    return ranked.head(limit).loc[:, ["feature", "assay", "rho", "p_value", "q_value", "n", "assay_direction"]].reset_index(drop=True)


def assay_missingness(joined: pd.DataFrame) -> dict[str, dict[str, Any]]:
    missing: dict[str, dict[str, Any]] = {}
    total = len(joined)
    for assay in JAIN_ASSAYS:
        values = pd.to_numeric(joined[assay], errors="coerce")
        missing_n = int(values.isna().sum())
        missing[assay] = {
            "total_n": total,
            "non_missing_n": total - missing_n,
            "missing_n": missing_n,
            "missing_percentage": round((missing_n / total * 100) if total else 0.0, 4),
        }
    return missing


def _write_heatmap(
    results: pd.DataFrame,
    *,
    value_column: str,
    title: str,
    output_path: Path,
    colorbar_label: str,
    transform=None,
) -> None:
    import matplotlib

    matplotlib.use("Agg")
    import matplotlib.pyplot as plt

    matrix = results.pivot(index="feature", columns="assay", values=value_column).reindex(index=BENCHMARK_FEATURES, columns=JAIN_ASSAYS)
    values = matrix.to_numpy(dtype=float)
    if transform is not None:
        plotted = transform(values)
    else:
        plotted = values
    height = max(9.0, len(BENCHMARK_FEATURES) * 0.36)
    fig, ax = plt.subplots(figsize=(16, height), dpi=160)
    masked = np.ma.masked_invalid(plotted)
    image = ax.imshow(masked, aspect="auto", cmap="coolwarm" if value_column == "rho" else "viridis")
    ax.set_xticks(np.arange(len(JAIN_ASSAYS)), labels=JAIN_ASSAYS, rotation=65, ha="right", fontsize=7)
    ax.set_yticks(np.arange(len(BENCHMARK_FEATURES)), labels=BENCHMARK_FEATURES, fontsize=7)
    ax.set_xlabel("Jain assay (source column name)")
    ax.set_ylabel("Frozen rule feature")
    ax.set_title(title)
    fig.colorbar(image, ax=ax, label=colorbar_label, fraction=0.025, pad=0.02)
    rho_matrix = results.pivot(index="feature", columns="assay", values="rho").reindex(index=BENCHMARK_FEATURES, columns=JAIN_ASSAYS)
    q_matrix = results.pivot(index="feature", columns="assay", values="q_value").reindex(index=BENCHMARK_FEATURES, columns=JAIN_ASSAYS)
    n_matrix = results.pivot(index="feature", columns="assay", values="n").reindex(index=BENCHMARK_FEATURES, columns=JAIN_ASSAYS)
    for row_index in range(values.shape[0]):
        for column_index in range(values.shape[1]):
            value = values[row_index, column_index]
            n = n_matrix.iat[row_index, column_index]
            rho = rho_matrix.iat[row_index, column_index]
            q_value = q_matrix.iat[row_index, column_index]
            if np.isfinite(rho) or np.isfinite(q_value):
                rho_label = f"rho={rho:.2f}" if np.isfinite(rho) else "rho=NA"
                q_label = f"q={q_value:.2g}" if np.isfinite(q_value) else "q=NA"
                label = f"{rho_label}\n{q_label}\nN={int(n)}"
                ax.text(column_index, row_index, label, ha="center", va="center", fontsize=4.5, color="black")
    fig.tight_layout()
    fig.savefig(output_path, bbox_inches="tight")
    plt.close(fig)


def _write_top_scatter(results: pd.DataFrame, joined: pd.DataFrame, output_dir: Path, rank: int, row: pd.Series) -> str:
    import matplotlib

    matplotlib.use("Agg")
    import matplotlib.pyplot as plt

    feature = row["feature"]
    assay = row["assay"]
    x = pd.to_numeric(joined[feature], errors="coerce")
    y = pd.to_numeric(joined[assay], errors="coerce")
    mask = x.notna() & y.notna()
    fig, ax = plt.subplots(figsize=(7.5, 5.5), dpi=160)
    ax.scatter(x.loc[mask], y.loc[mask], s=18, alpha=0.75, color="#2b6cb0", edgecolors="none")
    ax.set_xlabel(feature)
    ax.set_ylabel(assay)
    ax.set_title(f"Jain association {rank:02d}\nrho={row['rho']:.3f}, q={row['q_value']:.3g}, N={int(row['n'])}")
    ax.grid(True, alpha=0.25)
    fig.tight_layout()
    filename = f"top_{rank:02d}_scatter.png"
    fig.savefig(output_dir / filename, bbox_inches="tight")
    plt.close(fig)
    return filename


def _format_value(value: Any, digits: int = 4) -> str:
    if value is None or (isinstance(value, float) and not math.isfinite(value)):
        return "NA"
    try:
        if pd.isna(value):
            return "NA"
    except (TypeError, ValueError):
        pass
    return f"{float(value):.{digits}g}" if isinstance(value, (float, int, np.number)) else str(value)


def _write_report(
    results: pd.DataFrame,
    joined: pd.DataFrame,
    input_audit: Mapping[str, Any],
    directions: Mapping[str, str],
    missingness: Mapping[str, Mapping[str, Any]],
    top10: pd.DataFrame,
    scatter_files: Sequence[str],
    output_path: Path,
) -> None:
    significant = results.loc[results["q_value"] < 0.05].copy()
    exploratory = results.loc[results["q_value"] < 0.10].copy()
    moderate = results.loc[(results["abs_rho"] >= 0.40) & (results["abs_rho"] < 0.60)].copy()
    strong = results.loc[(results["abs_rho"] >= 0.60) & (results["abs_rho"] < 0.80)].copy()
    very_strong = results.loc[results["abs_rho"] >= 0.80].copy()
    weak_null = results.loc[results["abs_rho"] < 0.20].copy()
    score_rows = results.loc[results["feature"].isin(SCORE_FEATURES)].sort_values(["abs_rho", "q_value", "feature", "assay"], ascending=[False, True, True, True], na_position="last", kind="mergesort").head(8)
    length_rows = results.loc[results["feature"].isin(CONTROL_FEATURES)].sort_values(["abs_rho", "q_value", "feature", "assay"], ascending=[False, True, True, True], na_position="last", kind="mergesort").head(8)

    lines = [
        "# Jain 2017 retrospective rule benchmark",
        "",
        "## Objective",
        "",
        "This benchmark measures retrospective rank association between the frozen Antibody AI rule-system outputs and the 12 experimental Jain 2017 assay columns. It is not rule optimization or biological validation.",
        "",
        "## Frozen boundary",
        "",
        "- Frozen scientific baseline: `d1487ed74bdfc52fb0b2015a25c4e91ee90af66d`.",
        "- Phase 4B feature checkpoint: `ec3a2221b6f9f68d3ea0171c8ae9a524d17fc554`.",
        "- No rule weights, thresholds, CDR definitions or production code were changed.",
        "- Only Jain 2017 was read. The external validation dataset was not inspected.",
        "",
        "## Dataset and join",
        "",
        f"- Experimental rows: {input_audit['experimental_rows']}",
        f"- Feature rows: {input_audit['feature_rows']}",
        f"- Matched rows: {input_audit['matched_rows']}",
        f"- Unmatched rows: {input_audit['unmatched_experimental_rows'] + input_audit['unmatched_feature_rows']}",
        f"- Join key: `{input_audit['join_key']}` with antibody ID cross-check.",
        "",
        "## Feature set",
        "",
        f"{len(BENCHMARK_FEATURES)} numeric features were tested. Chain scores and penalties were analyzed separately. No paired VH/VL score was created. `VH_length` and `VL_length` are CONTROL / DESCRIPTIVE variables.",
        "",
        "## Assays and missingness",
        "",
    ]
    for assay in JAIN_ASSAYS:
        item = missingness[assay]
        lines.append(f"- `{assay}`: total N={item['total_n']}, non-missing N={item['non_missing_n']}, missing N={item['missing_n']} ({item['missing_percentage']}%).")
    lines.extend([
        "",
        "## Statistical method",
        "",
        "Spearman rank correlation was calculated for every feature × assay pair using pairwise complete observations. Missing values were not imputed. Two-sided p-values were adjusted across all comparisons with Benjamini-Hochberg FDR. The primary threshold is q < 0.05; q < 0.10 is exploratory only.",
        "",
        "Effect-size labels are descriptive only: very weak (<0.20), weak (0.20–<0.40), moderate (0.40–<0.60), strong (0.60–<0.80), and very strong (≥0.80).",
        "",
        "## Top 10 absolute associations",
        "",
        "| Rank | Feature | Assay | rho | p | q | N | Directionality |",
        "|---:|---|---|---:|---:|---:|---:|---|",
    ])
    for rank, (_, row) in enumerate(top10.iterrows(), 1):
        lines.append(f"| {rank} | `{row['feature']}` | `{row['assay']}` | {_format_value(row['rho'], 4)} | {_format_value(row['p_value'], 4)} | {_format_value(row['q_value'], 4)} | {int(row['n'])} | {row['assay_direction']} |")
    if top10.empty:
        lines.append("No estimable associations.")

    def section_rows(title: str, frame: pd.DataFrame) -> None:
        lines.extend(["", f"## {title}", ""])
        if frame.empty:
            lines.append("None under the documented criterion.")
            return
        for _, row in frame.head(30).iterrows():
            lines.append(f"- `{row['feature']}` × `{row['assay']}`: rho={_format_value(row['rho'], 4)}, q={_format_value(row['q_value'], 4)}, N={int(row['n'])}, directionality={row['assay_direction']}.")
        if len(frame) > 30:
            lines.append(f"- Additional rows are retained in the generated result CSV ({len(frame) - 30} more).")

    section_rows(f"FDR-significant associations (q < 0.05; count={len(significant)})", significant.sort_values(["q_value", "abs_rho", "feature", "assay"], ascending=[True, False, True, True], kind="mergesort"))
    section_rows(f"Exploratory associations (q < 0.10; count={len(exploratory)})", exploratory.sort_values(["q_value", "abs_rho", "feature", "assay"], ascending=[True, False, True, True], kind="mergesort"))
    section_rows(f"Moderate associations (0.40 ≤ |rho| < 0.60; count={len(moderate)})", moderate.sort_values(["abs_rho", "q_value", "feature", "assay"], ascending=[False, True, True, True], kind="mergesort"))
    section_rows(f"Strong associations (0.60 ≤ |rho| < 0.80; count={len(strong)})", strong.sort_values(["abs_rho", "q_value", "feature", "assay"], ascending=[False, True, True, True], kind="mergesort"))
    section_rows(f"Very strong associations (|rho| ≥ 0.80; count={len(very_strong)})", very_strong.sort_values(["abs_rho", "q_value", "feature", "assay"], ascending=[False, True, True, True], kind="mergesort"))
    section_rows(f"Weak or null findings (|rho| < 0.20; count={len(weak_null)})", weak_null.sort_values(["abs_rho", "q_value", "feature", "assay"], ascending=[True, True, True, True], kind="mergesort"))

    section_rows("Rule score and penalty findings", score_rows)
    lines.extend(["", "The native calculated score retains its production semantics: higher calculated score means fewer or lower rule penalties. The validation-only rule penalty is `100 - calculated_score`, where higher values mean greater rule-derived penalty. Neither is called a risk probability or experimentally validated outcome."])
    section_rows("Control sequence-length findings", length_rows)
    lines.extend(["", "Length variables are CONTROL / DESCRIPTIVE. Any similarity between a length association and a rule-feature association is a possible confounding interpretation; no adjustment model was performed."])

    lines.extend([
        "",
        "## Assay directionality",
        "",
        "The local Jain data dictionary marks all 12 assay directions as `UNKNOWN`; no local source definition was sufficient to assign an unfavorable direction without guessing. Therefore the results support only positive/negative association statements, not claims that higher rule risk predicts worse assay performance.",
        "",
        "## Negative findings and limitations",
        "",
        "- Weak and null relationships are retained in `weak_or_null_findings.csv`; no result was manually removed.",
        "- Correlation does not establish causation.",
        "- Sequence liability rules are not equivalent to developability assays.",
        "- Jain is retrospective and may contain assay-specific protocol effects.",
        "- No rule tuning, cutoff optimization or ML training was performed.",
        "- The external validation dataset was not inspected and remains reserved for independent validation.",
        "- Therapeutic efficacy and affinity are not evaluated here.",
        "",
        "## Reproducible outputs",
        "",
        "- `data/benchmark/jain_spearman_results.csv`: complete feature × assay results with pairwise N.",
        "- `data/benchmark/jain_spearman_matrix.csv`: rho matrix.",
        "- `data/benchmark/jain_qvalue_matrix.csv`: BH-FDR q-value matrix.",
        "- `data/benchmark/jain_pairwise_n_matrix.csv`: pairwise N matrix.",
        "- `data/benchmark/top10_associations.csv`: deterministic top 10 table.",
        "- `data/benchmark/weak_or_null_findings.csv`: retained weak/null relationships.",
        f"- Top scatter plots: {', '.join(scatter_files) if scatter_files else 'none'}.",
        "",
    ])
    output_path.write_text("\n".join(lines), encoding="utf-8")


def write_benchmark(
    experimental_path: str | Path,
    feature_path: str | Path,
    dictionary_path: str | Path,
    *,
    output_dir: str | Path,
    report_dir: str | Path,
) -> dict[str, Any]:
    """Generate all Jain benchmark tables, figures and report."""

    output_root = Path(output_dir)
    report_root = Path(report_dir)
    output_root.mkdir(parents=True, exist_ok=True)
    report_root.mkdir(parents=True, exist_ok=True)
    joined, input_audit = load_jain_inputs(experimental_path, feature_path)
    directions = load_assay_directions(dictionary_path)
    results = compute_spearman_results(joined, directions)
    missingness = assay_missingness(joined)
    top10 = rank_top_associations(results)
    weak_null = results.loc[results["abs_rho"] < 0.20].copy()

    results.to_csv(output_root / "jain_spearman_results.csv", index=False)
    for column, filename in (("rho", "jain_spearman_matrix.csv"), ("q_value", "jain_qvalue_matrix.csv"), ("n", "jain_pairwise_n_matrix.csv")):
        matrix = results.pivot(index="feature", columns="assay", values=column).reindex(index=BENCHMARK_FEATURES, columns=JAIN_ASSAYS)
        matrix.index.name = "feature"
        matrix.to_csv(output_root / filename)
    top10.to_csv(output_root / "top10_associations.csv", index=False)
    weak_null.to_csv(output_root / "weak_or_null_findings.csv", index=False)

    n_min = int(results["n"].min())
    n_max = int(results["n"].max())
    _write_heatmap(
        results,
        value_column="rho",
        title=f"Jain 2017 frozen-rule Spearman rho (pairwise N range {n_min}–{n_max})",
        output_path=report_root / "correlation_heatmap.png",
        colorbar_label="Spearman rho",
    )
    _write_heatmap(
        results,
        value_column="q_value",
        title=f"Jain 2017 BH-FDR q-values (rho/N retained per cell; pairwise N range {n_min}–{n_max})",
        output_path=report_root / "qvalue_heatmap.png",
        colorbar_label="-log10(q-value)",
        transform=lambda values: -np.log10(np.clip(values, 1e-300, 1.0)),
    )
    scatter_files = [_write_top_scatter(results, joined, report_root, rank, row) for rank, (_, row) in enumerate(top10.head(3).iterrows(), 1)]

    summary = {
        "frozen_scientific_baseline": "d1487ed74bdfc52fb0b2015a25c4e91ee90af66d",
        "feature_checkpoint": "ec3a2221b6f9f68d3ea0171c8ae9a524d17fc554",
        "dataset": "jain_2017",
        "input_audit": input_audit,
        "feature_count": len(BENCHMARK_FEATURES),
        "assay_count": len(JAIN_ASSAYS),
        "comparison_count": int(len(results)),
        "assay_missingness": missingness,
        "counts": {
            "fdr_q_lt_0_05": int((results["q_value"] < 0.05).sum()),
            "exploratory_q_lt_0_10": int((results["q_value"] < 0.10).sum()),
            "moderate": int(((results["abs_rho"] >= 0.40) & (results["abs_rho"] < 0.60)).sum()),
            "strong": int(((results["abs_rho"] >= 0.60) & (results["abs_rho"] < 0.80)).sum()),
            "very_strong": int((results["abs_rho"] >= 0.80).sum()),
            "weak_or_very_weak": int((results["abs_rho"] < 0.40).sum()),
            "not_estimable": int(results["rho"].isna().sum()),
        },
        "directionality": directions,
        "external_validation_dataset_accessed": False,
        "experimental_values_imputed": False,
        "feature_selection_from_assays": False,
        "scatter_files": scatter_files,
    }
    (report_root / "jain_benchmark_audit.json").write_text(json.dumps(summary, indent=2, ensure_ascii=False), encoding="utf-8")
    _write_report(results, joined, input_audit, directions, missingness, top10, scatter_files, report_root / "report.md")
    return summary
