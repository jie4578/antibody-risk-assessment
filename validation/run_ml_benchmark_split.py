"""Create Phase 5A split and label-sealing artifacts.

Assignment is performed from identity fields only.  Outcome columns are read
after assignment solely to produce the audit and the sealed test-label file.
This script does not train a model, build embeddings, or calculate metrics.
"""

from __future__ import annotations

import hashlib
import json
from pathlib import Path

import pandas as pd

from validation.ml_benchmark.split import SplitPlan, audit_cross_split_leakage, build_split_plan
from validation.ml_benchmark_spec import (
    AUDIT_IDENTITY_THRESHOLD,
    FROZEN_SCIENTIFIC_BASELINE,
    IDENTITY_COLUMNS,
    CONTINUOUS_ENDPOINT_COLUMNS,
    OUTCOME_COLUMNS,
    PRIMARY_POPULATION_ROWS,
    SPLIT_TARGET_FRACTIONS,
)


ROOT = Path(__file__).resolve().parents[1]
PRIMARY_PATH = ROOT / "validation/data/external_validation/aintibody_primary_population.csv"
PROCESSED_PATH = ROOT / "validation/data/processed/aintibody_2026.csv"
DEFAULT_OUTPUT_DIR = ROOT / "validation/data/ml_benchmark"

LABEL_COLUMNS = OUTCOME_COLUMNS


def _write_csv(frame: pd.DataFrame, path: Path) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    frame.to_csv(path, index=False, lineterminator="\n")


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _identity_columns(plan: SplitPlan) -> list[str]:
    return [column for column in IDENTITY_COLUMNS if column in plan.identity.columns] + ["cluster_id", "split"]


def _load_outcome_table(plan: SplitPlan) -> pd.DataFrame:
    primary = pd.read_csv(PRIMARY_PATH, dtype=str, usecols=["sequence_hash", "representative_record_id", *OUTCOME_COLUMNS])
    identity = plan.identity.copy()
    merged = identity.merge(primary, on=["sequence_hash", "representative_record_id"], how="left", validate="one_to_one")
    if merged[list(OUTCOME_COLUMNS)].isna().all(axis=1).any():
        raise ValueError("Outcome join lost all endpoint fields for a primary row")
    return merged


def _outcome_audit(table: pd.DataFrame) -> dict[str, object]:
    result: dict[str, object] = {"rows": int(len(table)), "missing": {}}
    for column in LABEL_COLUMNS:
        result["missing"][column] = int(table[column].isna().sum())
    classified = table["derived_binary_status"].isin(["DEVELOPABLE", "NOT_DEVELOPABLE"])
    result["composite_classification_n"] = int(classified.sum())
    result["missing_composite_n"] = int((~classified).sum())
    result["developable_n"] = int((table["derived_binary_status"] == "DEVELOPABLE").sum())
    result["not_developable_n"] = int((table["derived_binary_status"] == "NOT_DEVELOPABLE").sum())
    result["positive_prevalence"] = (
        result["not_developable_n"] / result["composite_classification_n"]
        if result["composite_classification_n"]
        else None
    )
    result["endpoint_availability"] = {
        endpoint: {
            "column": column,
            "available_n": int(table[column].notna().sum()),
            "missing_n": int(table[column].isna().sum()),
        }
        for endpoint, column in CONTINUOUS_ENDPOINT_COLUMNS.items()
    }
    return result


def _cross_split_antibody_overlap(plan: SplitPlan) -> int:
    by_split = {
        split: {
            str(value).strip()
            for value in plan.identity.loc[plan.identity["split"] == split, "antibody_id"]
            if pd.notna(value) and str(value).strip()
        }
        for split in ("TRAIN", "VALIDATION", "TEST")
    }
    return sum(
        len(by_split[left] & by_split[right])
        for left, right in (("TRAIN", "VALIDATION"), ("TRAIN", "TEST"), ("VALIDATION", "TEST"))
    )


def _split_audit(plan: SplitPlan, table: pd.DataFrame) -> dict[str, object]:
    counts = plan.identity["split"].value_counts().to_dict()
    split_audit = {
        "frozen_baseline": FROZEN_SCIENTIFIC_BASELINE,
        "primary_population_rows": int(len(plan.identity)),
        "primary_population_expected_rows": PRIMARY_POPULATION_ROWS,
        "assignment_outcome_blind": True,
        "performance_metrics_calculated": False,
        "component_count": int(plan.clusters.shape[0]),
        "multi_member_component_count": int((plan.clusters["member_count"] > 1).sum()),
        "singleton_component_count": int((plan.clusters["member_count"] == 1).sum()),
        "largest_component_rows": int(plan.clusters["member_count"].max()),
        "median_component_rows": float(plan.clusters["member_count"].median()),
        "p95_component_rows": float(plan.clusters["member_count"].quantile(0.95)),
        "component_size_distribution": {
            str(size): int(count)
            for size, count in plan.clusters["member_count"].value_counts().sort_index().items()
        },
        "components_linked_by_antibody_id": int(
            plan.clusters["link_reason_summary"].str.contains("antibody_id", regex=False).sum()
        ),
        "components_linked_by_VH_identity": int(
            plan.clusters["link_reason_summary"].str.contains("VH>=0.90", regex=False).sum()
        ),
        "components_linked_by_VL_identity": int(
            plan.clusters["link_reason_summary"].str.contains("VL>=0.90", regex=False).sum()
        ),
        "splits": {
            name: {
                "rows": int(counts.get(name, 0)),
                "target_fraction": fraction,
                "observed_fraction": counts.get(name, 0) / len(plan.identity),
                "outcome_audit": _outcome_audit(table[table["split"] == name]),
            }
            for name, fraction in SPLIT_TARGET_FRACTIONS.items()
        },
        "cross_split_leakage": audit_cross_split_leakage(plan),
        "same_antibody_id_across_splits": _cross_split_antibody_overlap(plan),
        "audit_identity_threshold": AUDIT_IDENTITY_THRESHOLD,
        "severe_review_flags": [],
    }
    for name, details in split_audit["splits"].items():
        if abs(details["observed_fraction"] - details["target_fraction"]) > 0.05:
            split_audit["severe_review_flags"].append(f"{name}_proportion_deviation_gt_5pp")
        if details["outcome_audit"]["composite_classification_n"] < 10:
            split_audit["severe_review_flags"].append(f"{name}_composite_n_lt_10")
        if details["outcome_audit"]["not_developable_n"] < 10:
            split_audit["severe_review_flags"].append(f"{name}_positive_n_lt_10")
        if name == "TEST":
            for endpoint, endpoint_audit in details["outcome_audit"]["endpoint_availability"].items():
                if endpoint_audit["available_n"] < 40:
                    split_audit["severe_review_flags"].append(f"TEST_{endpoint}_available_n_lt_40")
    split_audit["split_review_required"] = bool(split_audit["severe_review_flags"])
    return split_audit


def write_split_artifacts(output_dir: Path | str = DEFAULT_OUTPUT_DIR) -> dict[str, Path]:
    output_dir = Path(output_dir)
    output_dir.mkdir(parents=True, exist_ok=True)
    plan = build_split_plan(PRIMARY_PATH, PROCESSED_PATH)
    if len(plan.identity) != PRIMARY_POPULATION_ROWS:
        raise ValueError(f"Expected {PRIMARY_POPULATION_ROWS} primary rows, found {len(plan.identity)}")

    manifest_columns = _identity_columns(plan)
    split_manifest = plan.identity[manifest_columns].sort_values(["split", "sequence_hash"], kind="mergesort")
    cluster_manifest = plan.clusters.sort_values(["member_count", "cluster_id"], ascending=[False, True], kind="mergesort")
    table = _load_outcome_table(plan)
    table = table.sort_values(["split", "sequence_hash"], kind="mergesort").reset_index(drop=True)

    output_paths = {
        "split_manifest": output_dir / "split_manifest.csv",
        "cluster_manifest": output_dir / "cluster_manifest.csv",
        "train_population": output_dir / "train_population.csv",
        "validation_population": output_dir / "validation_population.csv",
        "test_features": output_dir / "test_features.csv",
        "sealed_test_labels": output_dir / "sealed_test_labels.csv",
        "test_label_seal": output_dir / "test_label_seal.json",
        "split_audit": output_dir / "split_audit.json",
    }
    _write_csv(split_manifest, output_paths["split_manifest"])
    _write_csv(cluster_manifest, output_paths["cluster_manifest"])

    identity_output = [column for column in IDENTITY_COLUMNS if column in table.columns] + ["cluster_id", "split"]
    train_validation_columns = identity_output + [column for column in OUTCOME_COLUMNS if column in table.columns]
    for name in ("TRAIN", "VALIDATION"):
        _write_csv(table.loc[table["split"] == name, train_validation_columns], output_paths[name.lower() + "_population"])

    test_rows = table.loc[table["split"] == "TEST"]
    _write_csv(test_rows[identity_output], output_paths["test_features"])
    label_key_columns = ["sequence_hash", "representative_record_id", "antibody_id", "cluster_id", "split"]
    _write_csv(
        test_rows[label_key_columns + [column for column in LABEL_COLUMNS if column in test_rows.columns]],
        output_paths["sealed_test_labels"],
    )
    seal = {
        "file": output_paths["sealed_test_labels"].name,
        "sha256": _sha256(output_paths["sealed_test_labels"]),
        "rows": int(len(test_rows)),
        "sealed": True,
        "outcomes_read_by": "Phase 5A artifact generation only; not used for split assignment",
    }
    output_paths["test_label_seal"].write_text(json.dumps(seal, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    output_paths["split_audit"].write_text(json.dumps(_split_audit(plan, table), indent=2, sort_keys=True) + "\n", encoding="utf-8")
    return output_paths


if __name__ == "__main__":
    paths = write_split_artifacts()
    print(f"Wrote {len(paths)} Phase 5A artifacts to {DEFAULT_OUTPUT_DIR}")
