"""Deterministic global sequence identity and leakage-component utilities."""

from __future__ import annotations

from collections import defaultdict
from typing import Iterable

import pandas as pd
from Bio.Align import PairwiseAligner

from validation.ml_benchmark_spec import ALIGNMENT_SCORING, LEAKAGE_IDENTITY_THRESHOLD


def _aligner() -> PairwiseAligner:
    aligner = PairwiseAligner()
    aligner.mode = ALIGNMENT_SCORING["mode"]
    aligner.match_score = ALIGNMENT_SCORING["match_score"]
    aligner.mismatch_score = ALIGNMENT_SCORING["mismatch_score"]
    aligner.open_gap_score = ALIGNMENT_SCORING["open_gap_score"]
    aligner.extend_gap_score = ALIGNMENT_SCORING["extend_gap_score"]
    return aligner


def global_identity(left: str, right: str) -> float:
    """Calculate symmetric identity from a global alignment.

    Identity is exact aligned-residue matches divided by alignment columns,
    including columns containing a gap.  Empty sequences are invalid except
    for the identical empty/empty case, which returns 1.0 deterministically.
    """

    left = "" if left is None else str(left).strip().upper()
    right = "" if right is None else str(right).strip().upper()
    if not left or not right:
        return 1.0 if left == right else 0.0

    alignment = _aligner().align(left, right)[0]
    coordinates = alignment.coordinates
    matches = 0
    columns = 0
    for index in range(coordinates.shape[1] - 1):
        left_start, left_end = coordinates[0, index : index + 2]
        right_start, right_end = coordinates[1, index : index + 2]
        left_length = int(left_end - left_start)
        right_length = int(right_end - right_start)
        columns += max(left_length, right_length)
        if left_length == right_length and left_length:
            matches += sum(
                a == b
                for a, b in zip(
                    left[int(left_start) : int(left_end)],
                    right[int(right_start) : int(right_end)],
                )
            )
    return matches / columns if columns else 0.0


def _union_find(items: Iterable[str]):
    parent = {item: item for item in items}

    def find(item: str) -> str:
        while parent[item] != item:
            parent[item] = parent[parent[item]]
            item = parent[item]
        return item

    def union(left: str, right: str) -> None:
        left_root, right_root = find(left), find(right)
        if left_root != right_root:
            parent[max(left_root, right_root)] = min(left_root, right_root)

    return parent, find, union


def pairwise_identity_records(records: pd.DataFrame) -> dict[tuple[str, str], dict[str, float]]:
    """Compute VH/VL identities for every unordered pair, deterministically."""

    required = {"sequence_hash", "VH", "VL"}
    missing = required - set(records.columns)
    if missing:
        raise ValueError(f"Missing identity columns: {sorted(missing)}")
    rows = records.sort_values("sequence_hash", kind="mergesort").drop_duplicates("sequence_hash")
    values = rows.set_index("sequence_hash")[["VH", "VL"]].to_dict("index")
    hashes = sorted(values)
    result: dict[tuple[str, str], dict[str, float]] = {}
    for index, left_hash in enumerate(hashes):
        for right_hash in hashes[index + 1 :]:
            result[(left_hash, right_hash)] = {
                "VH": global_identity(values[left_hash]["VH"], values[right_hash]["VH"]),
                "VL": global_identity(values[left_hash]["VL"], values[right_hash]["VL"]),
            }
    return result


def build_leakage_components(
    records: pd.DataFrame,
    threshold: float = LEAKAGE_IDENTITY_THRESHOLD,
) -> tuple[pd.DataFrame, pd.DataFrame, dict[tuple[str, str], dict[str, float]]]:
    """Build transitive leakage components from identity and antibody ID links."""

    required = {"sequence_hash", "VH", "VL", "antibody_id"}
    missing = required - set(records.columns)
    if missing:
        raise ValueError(f"Missing component columns: {sorted(missing)}")
    if records["sequence_hash"].duplicated().any():
        raise ValueError("Component input must contain one row per sequence_hash")

    ordered = records.sort_values("sequence_hash", kind="mergesort").copy()
    hashes = ordered["sequence_hash"].astype(str).tolist()
    parent, find, union = _union_find(hashes)
    reasons: dict[tuple[str, str], set[str]] = defaultdict(set)
    antibody_rows: dict[str, list[str]] = defaultdict(list)
    for row in ordered.itertuples(index=False):
        antibody_id = "" if pd.isna(row.antibody_id) else str(row.antibody_id).strip()
        if antibody_id:
            antibody_rows[antibody_id].append(str(row.sequence_hash))
    for members in antibody_rows.values():
        members = sorted(members)
        for left, right in zip(members, members[1:]):
            union(left, right)
            reasons[(min(left, right), max(left, right))].add("antibody_id")

    pairwise = pairwise_identity_records(ordered)
    for pair, identities in pairwise.items():
        if identities["VH"] >= threshold:
            union(*pair)
            reasons[pair].add(f"VH>={threshold:.2f}")
        if identities["VL"] >= threshold:
            union(*pair)
            reasons[pair].add(f"VL>={threshold:.2f}")

    members_by_root: dict[str, list[str]] = defaultdict(list)
    for sequence_hash in hashes:
        members_by_root[find(sequence_hash)].append(sequence_hash)
    components = sorted(
        (sorted(members) for members in members_by_root.values()),
        key=lambda members: (-len(members), members[0]),
    )
    component_by_hash = {
        sequence_hash: members[0]
        for members in components
        for sequence_hash in members
    }
    assignment = pd.DataFrame(
        {
            "sequence_hash": hashes,
            "cluster_id": [component_by_hash[value] for value in hashes],
        }
    )
    member_sets = {members[0]: set(members) for members in components}
    component_reasons: dict[str, set[str]] = defaultdict(set)
    for (left, right), edge_reasons in reasons.items():
        component_id = component_by_hash[left]
        if component_by_hash[right] == component_id:
            component_reasons[component_id].update(edge_reasons)
    cluster_rows = []
    for component_id, members in sorted(member_sets.items(), key=lambda item: (-len(item[1]), item[0])):
        member_rows = ordered[ordered["sequence_hash"].isin(members)]
        ids = sorted({str(value).strip() for value in member_rows["antibody_id"] if pd.notna(value) and str(value).strip()})
        cluster_rows.append(
            {
                "cluster_id": component_id,
                "member_count": len(members),
                "sequence_hashes": ";".join(sorted(members)),
                "antibody_ids": ";".join(ids),
                "link_reason_summary": ";".join(sorted(component_reasons.get(component_id, set()))) or "singleton",
            }
        )
    return assignment, pd.DataFrame(cluster_rows), pairwise


def cross_split_identity_counts(
    assignments: pd.DataFrame,
    pairwise: dict[tuple[str, str], dict[str, float]],
    audit_threshold: float = 0.80,
) -> dict[str, int]:
    """Count cross-partition exact/identity links for the post-split audit."""

    split_by_hash = assignments.set_index("sequence_hash")["split"].to_dict()
    hash_sets = {
        split: {value for value, assigned in split_by_hash.items() if assigned == split}
        for split in ("TRAIN", "VALIDATION", "TEST")
    }
    exact = sum(len(hash_sets[left] & hash_sets[right]) for left, right in (("TRAIN", "VALIDATION"), ("TRAIN", "TEST"), ("VALIDATION", "TEST")))
    vh_primary = vl_primary = vh_audit = vl_audit = 0
    for (left, right), identity in pairwise.items():
        if split_by_hash[left] == split_by_hash[right]:
            continue
        if identity["VH"] >= LEAKAGE_IDENTITY_THRESHOLD:
            vh_primary += 1
        if identity["VL"] >= LEAKAGE_IDENTITY_THRESHOLD:
            vl_primary += 1
        if identity["VH"] >= audit_threshold:
            vh_audit += 1
        if identity["VL"] >= audit_threshold:
            vl_audit += 1
    return {
        "exact_sequence_hash_overlap_pairs": exact,
        "VH_identity_ge_0.90_pairs": vh_primary,
        "VL_identity_ge_0.90_pairs": vl_primary,
        "VH_identity_ge_0.80_pairs": vh_audit,
        "VL_identity_ge_0.80_pairs": vl_audit,
    }
