from __future__ import annotations

import json
from pathlib import Path

import pandas as pd

from validation.ml_benchmark.similarity import (
    build_leakage_components,
    cross_split_identity_counts,
    global_identity,
)
from validation.ml_benchmark.split import assign_component_splits, build_split_plan
from validation.ml_benchmark_spec import LEAKAGE_IDENTITY_THRESHOLD
from validation.run_ml_benchmark_split import write_split_artifacts


ROOT = Path(__file__).resolve().parents[2]
PRIMARY = ROOT / "validation/data/external_validation/aintibody_primary_population.csv"
PROCESSED = ROOT / "validation/data/processed/aintibody_2026.csv"


def test_global_identity_is_symmetric_and_self_identity_is_one() -> None:
    assert global_identity("AAAA", "AAAA") == 1.0
    assert global_identity("ABCD", "ABXCD") == global_identity("ABXCD", "ABCD")
    assert global_identity("ABCD", "ABXCD") == 0.8


def test_component_graph_is_transitive() -> None:
    rows = pd.DataFrame(
        [
            {"sequence_hash": "a", "VH": "AAAA", "VL": "CCCC", "antibody_id": "one"},
            {"sequence_hash": "b", "VH": "AAAT", "VL": "CCCC", "antibody_id": "two"},
            {"sequence_hash": "c", "VH": "AATT", "VL": "GGGG", "antibody_id": "three"},
        ]
    )
    assignments, clusters, _ = build_leakage_components(rows, threshold=0.75)
    assert assignments["cluster_id"].nunique() == 1
    assert clusters.iloc[0]["member_count"] == 3


def test_exact_sequence_and_each_link_type_cluster_together() -> None:
    rows = pd.DataFrame(
        [
            {"sequence_hash": "a", "VH": "AAAA", "VL": "CCCC", "antibody_id": "one"},
            {"sequence_hash": "b", "VH": "AAAA", "VL": "CCCT", "antibody_id": "two"},
            {"sequence_hash": "c", "VH": "AAAT", "VL": "GGGG", "antibody_id": "two"},
        ]
    )
    assignments, _, _ = build_leakage_components(rows, threshold=0.90)
    assert assignments["cluster_id"].nunique() == 1


def test_component_assignment_is_deterministic_and_outcome_blind() -> None:
    identity = pd.DataFrame(
        [
            {"sequence_hash": "a", "cluster_id": "a", "outcome": "x"},
            {"sequence_hash": "b", "cluster_id": "b", "outcome": "y"},
            {"sequence_hash": "c", "cluster_id": "c", "outcome": "z"},
            {"sequence_hash": "d", "cluster_id": "d", "outcome": "q"},
        ]
    )
    components = identity[["sequence_hash", "cluster_id"]]
    first = assign_component_splits(identity, components)
    changed = identity.assign(outcome=["changed"] * 4)
    second = assign_component_splits(changed, components)
    pd.testing.assert_frame_equal(first, second)


def test_frozen_population_has_no_cross_split_primary_identity_leakage() -> None:
    plan = build_split_plan(PRIMARY, PROCESSED)
    counts = cross_split_identity_counts(plan.assignments, plan.pairwise_identities)
    assert len(plan.identity) == 476
    assert counts["exact_sequence_hash_overlap_pairs"] == 0
    assert counts["VH_identity_ge_0.90_pairs"] == 0
    assert counts["VL_identity_ge_0.90_pairs"] == 0
    split_ids = plan.identity.groupby("split")["antibody_id"].apply(set).to_dict()
    assert not (split_ids.get("TRAIN", set()) & split_ids.get("VALIDATION", set()))
    assert not (split_ids.get("TRAIN", set()) & split_ids.get("TEST", set()))
    assert not (split_ids.get("VALIDATION", set()) & split_ids.get("TEST", set()))
    assert plan.assignments["split"].notna().all()
    assert LEAKAGE_IDENTITY_THRESHOLD == 0.90


def test_split_artifacts_are_deterministic_and_test_features_have_no_outcomes(tmp_path: Path) -> None:
    first_dir = tmp_path / "first"
    second_dir = tmp_path / "second"
    first = write_split_artifacts(first_dir)
    second = write_split_artifacts(second_dir)
    for name in first:
        assert first[name].read_bytes() == second[name].read_bytes(), name

    test_features = pd.read_csv(first["test_features"])
    labels = pd.read_csv(first["sealed_test_labels"])
    forbidden = {"Tm, C", "Tagg, C", "HIC RT in gradient (min)", "average BVP score", "average dPW", "total_developability_score", "derived_binary_status"}
    assert not forbidden.intersection(test_features.columns)
    assert forbidden.issubset(labels.columns)
    seal = json.loads(first["test_label_seal"].read_text(encoding="utf-8"))
    assert seal["sealed"] is True
    assert seal["rows"] == len(labels)
    audit = json.loads(first["split_audit"].read_text(encoding="utf-8"))
    assert audit["component_count"] == 1
    assert audit["split_review_required"] is True
