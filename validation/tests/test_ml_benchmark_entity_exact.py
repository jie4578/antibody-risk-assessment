from __future__ import annotations

import ast
import hashlib
import json
from pathlib import Path

import pandas as pd

from validation.ml_benchmark.entity_exact import (
    ENTITY_EXACT_V1,
    assign_entity_splits,
    build_entity_exact_components,
    component_id_from_members,
    residual_similarity_audit,
)
from validation.ml_benchmark_spec import OUTCOME_COLUMNS
from validation.ml_benchmark_spec_v1_2 import (
    BENCHMARK_NAME,
    STRICT_GENERALIZATION_STATUS,
)
from validation.run_ml_benchmark_entity_exact import (
    DEFAULT_OUTPUT_DIR,
    PRIMARY_PATH,
    PROCESSED_PATH,
    write_entity_exact_artifacts,
)
from validation.ml_benchmark.split import load_primary_identity


ROOT = Path(__file__).resolve().parents[2]


def _toy_identity() -> pd.DataFrame:
    return pd.DataFrame(
        [
            {"sequence_hash": "a", "representative_record_id": "1", "antibody_id": "ab-1", "VH": "AAAA", "VL": "CCCC"},
            {"sequence_hash": "b", "representative_record_id": "2", "antibody_id": "ab-1", "VH": "AAAT", "VL": "CCCT"},
            {"sequence_hash": "c", "representative_record_id": "3", "antibody_id": "ab-2", "VH": "GGGG", "VL": "TTTT"},
            {"sequence_hash": "d", "representative_record_id": "4", "antibody_id": "ab-3", "VH": "GGGG", "VL": "TTTT"},
            {"sequence_hash": "e", "representative_record_id": "5", "antibody_id": "ab-4", "VH": "LLLL", "VL": "MMMM"},
        ]
    )


def test_frozen_population_is_exactly_476_rows() -> None:
    identity = load_primary_identity(PRIMARY_PATH, PROCESSED_PATH)
    assert len(identity) == 476
    assert identity["sequence_hash"].nunique() == 476
    assert not set(OUTCOME_COLUMNS).intersection(identity.columns)


def test_same_antibody_id_is_grouped() -> None:
    assignments, clusters = build_entity_exact_components(_toy_identity())
    ab1 = assignments.loc[assignments["sequence_hash"].isin(["a", "b"]), "component_id"]
    assert ab1.nunique() == 1
    assert bool(clusters.loc[clusters["component_id"] == ab1.iloc[0], "linked_by_antibody_id"].iloc[0])


def test_exact_paired_sequence_is_grouped_without_similarity_threshold() -> None:
    assignments, clusters = build_entity_exact_components(_toy_identity())
    exact = assignments.loc[assignments["sequence_hash"].isin(["c", "d"]), "component_id"]
    assert exact.nunique() == 1
    row = clusters.loc[clusters["component_id"] == exact.iloc[0]].iloc[0]
    assert bool(row["linked_by_exact_paired_sequence"])


def test_non_exact_pairs_are_not_grouped_by_similarity() -> None:
    rows = _toy_identity().iloc[[0, 1]].copy()
    rows.loc[rows["sequence_hash"] == "b", "antibody_id"] = "ab-new"
    assignments, _ = build_entity_exact_components(rows)
    assert assignments["component_id"].nunique() == 2


def test_component_ids_and_assignments_are_deterministic_and_outcome_blind() -> None:
    first_assignments, first_clusters = build_entity_exact_components(_toy_identity())
    changed = _toy_identity().assign(outcome=["x", "y", "z", "q", "r"])
    second_assignments, second_clusters = build_entity_exact_components(changed.drop(columns="outcome"))
    pd.testing.assert_frame_equal(first_assignments, second_assignments)
    pd.testing.assert_frame_equal(first_clusters, second_clusters)
    assert component_id_from_members(["b", "a"]) == component_id_from_members(["a", "b"])


def test_real_entity_components_and_split_are_usable() -> None:
    identity = load_primary_identity(PRIMARY_PATH, PROCESSED_PATH)
    assignments, clusters = build_entity_exact_components(identity)
    assert len(clusters) == 31
    assert int((clusters["member_count"] == 1).sum()) == 3
    assert int(clusters["member_count"].max()) == 27
    split = assign_entity_splits(identity, assignments, clusters)
    assert split["split"].value_counts().to_dict() == {"TRAIN": 285, "VALIDATION": 96, "TEST": 95}


def test_no_component_crosses_splits_and_exact_overlap_is_zero() -> None:
    identity = load_primary_identity(PRIMARY_PATH, PROCESSED_PATH)
    assignments, clusters = build_entity_exact_components(identity)
    split = assign_entity_splits(identity, assignments, clusters)
    joined = identity.merge(split[["sequence_hash", "component_id", "split"]], on="sequence_hash")
    assert joined.groupby("component_id")["split"].nunique().max() == 1
    assert len(set(joined.loc[joined.split == "TRAIN", "sequence_hash"]) & set(joined.loc[joined.split == "TEST", "sequence_hash"])) == 0


def test_residual_similarity_audit_is_deterministic_and_does_not_change_split() -> None:
    identity = load_primary_identity(PRIMARY_PATH, PROCESSED_PATH)
    assignments, clusters = build_entity_exact_components(identity)
    split = assign_entity_splits(identity, assignments, clusters)
    joined = identity.merge(split[["sequence_hash", "component_id", "split"]], on="sequence_hash")
    first = residual_similarity_audit(joined, "TEST")
    second = residual_similarity_audit(joined, "TEST")
    pd.testing.assert_frame_equal(first, second)
    assert len(first) == 95
    assert set(first["novelty_bin"]).issubset({"BIN_1", "BIN_2", "BIN_3", "BIN_4", "BIN_5"})
    assert not (first["max_paired_min_identity_to_train"] >= 1.0 - 1e-12).any()
    assert joined["split"].value_counts().to_dict() == {"TRAIN": 285, "VALIDATION": 96, "TEST": 95}


def test_output_features_and_labels_are_separate_and_sealed(tmp_path: Path) -> None:
    paths = write_entity_exact_artifacts(tmp_path / "entity_exact_v1")
    test_features = pd.read_csv(paths["test_features"], dtype=object)
    validation_features = pd.read_csv(paths["validation_features"], dtype=object)
    validation_labels = pd.read_csv(paths["validation_labels"], dtype=object)
    sealed = pd.read_csv(paths["sealed_test_labels"], dtype=object)
    forbidden = set(OUTCOME_COLUMNS) | {"Tm", "Tagg", "HIC", "BVP", "AC-SINS", "composite_class"}
    assert not forbidden.intersection(test_features.columns)
    assert not forbidden.intersection(validation_features.columns)
    assert {"Tm", "Tagg", "HIC", "BVP", "AC-SINS", "composite_class"}.issubset(sealed.columns)
    assert {"Tm", "Tagg", "HIC", "BVP", "AC-SINS", "composite_class"}.issubset(validation_labels.columns)
    assert not set(test_features["sequence_hash"]) & set(validation_labels["sequence_hash"])
    seal = json.loads(paths["test_label_seal"].read_text(encoding="utf-8"))
    assert seal["benchmark_spec"] == "ML_BENCHMARK_SPEC_V1_2"
    assert seal["split_policy"] == ENTITY_EXACT_V1
    assert seal["sha256"] == hashlib.sha256(paths["sealed_test_labels"].read_bytes()).hexdigest()


def test_split_audit_has_no_review_flags_and_records_endpoint_availability(tmp_path: Path) -> None:
    paths = write_entity_exact_artifacts(tmp_path / "entity_exact_v1")
    audit = json.loads(paths["split_audit"].read_text(encoding="utf-8"))
    assert audit["split_review_required"] is False
    assert audit["splits"]["TRAIN"]["rows"] == 285
    assert audit["splits"]["VALIDATION"]["rows"] == 96
    assert audit["splits"]["TEST"]["rows"] == 95
    assert audit["splits"]["TEST"]["outcome_audit"]["endpoint_availability"]["HIC"]["available_n"] == 72
    assert audit["leakage_checks"]["component_overlap"] == 0


def test_benchmark_claims_and_future_firewall_are_explicit() -> None:
    assert BENCHMARK_NAME == "AINTIBODY_INTERNAL_ENTITY_EXACT_V1"
    assert STRICT_GENERALIZATION_STATUS == "DEFERRED"
    protocol = (ROOT / "validation/ml_benchmark_protocol_amendment_002.md").read_text(encoding="utf-8")
    for phrase in ("ENTITY_EXACT_V1", "internal", "family-level generalization", "DEFERRED", "sealed_test_labels.csv"):
        assert phrase in protocol
    spec = (ROOT / "validation/ml_benchmark_spec_v1_2.py").read_text(encoding="utf-8")
    assert "PROHIBITED_CLAIMS" in spec


def test_phase_5a2_code_has_no_model_embedding_or_performance_execution() -> None:
    paths = [
        ROOT / "validation/ml_benchmark/entity_exact.py",
        ROOT / "validation/ml_benchmark_spec_v1_2.py",
        ROOT / "validation/run_ml_benchmark_entity_exact.py",
    ]
    forbidden_imports = {"sklearn", "torch", "transformers", "esm", "core", "scoring"}
    forbidden_terms = ("roc_auc", "pr_auc", "spearman", "mean_squared_error", "predict(", ".fit(")
    for path in paths:
        tree = ast.parse(path.read_text(encoding="utf-8"))
        imported = {
            alias.name.split(".")[0]
            for node in ast.walk(tree)
            if isinstance(node, ast.Import)
            for alias in node.names
        }
        imported.update(
            node.module.split(".")[0]
            for node in ast.walk(tree)
            if isinstance(node, ast.ImportFrom) and node.module
        )
        assert not imported.intersection(forbidden_imports)
        source = path.read_text(encoding="utf-8").lower()
        if path.name != "ml_benchmark_spec_v1_2.py":
            assert not any(term in source for term in forbidden_terms)
