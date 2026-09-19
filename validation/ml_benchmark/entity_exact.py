"""Outcome-blind ENTITY_EXACT_V1 grouping, splitting, and residual audits.

This module is limited to benchmark-design infrastructure.  It does not
import production scientific code, read experimental outcomes while forming
components, fit estimators, generate embeddings, or calculate performance.
"""

from __future__ import annotations

import hashlib
from collections import defaultdict
from dataclasses import dataclass
from typing import Iterable

import numpy as np
import pandas as pd

from validation.ml_benchmark.similarity import global_identity
from validation.ml_benchmark.split import load_primary_identity
from validation.ml_benchmark_spec import (
    IDENTITY_COLUMNS,
    SPLIT_PRIORITY,
    SPLIT_TARGET_FRACTIONS,
)


ENTITY_EXACT_V1 = "ENTITY_EXACT_V1"
MAX_COMPONENT_FRACTION = 0.60
NOVELTY_BINS = ("BIN_1", "BIN_2", "BIN_3", "BIN_4", "BIN_5")


@dataclass(frozen=True)
class EntityExactPlan:
    identity: pd.DataFrame
    assignments: pd.DataFrame
    clusters: pd.DataFrame


def _clean_sequence(value: object) -> str:
    if value is None or pd.isna(value):
        return ""
    return str(value).strip().upper()


def _clean_identifier(value: object) -> str:
    if value is None or pd.isna(value):
        return ""
    return str(value).strip()


def _find(parent: dict[str, str], item: str) -> str:
    while parent[item] != item:
        parent[item] = parent[parent[item]]
        item = parent[item]
    return item


def _union(parent: dict[str, str], left: str, right: str) -> None:
    left_root, right_root = _find(parent, left), _find(parent, right)
    if left_root != right_root:
        parent[max(left_root, right_root)] = min(left_root, right_root)


def component_id_from_members(members: Iterable[str]) -> str:
    """Return a stable component ID from sorted member sequence hashes."""

    ordered = sorted(str(value) for value in members)
    if not ordered:
        raise ValueError("A component must contain at least one sequence hash")
    return hashlib.sha256("\n".join(ordered).encode("utf-8")).hexdigest()


def _validate_identity(records: pd.DataFrame) -> pd.DataFrame:
    required = {"sequence_hash", "VH", "VL", "antibody_id"}
    missing = required - set(records.columns)
    if missing:
        raise ValueError(f"Missing ENTITY_EXACT_V1 columns: {sorted(missing)}")
    if records["sequence_hash"].duplicated().any():
        raise ValueError("ENTITY_EXACT_V1 requires one row per sequence_hash")
    ordered = records.copy()
    ordered["sequence_hash"] = ordered["sequence_hash"].map(_clean_identifier)
    if (ordered["sequence_hash"] == "").any():
        raise ValueError("sequence_hash cannot be empty")
    return ordered.sort_values("sequence_hash", kind="mergesort").reset_index(drop=True)


def build_entity_exact_components(records: pd.DataFrame) -> tuple[pd.DataFrame, pd.DataFrame]:
    """Build exact antibody-entity components from identity fields only.

    Rows are connected when they share a non-empty antibody ID or have exact
    normalized VH and VL sequences.  No similarity threshold is used.
    """

    ordered = _validate_identity(records)
    hashes = ordered["sequence_hash"].tolist()
    parent = {value: value for value in hashes}
    reasons: dict[tuple[str, str], set[str]] = defaultdict(set)

    def connect_group(values: Iterable[str], reason: str) -> None:
        members = sorted(set(values))
        for left, right in zip(members, members[1:]):
            _union(parent, left, right)
            reasons[(min(left, right), max(left, right))].add(reason)

    by_id: dict[str, list[str]] = defaultdict(list)
    for row in ordered.itertuples(index=False):
        antibody_id = _clean_identifier(getattr(row, "antibody_id"))
        if antibody_id:
            by_id[antibody_id].append(str(getattr(row, "sequence_hash")))
    for members in by_id.values():
        if len(set(members)) > 1:
            connect_group(members, "antibody_id")

    by_pair: dict[tuple[str, str], list[str]] = defaultdict(list)
    for row in ordered.itertuples(index=False):
        vh = _clean_sequence(getattr(row, "VH"))
        vl = _clean_sequence(getattr(row, "VL"))
        if vh and vl:
            by_pair[(vh, vl)].append(str(getattr(row, "sequence_hash")))
    for members in by_pair.values():
        if len(set(members)) > 1:
            connect_group(members, "exact_paired_sequence")

    members_by_root: dict[str, list[str]] = defaultdict(list)
    for sequence_hash in hashes:
        members_by_root[_find(parent, sequence_hash)].append(sequence_hash)
    components = sorted(
        (sorted(values) for values in members_by_root.values()),
        key=lambda values: (-len(values), component_id_from_members(values)),
    )
    component_by_hash = {
        sequence_hash: component_id_from_members(values)
        for values in components
        for sequence_hash in values
    }

    assignments = pd.DataFrame(
        {
            "sequence_hash": hashes,
            "component_id": [component_by_hash[value] for value in hashes],
        }
    )
    ordered_by_hash = ordered.set_index("sequence_hash", drop=False)
    cluster_rows: list[dict[str, object]] = []
    for values in components:
        component_id = component_id_from_members(values)
        component_reasons: set[str] = set()
        for (left, right), edge_reasons in reasons.items():
            if left in values and right in values:
                component_reasons.update(edge_reasons)
        member_rows = ordered_by_hash.loc[values]
        ids = sorted(
            {
                _clean_identifier(value)
                for value in member_rows["antibody_id"]
                if _clean_identifier(value)
            }
        )
        cluster_rows.append(
            {
                "component_id": component_id,
                "member_count": len(values),
                "sequence_hashes": ";".join(values),
                "antibody_ids": ";".join(ids),
                "link_reason_summary": ";".join(sorted(component_reasons)) or "singleton",
                "linked_by_antibody_id": "antibody_id" in component_reasons,
                "linked_by_exact_paired_sequence": "exact_paired_sequence" in component_reasons,
            }
        )
    clusters = pd.DataFrame(cluster_rows)
    return assignments, clusters


def component_summary(clusters: pd.DataFrame) -> dict[str, object]:
    sizes = clusters["member_count"].astype(int)
    if sizes.empty:
        raise ValueError("At least one component is required")
    return {
        "components": int(len(sizes)),
        "singleton_components": int((sizes == 1).sum()),
        "multi_row_components": int((sizes > 1).sum()),
        "largest_component": int(sizes.max()),
        "median_component_size": float(sizes.median()),
        "p95_component_size": float(np.percentile(sizes, 95)),
        "components_linked_by_antibody_id": int(clusters["linked_by_antibody_id"].sum()),
        "components_linked_by_exact_paired_sequence": int(clusters["linked_by_exact_paired_sequence"].sum()),
        "component_size_frequency": {
            str(size): int(count) for size, count in sizes.value_counts().sort_index().items()
        },
    }


def assign_entity_splits(identity: pd.DataFrame, assignments: pd.DataFrame, clusters: pd.DataFrame) -> pd.DataFrame:
    """Assign whole exact-entity components using the frozen greedy algorithm."""

    if len(identity) == 0:
        raise ValueError("Cannot split an empty population")
    sizes = clusters.set_index("component_id")["member_count"].astype(int).to_dict()
    ordered_components = sorted(sizes, key=lambda value: (-sizes[value], value))
    targets = {name: len(identity) * fraction for name, fraction in SPLIT_TARGET_FRACTIONS.items()}
    counts = {name: 0 for name in SPLIT_PRIORITY}
    split_by_component: dict[str, str] = {}
    for component_id in ordered_components:
        deficits = {name: targets[name] - counts[name] for name in SPLIT_PRIORITY}
        chosen = max(
            SPLIT_PRIORITY,
            key=lambda name: (deficits[name], -SPLIT_PRIORITY.index(name)),
        )
        split_by_component[component_id] = chosen
        counts[chosen] += sizes[component_id]

    result = identity[["sequence_hash", "representative_record_id", "antibody_id"]].copy()
    result = result.merge(assignments, on="sequence_hash", how="left", validate="one_to_one")
    result["split"] = result["component_id"].map(split_by_component)
    if result["split"].isna().any():
        raise ValueError("Every exact entity component must receive a split")
    return result.sort_values("sequence_hash", kind="mergesort").reset_index(drop=True)


def build_entity_exact_plan(primary_path: str, processed_path: str) -> EntityExactPlan:
    """Load the frozen identity population and construct its exact split plan."""

    identity = load_primary_identity(primary_path, processed_path)
    assignments, clusters = build_entity_exact_components(identity)
    split_assignments = assign_entity_splits(identity, assignments, clusters)
    enriched = identity.merge(
        split_assignments[["sequence_hash", "component_id", "split"]],
        on="sequence_hash",
        how="left",
        validate="one_to_one",
    )
    return EntityExactPlan(
        identity=enriched.sort_values("sequence_hash", kind="mergesort").reset_index(drop=True),
        assignments=split_assignments,
        clusters=clusters,
    )


def _novelty_bin(value: float) -> str:
    if value >= 1.0 - 1e-12:
        return "BIN_5"
    if value >= 0.95:
        return "BIN_4"
    if value >= 0.90:
        return "BIN_3"
    if value >= 0.80:
        return "BIN_2"
    return "BIN_1"


def residual_similarity_audit(identity: pd.DataFrame, heldout_split: str) -> pd.DataFrame:
    """Compare each VALIDATION/TEST row against every TRAIN row."""

    if heldout_split not in {"VALIDATION", "TEST"}:
        raise ValueError("heldout_split must be VALIDATION or TEST")
    required = {"sequence_hash", "VH", "VL", "split"}
    missing = required - set(identity.columns)
    if missing:
        raise ValueError(f"Missing residual-audit columns: {sorted(missing)}")
    train = identity[identity["split"] == "TRAIN"].sort_values("sequence_hash", kind="mergesort")
    heldout = identity[identity["split"] == heldout_split].sort_values("sequence_hash", kind="mergesort")
    if train.empty:
        raise ValueError("Residual similarity audit requires non-empty TRAIN")

    train_rows = [
        (_clean_identifier(row.sequence_hash), _clean_sequence(row.VH), _clean_sequence(row.VL))
        for row in train.itertuples(index=False)
    ]
    output: list[dict[str, object]] = []
    for row in heldout.itertuples(index=False):
        vh = _clean_sequence(row.VH)
        vl = _clean_sequence(row.VL)
        vh_values = [global_identity(vh, train_vh) for _, train_vh, _ in train_rows]
        vl_values = [global_identity(vl, train_vl) for _, _, train_vl in train_rows]
        paired_min = [min(left, right) for left, right in zip(vh_values, vl_values)]
        paired_mean = [(left + right) / 2 for left, right in zip(vh_values, vl_values)]
        max_paired_min = max(paired_min)
        output.append(
            {
                "sequence_hash": _clean_identifier(row.sequence_hash),
                "representative_record_id": _clean_identifier(getattr(row, "representative_record_id", "")),
                "antibody_id": _clean_identifier(getattr(row, "antibody_id", "")),
                "max_VH_identity_to_train": max(vh_values),
                "max_VL_identity_to_train": max(vl_values),
                "max_paired_min_identity_to_train": max_paired_min,
                "max_paired_mean_identity_to_train": max(paired_mean),
                "novelty_bin": _novelty_bin(max_paired_min),
            }
        )
    return pd.DataFrame(output).sort_values("sequence_hash", kind="mergesort").reset_index(drop=True)


def similarity_summary(audit: pd.DataFrame) -> dict[str, object]:
    """Summarize residual similarity without calculating model performance."""

    if audit.empty:
        return {"rows": 0, "threshold_counts": {}, "distribution": {}, "novelty_bins": {}}
    n = len(audit)
    threshold_counts: dict[str, dict[str, float | int]] = {}
    for field, label in (
        ("max_paired_min_identity_to_train", "paired_min"),
        ("max_VH_identity_to_train", "VH"),
        ("max_VL_identity_to_train", "VL"),
    ):
        values = audit[field].astype(float)
        for threshold in (0.90, 0.95, 0.98):
            count = int((values >= threshold).sum())
            threshold_counts[f"{label}_ge_{threshold:.2f}"] = {
                "count": count,
                "percentage": count / n * 100,
            }
    distribution = {}
    for field, label in (
        ("max_paired_min_identity_to_train", "max_paired_min"),
        ("max_VH_identity_to_train", "max_VH"),
        ("max_VL_identity_to_train", "max_VL"),
    ):
        values = audit[field].astype(float).to_numpy()
        distribution[label] = {
            "median": float(np.median(values)),
            "p25": float(np.percentile(values, 25)),
            "p75": float(np.percentile(values, 75)),
            "max": float(np.max(values)),
        }
    bins = audit["novelty_bin"].value_counts().to_dict()
    return {
        "rows": int(n),
        "threshold_counts": threshold_counts,
        "distribution": distribution,
        "novelty_bins": {name: int(bins.get(name, 0)) for name in NOVELTY_BINS},
    }


def cross_split_leakage_audit(identity: pd.DataFrame) -> dict[str, object]:
    """Audit exact hash, exact paired sequence, ID, and component overlap."""

    by_split = {
        split: identity[identity["split"] == split]
        for split in SPLIT_PRIORITY
    }
    hash_sets = {split: set(frame["sequence_hash"].astype(str)) for split, frame in by_split.items()}
    pair_sets = {
        split: {
            (_clean_sequence(row.VH), _clean_sequence(row.VL))
            for row in frame.itertuples(index=False)
            if _clean_sequence(row.VH) and _clean_sequence(row.VL)
        }
        for split, frame in by_split.items()
    }
    id_sets = {
        split: {
            _clean_identifier(value)
            for value in frame["antibody_id"]
            if _clean_identifier(value)
        }
        for split, frame in by_split.items()
    }
    component_sets = {split: set(frame["component_id"].astype(str)) for split, frame in by_split.items()}

    def overlap_count(values: dict[str, set[object]]) -> int:
        return sum(
            len(values[left] & values[right])
            for left, right in (("TRAIN", "VALIDATION"), ("TRAIN", "TEST"), ("VALIDATION", "TEST"))
        )

    return {
        "exact_sequence_hash_overlap": overlap_count(hash_sets),
        "exact_paired_VH_VL_overlap": overlap_count(pair_sets),
        "antibody_id_overlap": overlap_count(id_sets),
        "component_overlap": overlap_count(component_sets),
    }


def population_is_structurally_usable(clusters: pd.DataFrame, population_rows: int) -> bool:
    """Return whether a largest component permits the preregistered split."""

    if population_rows <= 0:
        return False
    largest = int(clusters["member_count"].max())
    return largest <= population_rows * MAX_COMPONENT_FRACTION


def identity_feature_columns(identity: pd.DataFrame) -> list[str]:
    """Return the stable non-outcome fields allowed in feature artifacts."""

    fields = [column for column in IDENTITY_COLUMNS if column in identity.columns]
    for column in ("source_record_ids", "component_id", "split"):
        if column in identity.columns and column not in fields:
            fields.append(column)
    return fields
