"""Run Phase 5A.1 graph diagnostics and write the amended PAIRED_90 split."""

from __future__ import annotations

import hashlib
import json
from pathlib import Path

import pandas as pd

from validation.ml_benchmark.paired_policy import (
    PAIRED_AND,
    SINGLE_CHAIN_OR_90,
    PolicyGraph,
    articulation_points,
    bridge_examples,
    build_policy_graph,
    component_summary,
    original_edge_diagnostic,
    residual_single_chain_audit,
    threshold_connectivity_audit,
)
from validation.ml_benchmark.similarity import pairwise_identity_records
from validation.ml_benchmark.split import assign_component_splits, load_primary_identity
from validation.ml_benchmark_spec import IDENTITY_COLUMNS, OUTCOME_COLUMNS, SPLIT_TARGET_FRACTIONS
from validation.ml_benchmark_spec_v1_1 import (
    AMENDMENT_ID,
    AMENDMENT_REASON,
    NEW_POLICY,
    POPULATION,
    PRIOR_POLICY,
    PRIOR_SPEC,
    THRESHOLD,
)


ROOT = Path(__file__).resolve().parents[1]
PRIMARY_PATH = ROOT / "validation/data/external_validation/aintibody_primary_population.csv"
PROCESSED_PATH = ROOT / "validation/data/processed/aintibody_2026.csv"
DEFAULT_OUTPUT_DIR = ROOT / "validation/data/ml_benchmark/paired90"

LABEL_COLUMNS = OUTCOME_COLUMNS
CONTINUOUS_ENDPOINT_COLUMNS = {
    "Tm": "Tm, C",
    "Tagg": "Tagg, C",
    "HIC": "HIC RT in gradient (min)",
    "BVP": "average BVP score",
    "AC-SINS": "average dPW",
}


class SplitPolicyReviewRequired(RuntimeError):
    """Raised when PAIRED_90 is still unusable for a whole-component split."""


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _write_csv(frame: pd.DataFrame, path: Path) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    frame.to_csv(path, index=False, lineterminator="\n")


def _outcome_table(identity: pd.DataFrame, primary_path: Path) -> pd.DataFrame:
    primary = pd.read_csv(primary_path, dtype=str, usecols=["sequence_hash", "representative_record_id", *OUTCOME_COLUMNS])
    return identity.merge(primary, on=["sequence_hash", "representative_record_id"], how="left", validate="one_to_one")


def _outcome_audit(table: pd.DataFrame) -> dict[str, object]:
    classified = table["derived_binary_status"].isin(["DEVELOPABLE", "NOT_DEVELOPABLE"])
    return {
        "rows": int(len(table)),
        "developable": int((table["derived_binary_status"] == "DEVELOPABLE").sum()),
        "not_developable": int((table["derived_binary_status"] == "NOT_DEVELOPABLE").sum()),
        "missing_composite": int((~classified).sum()),
        "positive_prevalence": float((table["derived_binary_status"] == "NOT_DEVELOPABLE").sum() / classified.sum()) if classified.sum() else None,
        "endpoint_availability": {
            name: {"available": int(table[column].notna().sum()), "missing": int(table[column].isna().sum())}
            for name, column in CONTINUOUS_ENDPOINT_COLUMNS.items()
        },
    }


def _cross_split_antibody_ids(identity: pd.DataFrame) -> int:
    sets = {
        split: {
            str(value).strip()
            for value in identity.loc[identity["split"] == split, "antibody_id"]
            if pd.notna(value) and str(value).strip()
        }
        for split in ("TRAIN", "VALIDATION", "TEST")
    }
    return sum(len(sets[left] & sets[right]) for left, right in (("TRAIN", "VALIDATION"), ("TRAIN", "TEST"), ("VALIDATION", "TEST")))


def _split_audit(identity: pd.DataFrame, graph: PolicyGraph, outcomes: pd.DataFrame, original: dict[str, object], threshold_rows: list[dict[str, object]], paired_equivalent: bool, population: int) -> dict[str, object]:
    counts = identity["split"].value_counts().to_dict()
    splits = {}
    severe = []
    for name, target in SPLIT_TARGET_FRACTIONS.items():
        subset = outcomes[outcomes["split"] == name]
        audit = _outcome_audit(subset)
        observed = counts.get(name, 0) / len(identity)
        splits[name] = {"rows": int(counts.get(name, 0)), "target_fraction": target, "observed_fraction": observed, **audit}
        if abs(observed - target) > 0.05:
            severe.append(f"{name}_proportion_deviation_gt_5pp")
        if name in {"VALIDATION", "TEST"} and (audit["developable"] < 10 or audit["not_developable"] < 10):
            severe.append(f"{name}_classification_count_lt_10")
        if name == "TEST":
            for endpoint, values in audit["endpoint_availability"].items():
                if values["available"] < 40:
                    severe.append(f"TEST_{endpoint}_available_lt_40")
    return {
        "amendment_id": AMENDMENT_ID,
        "prior_policy": PRIOR_POLICY,
        "new_policy": NEW_POLICY,
        "frozen_population": population,
        "outcome_blind_assignment": True,
        "original_policy_diagnostic": original,
        "threshold_connectivity_audit": threshold_rows,
        "paired_and_equals_paired_min": paired_equivalent,
        "amended_policy_summary": component_summary(graph),
        "splits": splits,
        "cross_split_exact_sequence_overlap": 0,
        "cross_split_antibody_id_overlap": _cross_split_antibody_ids(identity),
        "cross_split_paired_ge_0.90_pairs": 0,
        "residual_single_chain_audit": residual_single_chain_audit(graph.assignments, graph.pairwise),
        "split_review_required": bool(severe),
        "severe_review_flags": severe,
        "ml_models_trained": False,
        "protein_lm_embeddings_generated": False,
        "ml_performance_calculated": False,
    }


def _diagnostic_summary(identity: pd.DataFrame, original_graph: PolicyGraph) -> dict[str, object]:
    edge_audit = original_edge_diagnostic(original_graph)
    antibody_edges = original_graph.edges[original_graph.edges["reasons"].str.contains("antibody_id", regex=False)]
    antibody_nodes = set(antibody_edges["left_hash"]).union(antibody_edges["right_hash"])
    return {
        **edge_audit,
        "nodes_involved_through_antibody_id": len(antibody_nodes),
        "articulation_points": articulation_points(original_graph),
        "bridge_examples": bridge_examples(original_graph),
        "original_component_summary": component_summary(original_graph),
    }


def write_paired90_artifacts(
    output_dir: Path | str = DEFAULT_OUTPUT_DIR,
    primary_path: Path | str = PRIMARY_PATH,
    processed_path: Path | str = PROCESSED_PATH,
    expected_population: int = POPULATION,
) -> dict[str, Path]:
    output_dir = Path(output_dir)
    primary_path = Path(primary_path)
    processed_path = Path(processed_path)
    identity = load_primary_identity(primary_path, processed_path)
    if len(identity) != expected_population:
        raise ValueError(f"Expected {expected_population} paired sequences, found {len(identity)}")
    pairwise = pairwise_identity_records(identity)
    original_graph = build_policy_graph(identity, "SINGLE_CHAIN_OR", THRESHOLD, pairwise)
    threshold_rows, paired_equivalent = threshold_connectivity_audit(identity, (0.80, 0.85, 0.90, 0.95, 0.98, 1.00))
    amended_graph = build_policy_graph(identity, PAIRED_AND, THRESHOLD, pairwise)
    amended_summary = component_summary(amended_graph)
    if amended_summary["components"] == 1 and amended_summary["largest_component"] == len(identity):
        raise SplitPolicyReviewRequired(
            "SPLIT_POLICY_REVIEW_REQUIRED: PAIRED_90 still produces one unusable giant component"
        )
    amended_assignments = assign_component_splits(identity, amended_graph.assignments)
    amended_split_graph = PolicyGraph(amended_assignments, amended_graph.clusters, amended_graph.edges, amended_graph.pairwise)
    enriched = identity.merge(amended_assignments, on="sequence_hash", validate="one_to_one")
    output_dir.mkdir(parents=True, exist_ok=True)
    outcomes = _outcome_table(enriched, primary_path)
    paths = {
        "cluster_manifest": output_dir / "cluster_manifest.csv",
        "split_manifest": output_dir / "split_manifest.csv",
        "train_population": output_dir / "train_population.csv",
        "validation_population": output_dir / "validation_population.csv",
        "test_features": output_dir / "test_features.csv",
        "sealed_test_labels": output_dir / "sealed_test_labels.csv",
        "test_label_seal": output_dir / "test_label_seal.json",
        "split_audit": output_dir / "split_audit.json",
    }
    identity_columns = [column for column in IDENTITY_COLUMNS if column in enriched.columns] + ["cluster_id", "split"]
    _write_csv(enriched[identity_columns].sort_values(["split", "sequence_hash"], kind="mergesort"), paths["split_manifest"])
    _write_csv(amended_graph.clusters.sort_values(["member_count", "cluster_id"], ascending=[False, True], kind="mergesort"), paths["cluster_manifest"])
    outcome_columns = identity_columns + [column for column in LABEL_COLUMNS if column in outcomes.columns]
    for split in ("TRAIN", "VALIDATION"):
        _write_csv(outcomes.loc[outcomes["split"] == split, outcome_columns], paths[split.lower() + "_population"])
    test_rows = outcomes[outcomes["split"] == "TEST"]
    _write_csv(test_rows[identity_columns], paths["test_features"])
    label_keys = ["sequence_hash", "representative_record_id", "antibody_id", "cluster_id", "split"]
    _write_csv(test_rows[label_keys + [column for column in LABEL_COLUMNS if column in test_rows.columns]], paths["sealed_test_labels"])
    paths["test_label_seal"].write_text(
        json.dumps({"file": paths["sealed_test_labels"].name, "sha256": _sha256(paths["sealed_test_labels"]), "rows": int(len(test_rows)), "sealed": True}, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )
    audit = _split_audit(enriched, amended_split_graph, outcomes, _diagnostic_summary(identity, original_graph), threshold_rows, paired_equivalent, expected_population)
    paths["split_audit"].write_text(json.dumps(audit, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    return paths


if __name__ == "__main__":
    written = write_paired90_artifacts()
    print(f"Wrote {len(written)} Phase 5A.1 artifacts to {DEFAULT_OUTPUT_DIR}")
