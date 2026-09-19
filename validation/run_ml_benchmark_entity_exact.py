"""Create the outcome-safe Phase 5A.2 ENTITY_EXACT_V1 artifacts.

The split manifest is written before outcome columns are loaded.  This
runner only constructs benchmark data boundaries and residual relatedness
audits; it never trains a model, creates embeddings, or calculates metrics.
"""

from __future__ import annotations

import hashlib
import json
from pathlib import Path

import pandas as pd

from validation.ml_benchmark.entity_exact import (
    ENTITY_EXACT_V1,
    EntityExactPlan,
    build_entity_exact_plan,
    component_summary,
    cross_split_leakage_audit,
    identity_feature_columns,
    population_is_structurally_usable,
    residual_similarity_audit,
    similarity_summary,
)
from validation.ml_benchmark_spec import (
    CONTINUOUS_ENDPOINT_COLUMNS,
    FROZEN_SCIENTIFIC_BASELINE,
    OUTCOME_COLUMNS,
    PRIMARY_POPULATION_ROWS,
    SPLIT_TARGET_FRACTIONS,
)
from validation.ml_benchmark_spec_v1_2 import (
    BENCHMARK_NAME,
    BENCHMARK_TYPE,
    SPEC_VERSION,
    STRICT_GENERALIZATION_STATUS,
)


ROOT = Path(__file__).resolve().parents[1]
PRIMARY_PATH = ROOT / "validation/data/external_validation/aintibody_primary_population.csv"
PROCESSED_PATH = ROOT / "validation/data/processed/aintibody_2026.csv"
DEFAULT_OUTPUT_DIR = ROOT / "validation/data/ml_benchmark/entity_exact_v1"

RAW_LABEL_COLUMNS = (
    "Tm, C",
    "Tm_original_status",
    "Tagg, C",
    "Tagg_original_status",
    "HIC RT in gradient (min)",
    "HIC_original_status",
    "average BVP score",
    "BVP_original_status",
    "average dPW",
    "AC-SINS_original_status",
    "total_developability_score",
    "derived_binary_status",
)
CANONICAL_LABEL_COLUMNS = (
    "sequence_hash",
    "representative_record_id",
    "antibody_id",
    "Tm",
    "Tagg",
    "HIC",
    "BVP",
    "AC-SINS",
    "total_developability_score",
    "composite_class",
)
CANONICAL_ENDPOINT_MAP = {
    "Tm": "Tm, C",
    "Tagg": "Tagg, C",
    "HIC": "HIC RT in gradient (min)",
    "BVP": "average BVP score",
    "AC-SINS": "average dPW",
}


class InternalBenchmarkRedesignRequired(RuntimeError):
    """Raised when exact entity components still cannot support a split."""


def _write_csv(frame: pd.DataFrame, path: Path) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    frame.to_csv(path, index=False, lineterminator="\n")


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _load_outcomes_after_split(primary_path: Path, plan: EntityExactPlan) -> pd.DataFrame:
    columns = ["sequence_hash", "representative_record_id", *RAW_LABEL_COLUMNS]
    source = pd.read_csv(primary_path, dtype=str, usecols=columns)
    joined = plan.identity[["sequence_hash", "representative_record_id", "antibody_id", "split"]].merge(
        source,
        on=["sequence_hash", "representative_record_id"],
        how="left",
        validate="one_to_one",
    )
    if len(joined) != len(plan.identity):
        raise ValueError("Outcome join changed the frozen population size")
    if joined[list(RAW_LABEL_COLUMNS)].isna().all(axis=1).any():
        raise ValueError("Outcome join lost all endpoint fields for a population row")
    return joined


def _canonical_labels(joined: pd.DataFrame) -> pd.DataFrame:
    result = joined[["sequence_hash", "representative_record_id", "antibody_id"]].copy()
    for target, source in CANONICAL_ENDPOINT_MAP.items():
        result[target] = joined[source]
    result["total_developability_score"] = joined["total_developability_score"]
    result["composite_class"] = joined["derived_binary_status"]
    return result.loc[:, list(CANONICAL_LABEL_COLUMNS)]


def _outcome_audit(labels: pd.DataFrame) -> dict[str, object]:
    classes = labels["composite_class"]
    result: dict[str, object] = {
        "rows": int(len(labels)),
        "developable": int((classes == "DEVELOPABLE").sum()),
        "not_developable": int((classes == "NOT_DEVELOPABLE").sum()),
        "missing": int((~classes.isin(["DEVELOPABLE", "NOT_DEVELOPABLE"])).sum()),
        "endpoint_availability": {},
    }
    for endpoint in CANONICAL_ENDPOINT_MAP:
        available = int(labels[endpoint].notna().sum())
        result["endpoint_availability"][endpoint] = {
            "available_n": available,
            "missing_n": int(len(labels) - available),
        }
    return result


def _quality_flags(plan: EntityExactPlan, labels: pd.DataFrame) -> list[str]:
    flags: list[str] = []
    total = len(plan.identity)
    for split, target in SPLIT_TARGET_FRACTIONS.items():
        observed = int((plan.identity["split"] == split).sum()) / total
        if abs(observed - target) > 0.05:
            flags.append(f"{split}_proportion_deviation_gt_5pp")
        split_labels = labels[plan.identity["split"].to_numpy() == split]
        if split in {"VALIDATION", "TEST"}:
            if int((split_labels["composite_class"] == "DEVELOPABLE").sum()) < 10:
                flags.append(f"{split}_developable_n_lt_10")
            if int((split_labels["composite_class"] == "NOT_DEVELOPABLE").sum()) < 10:
                flags.append(f"{split}_not_developable_n_lt_10")
        if split == "TEST":
            for endpoint in CANONICAL_ENDPOINT_MAP:
                if int(split_labels[endpoint].notna().sum()) < 40:
                    flags.append(f"TEST_{endpoint}_available_n_lt_40")
    return flags


def _build_split_audit(
    plan: EntityExactPlan,
    labels: pd.DataFrame,
    test_similarity: pd.DataFrame,
    validation_similarity: pd.DataFrame,
) -> dict[str, object]:
    summary = component_summary(plan.clusters)
    audit: dict[str, object] = {
        "benchmark_name": BENCHMARK_NAME,
        "benchmark_type": BENCHMARK_TYPE,
        "benchmark_spec": SPEC_VERSION,
        "frozen_scientific_baseline": FROZEN_SCIENTIFIC_BASELINE,
        "population": int(len(plan.identity)),
        "population_expected": PRIMARY_POPULATION_ROWS,
        "grouping_policy": ENTITY_EXACT_V1,
        "assignment_outcome_blind": True,
        "outcomes_loaded_after_split_manifest": True,
        "component_summary": summary,
        "splits": {},
        "leakage_checks": cross_split_leakage_audit(plan.identity),
        "residual_similarity": {
            "TEST": similarity_summary(test_similarity),
            "VALIDATION": similarity_summary(validation_similarity),
        },
        "split_review_required": False,
        "split_review_flags": [],
        "ml_trained": False,
        "protein_lm_embeddings_generated": False,
        "ml_performance_calculated": False,
        "strict_family_generalization_status": STRICT_GENERALIZATION_STATUS,
    }
    for split, target in SPLIT_TARGET_FRACTIONS.items():
        subset = labels[plan.identity["split"].to_numpy() == split]
        audit["splits"][split] = {
            "rows": int(len(subset)),
            "target_fraction": target,
            "observed_fraction": float(len(subset) / len(plan.identity)),
            "outcome_audit": _outcome_audit(subset),
        }
    flags = _quality_flags(plan, labels)
    audit["split_review_flags"] = flags
    audit["split_review_required"] = bool(flags)
    return audit


def _identity_with_split(plan: EntityExactPlan) -> pd.DataFrame:
    fields = identity_feature_columns(plan.identity)
    return plan.identity.loc[:, fields].copy()


def write_entity_exact_artifacts(
    output_dir: str | Path = DEFAULT_OUTPUT_DIR,
    primary_path: str | Path = PRIMARY_PATH,
    processed_path: str | Path = PROCESSED_PATH,
    expected_population: int = PRIMARY_POPULATION_ROWS,
) -> dict[str, Path]:
    """Write deterministic Phase 5A.2 artifacts to the new ignored namespace."""

    output = Path(output_dir)
    primary = Path(primary_path)
    processed = Path(processed_path)
    plan = build_entity_exact_plan(str(primary), str(processed))
    if len(plan.identity) != expected_population:
        raise ValueError(f"Expected frozen population {expected_population}, got {len(plan.identity)}")
    if not population_is_structurally_usable(plan.clusters, len(plan.identity)):
        raise InternalBenchmarkRedesignRequired(
            "INTERNAL_BENCHMARK_REDESIGN_REQUIRED: exact entity components cannot support 60/20/20"
        )

    output.mkdir(parents=True, exist_ok=True)
    identity = _identity_with_split(plan)
    cluster_path = output / "cluster_manifest.csv"
    split_path = output / "split_manifest.csv"
    _write_csv(plan.clusters, cluster_path)
    _write_csv(plan.assignments, split_path)

    # The two manifests are frozen before any experimental outcome column is read.
    test_similarity = residual_similarity_audit(plan.identity, "TEST")
    validation_similarity = residual_similarity_audit(plan.identity, "VALIDATION")
    test_similarity_path = output / "test_similarity_audit.csv"
    validation_similarity_path = output / "validation_similarity_audit.csv"
    _write_csv(test_similarity, test_similarity_path)
    _write_csv(validation_similarity, validation_similarity_path)

    joined = _load_outcomes_after_split(primary, plan)
    canonical = _canonical_labels(joined)
    feature_columns = identity_feature_columns(plan.identity)
    feature_table = plan.identity.loc[:, feature_columns].copy()
    train_population = feature_table[plan.identity["split"] == "TRAIN"].merge(
        joined.loc[:, ["sequence_hash", *RAW_LABEL_COLUMNS]],
        on="sequence_hash",
        how="left",
        validate="one_to_one",
    )
    validation_features = feature_table[plan.identity["split"] == "VALIDATION"].copy()
    test_features = feature_table[plan.identity["split"] == "TEST"].copy()
    validation_labels = canonical[plan.identity["split"] == "VALIDATION"].copy()
    test_labels = canonical[plan.identity["split"] == "TEST"].copy()

    train_path = output / "train_population.csv"
    validation_features_path = output / "validation_features.csv"
    validation_labels_path = output / "validation_labels.csv"
    test_features_path = output / "test_features.csv"
    sealed_labels_path = output / "sealed_test_labels.csv"
    _write_csv(train_population, train_path)
    _write_csv(validation_features, validation_features_path)
    _write_csv(validation_labels, validation_labels_path)
    _write_csv(test_features, test_features_path)
    _write_csv(test_labels, sealed_labels_path)

    split_audit = _build_split_audit(plan, canonical, test_similarity, validation_similarity)
    split_audit_path = output / "split_audit.json"
    split_audit_path.write_text(json.dumps(split_audit, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    seal_path = output / "test_label_seal.json"
    seal_path.write_text(
        json.dumps(
            {
                "benchmark_spec": SPEC_VERSION,
                "split_policy": ENTITY_EXACT_V1,
                "test_n": int(len(test_labels)),
                "sha256": _sha256(sealed_labels_path),
                "created_by_phase": "Phase 5A.2",
                "sealed": True,
            },
            indent=2,
        )
        + "\n",
        encoding="utf-8",
    )
    return {
        "cluster_manifest": cluster_path,
        "split_manifest": split_path,
        "train_population": train_path,
        "validation_features": validation_features_path,
        "validation_labels": validation_labels_path,
        "test_features": test_features_path,
        "sealed_test_labels": sealed_labels_path,
        "split_audit": split_audit_path,
        "test_similarity_audit": test_similarity_path,
        "validation_similarity_audit": validation_similarity_path,
        "test_label_seal": seal_path,
    }


def main() -> None:
    write_entity_exact_artifacts()


if __name__ == "__main__":
    main()
