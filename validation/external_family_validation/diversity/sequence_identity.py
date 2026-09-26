"""Deterministic identity summaries using the existing global aligner."""

from __future__ import annotations

import random
from typing import Any

import pandas as pd

from validation.ml_benchmark.similarity import global_identity


def paired_identity(left: dict[str, Any], right: dict[str, Any]) -> dict[str, float]:
    vh = global_identity(left.get("VH", ""), right.get("VH", ""))
    vl = global_identity(left.get("VL", ""), right.get("VL", ""))
    return {"VH": vh, "VL": vl, "paired_min": min(vh, vl)}


def sample_pair_indices(size: int, max_pairs: int = 10_000, seed: int = 7) -> list[tuple[int, int]]:
    if size < 2:
        return []
    total = size * (size - 1) // 2
    if total <= max_pairs:
        return [(left, right) for left in range(size) for right in range(left + 1, size)]
    rng = random.Random(seed)
    selected: set[tuple[int, int]] = set()
    while len(selected) < max_pairs:
        left = rng.randrange(size - 1)
        right = rng.randrange(left + 1, size)
        selected.add((left, right))
    return sorted(selected)


def summarize_values(values: list[float]) -> dict[str, float | int | None]:
    if not values:
        return {"n": 0, "min": None, "q25": None, "median": None, "q75": None, "max": None, "mean": None}
    series = pd.Series(values, dtype=float)
    return {
        "n": int(series.size),
        "min": float(series.min()),
        "q25": float(series.quantile(0.25)),
        "median": float(series.median()),
        "q75": float(series.quantile(0.75)),
        "max": float(series.max()),
        "mean": float(series.mean()),
    }


def compute_identity_sample(records: pd.DataFrame, *, max_pairs: int = 10_000, seed: int = 7) -> dict[str, Any]:
    required = {"sequence_hash", "VH", "VL"}
    missing = required - set(records.columns)
    if missing:
        raise ValueError(f"identity sample missing columns: {sorted(missing)}")
    unique = records.sort_values("sequence_hash", kind="mergesort").drop_duplicates("sequence_hash")
    rows = unique[["sequence_hash", "VH", "VL"]].to_dict("records")
    vh_values: list[float] = []
    vl_values: list[float] = []
    paired_values: list[float] = []
    for left, right in sample_pair_indices(len(rows), max_pairs=max_pairs, seed=seed):
        identity = paired_identity(rows[left], rows[right])
        vh_values.append(identity["VH"])
        vl_values.append(identity["VL"])
        paired_values.append(identity["paired_min"])
    return {
        "unit": "unique valid paired VH/VL sequence_hash",
        "method": "deterministic sample of global pairwise alignments",
        "seed": seed,
        "max_pairs": max_pairs,
        "unique_sequences": len(rows),
        "sampled_pairs": len(paired_values),
        "VH": summarize_values(vh_values),
        "VL": summarize_values(vl_values),
        "paired_min": summarize_values(paired_values),
    }
