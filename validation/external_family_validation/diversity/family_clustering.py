"""Deterministic identity clusters used as family-diversity proxies.

Clusters are not immunogenetic V-gene families.  They are reproducible
sequence-similarity groups and must be described as such.
"""

from __future__ import annotations

from collections import Counter
from typing import Any

import pandas as pd

from validation.ml_benchmark.similarity import global_identity


def _length_possible(left: str, right: str, threshold: float) -> bool:
    if not left or not right:
        return False
    return min(len(left), len(right)) / max(len(left), len(right)) + 1e-12 >= threshold


def _kmer_set(sequence: str, k: int = 3) -> set[str]:
    return {sequence[index : index + k] for index in range(max(0, len(sequence) - k + 1))}


def _candidate_pair(left: dict[str, Any], right: dict[str, Any], threshold: float) -> bool:
    """Cheap deterministic prefilter; final decisions always use global identity."""

    for chain in ("VH", "VL"):
        left_sequence, right_sequence = str(left.get(chain, "")), str(right.get(chain, ""))
        if not _length_possible(left_sequence, right_sequence, threshold):
            return False
        left_kmers, right_kmers = _kmer_set(left_sequence), _kmer_set(right_sequence)
        if left_kmers and right_kmers:
            overlap = len(left_kmers & right_kmers) / max(1, min(len(left_kmers), len(right_kmers)))
            # The floor is intentionally permissive. It is only a speed filter;
            # global identity remains the acceptance criterion.
            if overlap < max(0.05, threshold - 0.65):
                return False
    return True


def _indexed_candidates(kmers: set[str], index: dict[str, set[str]]) -> set[str]:
    """Return representatives sharing several indexed k-mers.

    Requiring multiple shared 5-mers keeps the audit tractable on framework-
    rich tables.  It is a documented approximate prefilter; global alignment
    remains the only identity acceptance rule after this step.
    """

    if not kmers:
        return set()
    counts: Counter[str] = Counter()
    for kmer in kmers:
        counts.update(index.get(kmer, set()))
    if len(kmers) < 20:
        minimum_shared = 1
    else:
        minimum_shared = max(2, min(12, len(kmers) // 10))
    return {cluster_id for cluster_id, count in counts.items() if count >= minimum_shared}


def cluster_unique_paired_sequences(records: pd.DataFrame, threshold: float) -> tuple[pd.DataFrame, pd.DataFrame]:
    """Assign unique valid paired sequences to deterministic greedy clusters."""

    if not 0.0 < threshold <= 1.0:
        raise ValueError("threshold must be in (0, 1]")
    required = {"sequence_hash", "VH", "VL", "sequence_status"}
    missing = required - set(records.columns)
    if missing:
        raise ValueError(f"clustering input missing columns: {sorted(missing)}")
    valid = records.loc[
        (records["sequence_status"] == "VALID")
        & records["VH"].astype(str).ne("")
        & records["VL"].astype(str).ne(""),
        ["sequence_hash", "VH", "VL"],
    ].sort_values("sequence_hash", kind="mergesort").drop_duplicates("sequence_hash")
    rows = valid.to_dict("records")
    clusters: list[dict[str, Any]] = []
    # Keep deterministic inverted indexes so the expensive global aligner is
    # called only for representatives sharing sequence evidence on both
    # chains.  `_candidate_pair` remains the final cheap prefilter and global
    # identity remains the only acceptance criterion.
    vh_index: dict[str, set[str]] = {}
    vl_index: dict[str, set[str]] = {}
    assignments: list[dict[str, Any]] = []
    for row in rows:
        # A longer index k-mer keeps the candidate set tractable for large
        # framework-rich structure tables.  The subsequent `_candidate_pair`
        # check still uses its permissive 3-mer overlap rule, followed by
        # global alignment identity for acceptance.
        row_vh_kmers = _kmer_set(row["VH"], k=5)
        row_vl_kmers = _kmer_set(row["VL"], k=5)
        vh_candidates = _indexed_candidates(row_vh_kmers, vh_index)
        vl_candidates = _indexed_candidates(row_vl_kmers, vl_index)
        candidate_ids = vh_candidates & vl_candidates
        assigned = None
        for cluster in clusters:
            if cluster["cluster_id"] not in candidate_ids:
                continue
            representative = cluster["representative"]
            if not _candidate_pair(row, representative, threshold):
                continue
            vh_identity = global_identity(row["VH"], representative["VH"])
            vl_identity = global_identity(row["VL"], representative["VL"])
            if vh_identity >= threshold and vl_identity >= threshold:
                assigned = cluster
                break
        if assigned is None:
            cluster_id = f"identity_{threshold:.2f}_{len(clusters) + 1:05d}"
            assigned = {"cluster_id": cluster_id, "representative": row, "members": []}
            clusters.append(assigned)
            for kmer in _kmer_set(row["VH"], k=5):
                vh_index.setdefault(kmer, set()).add(cluster_id)
            for kmer in _kmer_set(row["VL"], k=5):
                vl_index.setdefault(kmer, set()).add(cluster_id)
        assigned["members"].append(row["sequence_hash"])
        assignments.append(
            {
                "sequence_hash": row["sequence_hash"],
                "cluster_id": assigned["cluster_id"],
                "cluster_size": 0,
                "representative_sequence": f"{assigned['representative']['VH']}|{assigned['representative']['VL']}",
                "threshold": threshold,
            }
        )
    sizes = {cluster["cluster_id"]: len(cluster["members"]) for cluster in clusters}
    assignment_frame = pd.DataFrame(assignments)
    if not assignment_frame.empty:
        assignment_frame["cluster_size"] = assignment_frame["cluster_id"].map(sizes).astype(int)
    cluster_frame = pd.DataFrame(
        [
            {
                "cluster_id": cluster["cluster_id"],
                "threshold": threshold,
                "cluster_size": len(cluster["members"]),
                "representative_sequence_hash": cluster["representative"]["sequence_hash"],
                "representative_sequence": f"{cluster['representative']['VH']}|{cluster['representative']['VL']}",
            }
            for cluster in clusters
        ]
    )
    return assignment_frame, cluster_frame


def cluster_summary(cluster_frame: pd.DataFrame) -> dict[str, Any]:
    if cluster_frame.empty:
        return {"clusters": 0, "largest_cluster": 0, "cluster_size_distribution": {}}
    sizes = Counter(int(value) for value in cluster_frame["cluster_size"])
    return {
        "clusters": int(len(cluster_frame)),
        "largest_cluster": int(cluster_frame["cluster_size"].max()),
        "singleton_clusters": int((cluster_frame["cluster_size"] == 1).sum()),
        "cluster_size_distribution": {str(size): count for size, count in sorted(sizes.items())},
    }
