"""Outcome-blind Phase 5A.1 graph diagnostics and PAIRED_90 policy."""

from __future__ import annotations

from collections import defaultdict
from dataclasses import dataclass
from typing import Iterable

import numpy as np
import pandas as pd

from validation.ml_benchmark.similarity import pairwise_identity_records


SINGLE_CHAIN_OR_90 = "SINGLE_CHAIN_OR_90"
PAIRED_AND = "PAIRED_AND"
PAIRED_MIN = "PAIRED_MIN"
PAIRED_90 = "PAIRED_90"
POLICIES = ("SINGLE_CHAIN_OR", PAIRED_AND, PAIRED_MIN)


@dataclass(frozen=True)
class PolicyGraph:
    assignments: pd.DataFrame
    clusters: pd.DataFrame
    edges: pd.DataFrame
    pairwise: dict[tuple[str, str], dict[str, float]]


def _find(parent: dict[str, str], item: str) -> str:
    while parent[item] != item:
        parent[item] = parent[parent[item]]
        item = parent[item]
    return item


def _union(parent: dict[str, str], left: str, right: str) -> None:
    left_root, right_root = _find(parent, left), _find(parent, right)
    if left_root != right_root:
        parent[max(left_root, right_root)] = min(left_root, right_root)


def _policy_edge(reasons: set[str], policy: str) -> bool:
    if "antibody_id" in reasons:
        return True
    if policy == "SINGLE_CHAIN_OR":
        return bool(reasons.intersection({"VH", "VL"}))
    if policy in {PAIRED_AND, PAIRED_MIN}:
        return {"VH", "VL"}.issubset(reasons)
    raise ValueError(f"Unknown graph policy: {policy}")


def _edge_category(reasons: set[str]) -> str:
    if reasons == {"antibody_id"}:
        return "ANTIBODY_ID_ONLY"
    if reasons == {"VH"}:
        return "VH_ONLY"
    if reasons == {"VL"}:
        return "VL_ONLY"
    if reasons == {"VH", "VL"}:
        return "BOTH_CHAINS"
    return "MULTIPLE_REASONS"


def _validate_records(records: pd.DataFrame) -> pd.DataFrame:
    required = {"sequence_hash", "VH", "VL", "antibody_id"}
    missing = required - set(records.columns)
    if missing:
        raise ValueError(f"Missing graph columns: {sorted(missing)}")
    if records["sequence_hash"].duplicated().any():
        raise ValueError("Graph input must contain one row per sequence_hash")
    return records.sort_values("sequence_hash", kind="mergesort").reset_index(drop=True)


def build_policy_graph(
    records: pd.DataFrame,
    policy: str,
    threshold: float,
    pairwise: dict[tuple[str, str], dict[str, float]] | None = None,
) -> PolicyGraph:
    """Build a graph and connected components using identity fields only."""

    ordered = _validate_records(records)
    if pairwise is None:
        pairwise = pairwise_identity_records(ordered)
    hashes = ordered["sequence_hash"].astype(str).tolist()
    antibody_by_hash = ordered.set_index("sequence_hash")["antibody_id"].to_dict()
    parent = {value: value for value in hashes}
    edge_rows: list[dict[str, object]] = []

    for (left, right), identity in sorted(pairwise.items()):
        reasons: set[str] = set()
        left_id = "" if pd.isna(antibody_by_hash[left]) else str(antibody_by_hash[left]).strip()
        right_id = "" if pd.isna(antibody_by_hash[right]) else str(antibody_by_hash[right]).strip()
        if left_id and left_id == right_id:
            reasons.add("antibody_id")
        if identity["VH"] >= threshold:
            reasons.add("VH")
        if identity["VL"] >= threshold:
            reasons.add("VL")
        if not _policy_edge(reasons, policy):
            continue
        _union(parent, left, right)
        edge_rows.append(
            {
                "left_hash": left,
                "right_hash": right,
                "VH_identity": identity["VH"],
                "VL_identity": identity["VL"],
                "reasons": ";".join(sorted(reasons)),
                "category": _edge_category(reasons),
            }
        )

    members_by_root: dict[str, list[str]] = defaultdict(list)
    for sequence_hash in hashes:
        members_by_root[_find(parent, sequence_hash)].append(sequence_hash)
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
    edges = pd.DataFrame(edge_rows, columns=["left_hash", "right_hash", "VH_identity", "VL_identity", "reasons", "category"])
    component_reasons: dict[str, set[str]] = defaultdict(set)
    for row in edge_rows:
        component_id = component_by_hash[str(row["left_hash"])]
        component_reasons[component_id].update(str(row["reasons"]).split(";"))
    cluster_rows = []
    records_by_hash = ordered.set_index("sequence_hash")
    for members in components:
        component_id = members[0]
        ids = sorted(
            {
                str(records_by_hash.loc[value, "antibody_id"]).strip()
                for value in members
                if pd.notna(records_by_hash.loc[value, "antibody_id"])
                and str(records_by_hash.loc[value, "antibody_id"]).strip()
            }
        )
        cluster_rows.append(
            {
                "cluster_id": component_id,
                "member_count": len(members),
                "sequence_hashes": ";".join(members),
                "antibody_ids": ";".join(ids),
                "link_reason_summary": ";".join(sorted(component_reasons.get(component_id, set()))) or "singleton",
            }
        )
    return PolicyGraph(assignment, pd.DataFrame(cluster_rows), edges, pairwise)


def component_summary(graph: PolicyGraph) -> dict[str, object]:
    sizes = graph.clusters["member_count"].astype(int)
    return {
        "components": int(len(sizes)),
        "singleton_components": int((sizes == 1).sum()),
        "multi_sequence_components": int((sizes > 1).sum()),
        "largest_component": int(sizes.max()),
        "median_component_size": float(sizes.median()),
        "p95_component_size": float(np.percentile(sizes, 95)),
        "largest_component_percentage": float(sizes.max() / sizes.sum() * 100),
        "component_size_distribution": {
            str(size): int(count) for size, count in sizes.value_counts().sort_index().items()
        },
    }


def original_edge_diagnostic(graph: PolicyGraph) -> dict[str, object]:
    nodes = sorted(graph.assignments["sequence_hash"].astype(str))
    degree = {node: 0 for node in nodes}
    for row in graph.edges.itertuples(index=False):
        degree[row.left_hash] += 1
        degree[row.right_hash] += 1
    degree_values = np.array(list(degree.values()), dtype=float)
    category_counts = graph.edges["category"].value_counts().to_dict()
    nodes_by_category = {}
    for category in ("VH_ONLY", "VL_ONLY", "BOTH_CHAINS", "ANTIBODY_ID_ONLY", "MULTIPLE_REASONS"):
        subset = graph.edges[graph.edges["category"] == category]
        nodes_by_category[category] = int(set(subset["left_hash"]).union(subset["right_hash"]).__len__())
    top20 = [
        {"sequence_hash": node, "degree": int(degree[node])}
        for node in sorted(degree, key=lambda value: (-degree[value], value))[:20]
    ]
    return {
        "total_graph_edges": int(len(graph.edges)),
        "edge_categories": {
            category: int(category_counts.get(category, 0))
            for category in ("ANTIBODY_ID_ONLY", "VH_ONLY", "VL_ONLY", "BOTH_CHAINS", "MULTIPLE_REASONS")
        },
        "degree_statistics": {
            "mean": float(degree_values.mean()),
            "median": float(np.median(degree_values)),
            "p95": float(np.percentile(degree_values, 95)),
            "maximum": int(degree_values.max()),
        },
        "nodes_involved_by_category": nodes_by_category,
        "top20_highest_degree_nodes": top20,
    }


def articulation_points(graph: PolicyGraph) -> list[str]:
    """Return articulation points using a deterministic Tarjan DFS."""

    adjacency: dict[str, set[str]] = defaultdict(set)
    for row in graph.edges.itertuples(index=False):
        adjacency[row.left_hash].add(row.right_hash)
        adjacency[row.right_hash].add(row.left_hash)
    for node in graph.assignments["sequence_hash"].astype(str):
        adjacency.setdefault(node, set())
    discovery: dict[str, int] = {}
    low: dict[str, int] = {}
    parent: dict[str, str | None] = {}
    points: set[str] = set()
    clock = 0

    def visit(node: str) -> None:
        nonlocal clock
        clock += 1
        discovery[node] = low[node] = clock
        children = 0
        for neighbor in sorted(adjacency[node]):
            if neighbor not in discovery:
                parent[neighbor] = node
                children += 1
                visit(neighbor)
                low[node] = min(low[node], low[neighbor])
                if parent.get(node) is None and children > 1:
                    points.add(node)
                if parent.get(node) is not None and low[neighbor] >= discovery[node]:
                    points.add(node)
            elif neighbor != parent.get(node):
                low[node] = min(low[node], discovery[neighbor])

    for node in sorted(adjacency):
        if node not in discovery:
            parent[node] = None
            visit(node)
    return sorted(points)


def bridge_examples(graph: PolicyGraph, limit: int = 10) -> list[dict[str, str]]:
    vh_only: dict[str, list[str]] = defaultdict(list)
    vl_only: dict[str, list[str]] = defaultdict(list)
    for row in graph.edges.itertuples(index=False):
        if row.category == "VH_ONLY":
            vh_only[row.left_hash].append(row.right_hash)
            vh_only[row.right_hash].append(row.left_hash)
        if row.category == "VL_ONLY":
            vl_only[row.left_hash].append(row.right_hash)
            vl_only[row.right_hash].append(row.left_hash)
    examples = []
    for middle in sorted(set(vh_only).intersection(vl_only)):
        for left in sorted(vh_only[middle]):
            for right in sorted(vl_only[middle]):
                if left == right:
                    continue
                examples.append({"left": left, "middle": middle, "right": right, "first_link": "VH", "second_link": "VL"})
                if len(examples) >= limit:
                    return examples
    return examples


def threshold_connectivity_audit(
    records: pd.DataFrame,
    thresholds: Iterable[float] = (0.80, 0.85, 0.90, 0.95, 0.98, 1.00),
) -> tuple[list[dict[str, object]], bool]:
    pairwise = pairwise_identity_records(records)
    rows = []
    paired_equivalent = True
    for threshold in thresholds:
        graphs = {
            policy: build_policy_graph(records, policy, threshold, pairwise)
            for policy in POLICIES
        }
        and_edges = set(zip(graphs[PAIRED_AND].edges["left_hash"], graphs[PAIRED_AND].edges["right_hash"]))
        min_edges = set(zip(graphs[PAIRED_MIN].edges["left_hash"], graphs[PAIRED_MIN].edges["right_hash"]))
        paired_equivalent = paired_equivalent and and_edges == min_edges
        for policy, graph in graphs.items():
            summary = component_summary(graph)
            rows.append({"threshold": threshold, "policy": policy, "paired_and_equals_paired_min": and_edges == min_edges, **summary})
    return rows, paired_equivalent


def residual_single_chain_audit(
    assignments: pd.DataFrame,
    pairwise: dict[tuple[str, str], dict[str, float]],
) -> dict[str, object]:
    split_by_hash = assignments.set_index("sequence_hash")["split"].to_dict()
    conditions = {
        "VH_ge_0.90": lambda item: item["VH"] >= 0.90,
        "VL_ge_0.90": lambda item: item["VL"] >= 0.90,
        "VH_ge_0.80": lambda item: item["VH"] >= 0.80,
        "VL_ge_0.80": lambda item: item["VL"] >= 0.80,
        "paired_ge_0.80": lambda item: item["VH"] >= 0.80 and item["VL"] >= 0.80,
    }
    result = {}
    for name, predicate in conditions.items():
        pairs = [
            pair
            for pair, identities in pairwise.items()
            if split_by_hash[pair[0]] != split_by_hash[pair[1]] and predicate(identities)
        ]
        affected = sorted({value for pair in pairs for value in pair})
        result[name] = {"pairs": len(pairs), "affected_sequences": len(affected)}
    return result
