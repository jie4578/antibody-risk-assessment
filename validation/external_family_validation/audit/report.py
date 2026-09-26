"""Render the Phase 7B-A sequence-space audit without biological inference."""

from __future__ import annotations

from pathlib import Path
from typing import Any

import pandas as pd


GERMLINE_FIELDS = ("IGHV", "IGKV", "IGLV")


def audit_germline_columns(source_columns: list[str], source_path: str | Path | None = None) -> dict[str, Any]:
    """Use source annotations only; identity clusters never become germlines."""

    matching = [column for column in source_columns if any(token in column.upper() for token in GERMLINE_FIELDS)]
    counts: dict[str, dict[str, int] | None] = {field: None for field in GERMLINE_FIELDS}
    if matching and source_path is not None:
        annotated = pd.read_csv(source_path, usecols=matching, dtype=str, keep_default_na=False)
        for field in GERMLINE_FIELDS:
            columns = [column for column in matching if field in column.upper()]
            if columns:
                values = annotated[columns].stack().str.strip()
                counts[field] = {str(key): int(value) for key, value in values[values.ne("")].value_counts().items()}
    return {
        "status": "AVAILABLE" if matching and source_path is not None else "UNAVAILABLE",
        "source_columns": matching,
        **{f"{field}_family_counts": counts[field] for field in GERMLINE_FIELDS},
        "note": "Counts are raw source annotation values at the source-row unit; no germline is inferred from identity clusters." if matching else "The source summary has no IGHV/IGKV/IGLV annotation columns.",
    }


def _number(value: Any, places: int = 4) -> str:
    return "NA" if value is None else f"{float(value):.{places}f}"


def _count_map(values: dict[str, int]) -> str:
    return ", ".join(f"{key}: {value}" for key, value in sorted(values.items())) or "none"


def render_report(
    *,
    source: dict[str, Any],
    phase7a: dict[str, Any],
    rule: dict[str, Any],
    embedding: dict[str, Any],
    embedding_manifest: dict[str, Any],
    germline: dict[str, Any],
) -> str:
    """Render a deterministic report from audited, outcome-blind summaries."""

    external = rule["external"]
    internal = rule["internal_train_validation"]
    if external["n"] != phase7a["population"]["valid_paired_unique_sequences"]:
        raise ValueError("RULE48 external population differs from Phase 7A")
    if internal["n"] != 381 or embedding["internal_train_validation_n"] != 381:
        raise ValueError("Internal TRAIN/VALIDATION population differs from frozen split")
    if embedding["external_n"] != external["n"] or embedding_manifest["row_count"] != external["n"]:
        raise ValueError("External embedding population differs from RULE48 population")
    if rule["feature_count"] != 48:
        raise ValueError("RULE48 count changed")

    lines = [
        "# Phase 7B-A — SAbDab2 external diversity audit",
        "",
        "## Provenance and population",
        "",
        f"- Dataset: {source['dataset']}",
        f"- Official source: {source['source_url']}",
        f"- Publication: {source['publication']}",
        f"- Acquisition date: {source['acquisition_date']}",
        f"- Raw SHA256: `{source['sha256']}`",
        f"- Access/redistribution: {source['license_or_accessibility']}",
        f"- Source structure records: {phase7a['population']['source_records']}",
        f"- Valid paired records: {phase7a['population']['valid_paired_records']}",
        f"- Unique valid paired VH/VL hashes: {external['n']}",
        f"- Internal reference: frozen AIntibody TRAIN 285 + VALIDATION 96 = {internal['n']} unique hashes; TEST excluded.",
        "- Descriptive unit: one valid paired VH/VL sequence hash. Repeated structures are retained in the Phase 7A source audit and counted once here.",
        "",
        "## Sequence diversity from Phase 7A",
        "",
        "| Paired identity threshold | Deterministic representative clusters | Largest cluster | Singletons |",
        "| --- | ---: | ---: | ---: |",
    ]
    for threshold, values in sorted(phase7a["clusters"].items(), key=lambda item: float(item[0])):
        lines.append(f"| {threshold} | {values['clusters']} | {values['largest_cluster']} | {values['singleton_clusters']} |")
    identity = phase7a["identity_distribution"]
    lines.extend([
        "",
        f"Paired-min global identity sample: N={identity['sampled_pairs']}, median={_number(identity['paired_min']['median'])}, Q1={_number(identity['paired_min']['q25'])}, Q3={_number(identity['paired_min']['q75'])}.",
        "Clusters are deterministic sequence-similarity proxies, not biological family assignments.",
        "",
        "## Frozen RULE48 distribution",
        "",
        "Every count-feature prevalence is the fraction with a value above zero among observed unique paired sequences. Scores, penalties, and lengths are continuous and have no prevalence interpretation.",
        "",
        "| Count feature | SAbDab2 nonzero / N | SAbDab2 fraction | AIntibody TRAIN+VALIDATION nonzero / N | AIntibody fraction |",
        "| --- | ---: | ---: | ---: | ---: |",
    ])
    for feature in rule["feature_order"]:
        if feature not in external["feature_prevalence"]:
            continue
        left, right = external["feature_prevalence"][feature], internal["feature_prevalence"][feature]
        lines.append(
            f"| {feature} | {left['nonzero_n']} / {left['n']} | {_number(left['nonzero_fraction'])} "
            f"| {right['nonzero_n']} / {right['n']} | {_number(right['nonzero_fraction'])} |"
        )
    lines.extend([
        "",
        "| Continuous feature | SAbDab2 median [Q1, Q3] (N) | AIntibody TRAIN+VALIDATION median [Q1, Q3] (N) |",
        "| --- | ---: | ---: |",
    ])
    for feature in rule["feature_order"]:
        if feature not in external["continuous_feature_distribution"]:
            continue
        left, right = external["continuous_feature_distribution"][feature], internal["continuous_feature_distribution"][feature]
        lines.append(
            f"| {feature} | {_number(left['median'])} [{_number(left['q25'])}, {_number(left['q75'])}] ({left['n']}) "
            f"| {_number(right['median'])} [{_number(right['q25'])}, {_number(right['q75'])}] ({right['n']}) |"
        )
    lines.extend([
        "",
        "## Liability sites and CDR/framework locations",
        "",
        "| Quantity | SAbDab2 | AIntibody TRAIN+VALIDATION |",
        "| --- | ---: | ---: |",
        f"| Total detected risk-site rows | {external['total_risk_sites']} | {internal['total_risk_sites']} |",
        f"| Sites per paired sequence, median [Q1, Q3] | {_number(external['sites_per_pair']['median'])} [{_number(external['sites_per_pair']['q25'])}, {_number(external['sites_per_pair']['q75'])}] | {_number(internal['sites_per_pair']['median'])} [{_number(internal['sites_per_pair']['q25'])}, {_number(internal['sites_per_pair']['q75'])}] |",
        f"| CDR sites | {external['cdr_sites']} | {internal['cdr_sites']} |",
        f"| Framework sites | {external['framework_sites']} | {internal['framework_sites']} |",
        "",
        f"SAbDab2 categories: {_count_map(external['site_category_counts'])}.",
        f"AIntibody categories: {_count_map(internal['site_category_counts'])}.",
        f"SAbDab2 regions: {_count_map(external['region_counts'])}.",
        f"AIntibody regions: {_count_map(internal['region_counts'])}.",
        "",
        "## Frozen ESM2 representation geometry",
        "",
        f"- Model: `{embedding_manifest['model_name']}` at immutable revision `{embedding_manifest['resolved_model_revision']}`.",
        f"- Representation: {embedding_manifest['representation']}.",
        f"- SAbDab2 embedding rows: {embedding['external_n']}; internal reference rows: {embedding['internal_train_validation_n']}.",
        f"- Exact paired sequence-hash overlap: {embedding['exact_sequence_hash_overlap_n']}.",
        f"- External embedding SHA256: `{embedding_manifest['embedding_file_sha256']}`.",
        f"- Real extraction repeatability: N={embedding_manifest['repeatability']['sample_n']}, maximum absolute difference={embedding_manifest['repeatability']['max_absolute_difference']}.",
        "",
        "| Paired cosine statistic | N | Median | Q1 | Q3 |",
        "| --- | ---: | ---: | ---: | ---: |",
    ])
    for name, label in (
        ("external_within_cosine", "SAbDab2 within-space sampled pairs"),
        ("internal_train_validation_within_cosine", "AIntibody TRAIN+VALIDATION within-space sampled pairs"),
        ("external_vs_internal_cosine", "Cross-space sampled pairs"),
        ("external_nearest_internal_cosine", "Each external row's nearest internal neighbor"),
        ("external_nearest_internal_cosine_excluding_exact_hash_overlap", "Nearest internal, external exact-hash overlaps excluded"),
    ):
        values = embedding[name]
        lines.append(f"| {label} | {values['n']} | {_number(values['median'])} | {_number(values['q25'])} | {_number(values['q75'])} |")
    lines.extend([
        "",
        "No classifier, endpoint comparison, prediction metric, or PCA was calculated.",
        "",
        "## Immunoglobulin germline family annotations",
        "",
        f"- Status: {germline['status']}.",
        f"- Source annotation columns: {', '.join(germline['source_columns']) or 'none'}.",
        f"- IGHV family counts: {germline['IGHV_family_counts'] if germline['IGHV_family_counts'] is not None else 'unavailable'}.",
        f"- IGKV family counts: {germline['IGKV_family_counts'] if germline['IGKV_family_counts'] is not None else 'unavailable'}.",
        f"- IGLV family counts: {germline['IGLV_family_counts'] if germline['IGLV_family_counts'] is not None else 'unavailable'}.",
        "- Identity clusters are not mapped to germline families.",
        "",
        "## Limitations and next gate",
        "",
        "- SAbDab2 is a structure-centered collection. Structure instances are not independent biological experiments; external analyses here count unique paired sequences.",
        "- No requested HIC, Tm, Tagg, AC-SINS, BVP, or aggregation outcome labels are present in the audited summary.",
        "- The rule and embedding comparisons are descriptive distributions only. They support no biological or predictive-performance conclusion.",
        "- Identity clustering used a deterministic representative method with candidate prefilters; it is not an exhaustive germline or lineage assignment.",
        "- Family-diverse external ML validation requires a separately reviewed labeled dataset and a predeclared held-out protocol. Phase 7B-A does not provide that validation.",
        "",
        "ML training: NO. Model tuning: NO. Experimental endpoint evaluation: NO. Prediction performance: NOT CALCULATED.",
        "",
    ])
    return "\n".join(lines)


def write_report(path: str | Path, content: str) -> None:
    destination = Path(path)
    destination.parent.mkdir(parents=True, exist_ok=True)
    destination.write_text(content, encoding="utf-8")
