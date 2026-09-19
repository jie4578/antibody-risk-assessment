from __future__ import annotations

import ast
import hashlib
import json
from pathlib import Path

import pandas as pd
import pytest

from validation.ml_benchmark.paired_policy import (
    PAIRED_AND,
    PAIRED_MIN,
    build_policy_graph,
    component_summary,
    original_edge_diagnostic,
    residual_single_chain_audit,
    threshold_connectivity_audit,
)
from validation.ml_benchmark.similarity import global_identity, pairwise_identity_records
from validation.ml_benchmark.split import assign_component_splits, load_primary_identity
from validation.ml_benchmark_spec_v1_1 import AMENDMENT_ID, NEW_POLICY, PRIOR_POLICY
from validation.ml_benchmark_spec import OUTCOME_COLUMNS
from validation.run_ml_benchmark_diagnostic import (
    DEFAULT_OUTPUT_DIR,
    PRIMARY_PATH,
    PROCESSED_PATH,
    SplitPolicyReviewRequired,
    write_paired90_artifacts,
)


ROOT = Path(__file__).resolve().parents[2]


def _records() -> pd.DataFrame:
    return pd.DataFrame(
        [
            {"sequence_hash": "a", "VH": "AAAA", "VL": "CCCC", "antibody_id": "one"},
            {"sequence_hash": "b", "VH": "AAAA", "VL": "CCCT", "antibody_id": "two"},
            {"sequence_hash": "c", "VH": "AAAT", "VL": "GGGG", "antibody_id": "three"},
        ]
    )


def test_original_policy_reproduces_frozen_one_component_result() -> None:
    identity = load_primary_identity(PRIMARY_PATH, PROCESSED_PATH)
    pairwise = pairwise_identity_records(identity)
    graph = build_policy_graph(identity, "SINGLE_CHAIN_OR", 0.90, pairwise)
    summary = component_summary(graph)
    assert len(identity) == 476
    assert summary["components"] == 1
    assert summary["largest_component"] == 476
    assert original_edge_diagnostic(graph)["total_graph_edges"] > 0


def test_paired_and_equals_paired_min_and_link_policy_is_outcome_blind() -> None:
    records = _records()
    pairwise = pairwise_identity_records(records)
    and_graph = build_policy_graph(records, PAIRED_AND, 0.75, pairwise)
    min_graph = build_policy_graph(records, PAIRED_MIN, 0.75, pairwise)
    assert set(zip(and_graph.edges.left_hash, and_graph.edges.right_hash)) == set(zip(min_graph.edges.left_hash, min_graph.edges.right_hash))
    vh_only = build_policy_graph(records.iloc[[0, 1]], PAIRED_AND, 0.90, pairwise_identity_records(records.iloc[[0, 1]]))
    assert len(vh_only.edges) == 0
    vl_only_records = records.iloc[[0, 2]].copy()
    vl_only_records.loc[vl_only_records.index[1], "VL"] = "CCCC"
    vl_only = build_policy_graph(vl_only_records, PAIRED_AND, 0.90, pairwise_identity_records(vl_only_records))
    assert len(vl_only.edges) == 0
    same_id_records = records.copy()
    same_id_records.loc[same_id_records["sequence_hash"] == "c", "antibody_id"] = "two"
    same_id = build_policy_graph(same_id_records, PAIRED_AND, 1.00, pairwise_identity_records(same_id_records))
    same_id_clusters = same_id.assignments.set_index("sequence_hash")["cluster_id"]
    assert same_id_clusters["b"] == same_id_clusters["c"]
    changed = records.assign(outcome=["x", "y", "z"])
    changed_graph = build_policy_graph(changed.drop(columns="outcome"), PAIRED_AND, 0.75, pairwise)
    assert changed_graph.assignments.equals(and_graph.assignments)


def test_threshold_audit_verifies_paired_equivalence() -> None:
    rows, equivalent = threshold_connectivity_audit(_records(), (0.80, 0.90, 1.00))
    assert equivalent is True
    assert {row["policy"] for row in rows} == {"SINGLE_CHAIN_OR", PAIRED_AND, PAIRED_MIN}


def test_identity_implementation_is_unchanged() -> None:
    assert global_identity("ABCD", "ABCD") == 1.0
    assert global_identity("ABCD", "ABXCD") == global_identity("ABXCD", "ABCD")


def test_paired90_artifacts_stop_without_overwriting_v1_outputs(tmp_path: Path) -> None:
    old_split = ROOT / "validation/data/ml_benchmark/split_manifest.csv"
    old_bytes = old_split.read_bytes() if old_split.exists() else None
    with pytest.raises(SplitPolicyReviewRequired, match="SPLIT_POLICY_REVIEW_REQUIRED"):
        write_paired90_artifacts(tmp_path / "paired90")
    assert old_split.exists()
    if old_bytes is not None:
        assert old_split.read_bytes() == old_bytes
    assert not (tmp_path / "paired90").exists()


def test_usable_synthetic_paired90_path_seals_labels_without_outcomes_in_features(tmp_path: Path) -> None:
    rows = []
    processed_rows = []
    for index, (vh, vl) in enumerate((("AAAA", "CCCC"), ("GGGG", "TTTT"), ("LLLL", "MMMM"), ("PPPP", "QQQQ")), start=1):
        record_id = str(index)
        sequence_hash = f"hash-{index}"
        common = {
            "dataset": "aintibody_2026",
            "sequence_hash": sequence_hash,
            "representative_record_id": record_id,
            "source_record_count": "1",
            "source_record_ids": record_id,
            "duplicate_resolution": "none",
            "VH": vh,
            "VL": vl,
            "record_type": "submission",
            "challenge": "1",
        }
        common.update(
            {
                "Tm, C": "70",
                "Tm_original_status": "measured",
                "Tagg, C": "60",
                "Tagg_original_status": "measured",
                "HIC RT in gradient (min)": "10",
                "HIC_original_status": "measured",
                "average BVP score": "1",
                "BVP_original_status": "measured",
                "average dPW": "1",
                "AC-SINS_original_status": "measured",
                "total_developability_score": "1",
                "derived_binary_status": "DEVELOPABLE",
            }
        )
        rows.append(common)
        processed_rows.append(
            {
                "record_id": record_id,
                "antibody_id": f"ab-{index}",
                "sequence_hash": sequence_hash,
                "VH": vh,
                "VL": vl,
                "record_type": "submission",
                "challenge": "1",
            }
        )
    primary_path = tmp_path / "primary.csv"
    processed_path = tmp_path / "processed.csv"
    pd.DataFrame(rows).to_csv(primary_path, index=False)
    pd.DataFrame(processed_rows).to_csv(processed_path, index=False)
    paths = write_paired90_artifacts(tmp_path / "paired90", primary_path, processed_path, expected_population=4)
    features = pd.read_csv(paths["test_features"])
    labels = pd.read_csv(paths["sealed_test_labels"])
    forbidden = set(OUTCOME_COLUMNS)
    assert not forbidden.intersection(features.columns)
    assert forbidden.issubset(labels.columns)
    seal = json.loads(paths["test_label_seal"].read_text(encoding="utf-8"))
    actual_hash = hashlib.sha256(paths["sealed_test_labels"].read_bytes()).hexdigest()
    assert seal["sealed"] is True
    assert seal["sha256"] == actual_hash


def test_phase_5a1_modules_have_no_model_or_embedding_calls() -> None:
    paths = [
        ROOT / "validation/ml_benchmark/paired_policy.py",
        ROOT / "validation/ml_benchmark_spec_v1_1.py",
        ROOT / "validation/run_ml_benchmark_diagnostic.py",
    ]
    forbidden_imports = {"sklearn", "torch", "transformers", "esm", "core", "scoring"}
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
        assert ".fit(" not in source
        assert ".predict(" not in source
        assert "roc_auc" not in source


def test_amendment_metadata_is_versioned() -> None:
    assert AMENDMENT_ID == "ML_BENCHMARK_SPEC_V1_1"
    assert PRIOR_POLICY == "SINGLE_CHAIN_OR_90"
    assert NEW_POLICY == "PAIRED_90"
    protocol = (ROOT / "validation/ml_benchmark_protocol_amendment_001.md").read_text(encoding="utf-8")
    for phrase in ("ML_BENCHMARK_SPEC_V1", "SINGLE_CHAIN_OR_90", "PAIRED_90", "before any Phase 5B", "single-chain family similarity"):
        assert phrase in protocol
