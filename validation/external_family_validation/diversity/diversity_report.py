"""Build the auditable Phase 7A diversity and label report."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

import pandas as pd

from .family_clustering import cluster_summary
from .sequence_identity import compute_identity_sample


LABEL_FIELDS = ("HIC", "Tm", "Tagg", "AC-SINS", "BVP", "aggregation")


def build_diversity_report(
    normalized: pd.DataFrame,
    cluster_outputs: dict[float, tuple[pd.DataFrame, pd.DataFrame]],
    *,
    source_manifest: dict[str, Any],
    max_identity_pairs: int = 10_000,
) -> dict[str, Any]:
    paired = normalized.loc[
        (normalized["sequence_status"] == "VALID")
        & normalized["VH"].astype(str).ne("")
        & normalized["VL"].astype(str).ne("")
    ].copy()
    unique_paired = paired.sort_values("sequence_hash", kind="mergesort").drop_duplicates("sequence_hash")
    pair_counts = paired["sequence_hash"].value_counts()
    duplicate_groups = pair_counts[pair_counts > 1]
    label_columns = [column for column in LABEL_FIELDS if column in normalized.columns]
    labels_available = bool(label_columns and normalized[label_columns].notna().any().any())
    return {
        "report_version": 1,
        "dataset": "SAbDab2",
        "source_manifest": source_manifest,
        "population": {
            "source_records": int(len(normalized)),
            "unique_antibody_ids": int(normalized["antibody_id"].replace("", pd.NA).nunique(dropna=True)),
            "valid_paired_records": int(len(paired)),
            "valid_paired_unique_sequences": int(len(unique_paired)),
            "unique_VH": int(normalized.loc[normalized["VH"].ne(""), "VH"].nunique()),
            "unique_VL": int(normalized.loc[normalized["VL"].ne(""), "VL"].nunique()),
            "sequence_status_counts": {str(key): int(value) for key, value in normalized["sequence_status"].value_counts().to_dict().items()},
            "paired_sequence_duplicate_groups": int(len(duplicate_groups)),
            "paired_duplicate_rows": int(duplicate_groups.sum()),
            "exact_duplicate_pair_count": int(sum(size * (size - 1) // 2 for size in duplicate_groups)),
        },
        "identity_distribution": compute_identity_sample(
            unique_paired,
            max_pairs=max_identity_pairs,
        ),
        "clusters": {
            str(threshold): {
                **cluster_summary(cluster_frame),
                "unit": "unique valid paired VH/VL sequence_hash",
                "similarity_definition": "VH global identity >= threshold AND VL global identity >= threshold",
                "cluster_method": "deterministic greedy representative assignment",
            }
            for threshold, (_, cluster_frame) in sorted(cluster_outputs.items())
        },
        "experimental_labels": {
            "available": labels_available,
            "fields": label_columns,
            "status": "AVAILABLE" if labels_available else "MISSING",
            "note": "SAbDab2 summary contains structural experimental metadata, not the requested developability assay labels; no label was synthesized or imputed.",
        },
        "split_readiness": {
            "family_cluster_ready": True,
            "label_based_external_validation_ready": labels_available,
            "decision": "HUMAN_REVIEW_REQUIRED",
            "note": "Identity clusters are a sequence-similarity family proxy, not immunogenetic family annotations. No model training or tuning was performed.",
        },
        "limitations": [
            "SAbDab2 is structure-centric and has no complete developability-label panel in the downloaded summary.",
            "Rows represent structure instances; repeated structures are preserved and are not independent biological experiments.",
            "Greedy identity clusters are reproducible family proxies, not V-gene or clonotype calls.",
            "The identity distribution is a deterministic sample when the full pair count exceeds the configured audit bound.",
        ],
    }


def write_diversity_report(report: dict[str, Any], path: str | Path) -> None:
    destination = Path(path)
    destination.parent.mkdir(parents=True, exist_ok=True)
    destination.write_text(json.dumps(report, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
