"""Outcome-blind deterministic population construction and component splitting."""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

import pandas as pd

from validation.ml_benchmark.similarity import build_leakage_components, cross_split_identity_counts
from validation.ml_benchmark_spec import (
    DATASET,
    LEAKAGE_IDENTITY_THRESHOLD,
    SPLIT_PRIORITY,
    SPLIT_TARGET_FRACTIONS,
)


NON_OUTCOME_PRIMARY_COLUMNS = (
    "dataset",
    "sequence_hash",
    "representative_record_id",
    "source_record_count",
    "source_record_ids",
    "duplicate_resolution",
    "VH",
    "VL",
    "record_type",
    "challenge",
)
PROCESSED_IDENTITY_COLUMNS = ("record_id", "antibody_id", "sequence_hash", "VH", "VL", "record_type", "challenge")


@dataclass(frozen=True)
class SplitPlan:
    identity: pd.DataFrame
    assignments: pd.DataFrame
    clusters: pd.DataFrame
    pairwise_identities: dict[tuple[str, str], dict[str, float]]


def load_primary_identity(
    primary_path: Path | str,
    processed_path: Path | str,
) -> pd.DataFrame:
    """Load only identity/non-outcome fields needed to form leakage groups."""

    primary = pd.read_csv(primary_path, dtype=str, usecols=list(NON_OUTCOME_PRIMARY_COLUMNS))
    processed = pd.read_csv(processed_path, dtype=str, usecols=list(PROCESSED_IDENTITY_COLUMNS))
    if processed["record_id"].duplicated().any():
        raise ValueError("Processed record_id is not unique; representative mapping is ambiguous")
    merged = primary.merge(
        processed,
        left_on="representative_record_id",
        right_on="record_id",
        how="left",
        suffixes=("", "_processed"),
        validate="one_to_one",
    )
    if merged["record_id"].isna().any():
        raise ValueError("Primary population contains records missing from processed identity data")
    for column in ("sequence_hash", "VH", "VL"):
        if (merged[column] != merged[f"{column}_processed"]).any():
            raise ValueError(f"Primary and processed identity mismatch in {column}")
    merged["antibody_id"] = merged["antibody_id"].fillna("").astype(str).str.strip()
    merged["record_type"] = merged["record_type"].fillna(merged["record_type_processed"])
    merged["challenge"] = merged["challenge"].fillna(merged["challenge_processed"])
    keep = list(NON_OUTCOME_PRIMARY_COLUMNS) + ["antibody_id"]
    result = merged[keep].copy()
    result["dataset"] = result["dataset"].fillna(DATASET)
    result = result.sort_values("sequence_hash", kind="mergesort").reset_index(drop=True)
    if result["sequence_hash"].duplicated().any():
        raise ValueError("Frozen primary population must contain unique sequence hashes")
    return result


def assign_component_splits(
    identity: pd.DataFrame,
    component_assignments: pd.DataFrame,
) -> pd.DataFrame:
    """Greedily assign whole components to target partitions without outcomes."""

    sizes = component_assignments.groupby("cluster_id", sort=False).size().to_dict()
    ordered_components = sorted(sizes, key=lambda value: (-sizes[value], value))
    targets = {name: len(identity) * fraction for name, fraction in SPLIT_TARGET_FRACTIONS.items()}
    counts = {name: 0 for name in SPLIT_PRIORITY}
    split_by_cluster: dict[str, str] = {}
    for cluster_id in ordered_components:
        deficits = {name: targets[name] - counts[name] for name in SPLIT_PRIORITY}
        selected = max(SPLIT_PRIORITY, key=lambda name: (deficits[name], -SPLIT_PRIORITY.index(name)))
        split_by_cluster[cluster_id] = selected
        counts[selected] += sizes[cluster_id]
    result = component_assignments.copy()
    result["split"] = result["cluster_id"].map(split_by_cluster)
    return result.sort_values("sequence_hash", kind="mergesort").reset_index(drop=True)


def build_split_plan(primary_path: Path | str, processed_path: Path | str) -> SplitPlan:
    identity = load_primary_identity(primary_path, processed_path)
    components, clusters, pairwise = build_leakage_components(identity, LEAKAGE_IDENTITY_THRESHOLD)
    assignments = assign_component_splits(identity, components)
    enriched = identity.merge(assignments, on="sequence_hash", validate="one_to_one")
    return SplitPlan(
        identity=enriched.sort_values("sequence_hash", kind="mergesort").reset_index(drop=True),
        assignments=assignments,
        clusters=clusters,
        pairwise_identities=pairwise,
    )


def audit_cross_split_leakage(plan: SplitPlan) -> dict[str, int]:
    return cross_split_identity_counts(plan.assignments, plan.pairwise_identities)
