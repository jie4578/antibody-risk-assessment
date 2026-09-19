"""Frozen, outcome-blind Phase 5A benchmark specification.

This module defines the future benchmark contract only.  It deliberately does
not import production scientific code, read labels, train estimators, create
embeddings, or calculate performance metrics.
"""

from __future__ import annotations

from pathlib import Path

from validation.external_validation_spec import FROZEN_RULE_FEATURES


FROZEN_SCIENTIFIC_BASELINE = "d1487ed74bdfc52fb0b2015a25c4e91ee90af66d"
PHASE_5A_CHECKPOINT = "3013c04f2f2fde3003aa38a448736a0adeb75947"

DATASET = "aintibody_2026"
PRIMARY_POPULATION_ROWS = 476
PRIMARY_ANALYSIS_UNIT = "unique VH/VL sequence hash"

CONTROL_FEATURES = ("VH_length", "VL_length")
RULE48_FEATURES = tuple(FROZEN_RULE_FEATURES)
RULE48_FEATURE_MANIFEST = Path("validation/data/features/aintibody_rule_features.csv")

ESM2_CHECKPOINT = "facebook/esm2_t30_150M_UR50D"
ESM2_POOLING = "eval mode; strip BOS/EOS/pad; mean-pool VH and VL separately; concatenate"
ESM2_VH_DIMENSION = 640
ESM2_VL_DIMENSION = 640
ESM2_CONCATENATED_DIMENSION = 1280

FEATURE_BLOCKS = {
    "LENGTH_CONTROL": CONTROL_FEATURES,
    "RULE48": RULE48_FEATURES,
    "ESM2": (ESM2_CHECKPOINT,),
    "ESM2_PLUS_RULE48": (ESM2_CHECKPOINT,) + RULE48_FEATURES,
}

PRIMARY_ASSAYS = ("Tm", "Tagg", "HIC", "BVP", "AC-SINS")
POSITIVE_CLASS = "NOT_DEVELOPABLE"
COMPOSITE_DEVELOPABLE_MAX = 3
CONTINUOUS_ENDPOINT_COLUMNS = {
    "Tm": "Tm, C",
    "Tagg": "Tagg, C",
    "HIC": "HIC RT in gradient (min)",
    "BVP": "average BVP score",
    "AC-SINS": "average dPW",
}
OUTCOME_COLUMNS = (
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

IDENTITY_COLUMNS = (
    "dataset",
    "sequence_hash",
    "representative_record_id",
    "antibody_id",
    "VH",
    "VL",
    "record_type",
    "challenge",
    "source_record_count",
    "duplicate_resolution",
)

SPLIT_TARGET_FRACTIONS = {"TRAIN": 0.60, "VALIDATION": 0.20, "TEST": 0.20}
SPLIT_PRIORITY = ("TRAIN", "VALIDATION", "TEST")
LEAKAGE_IDENTITY_THRESHOLD = 0.90
AUDIT_IDENTITY_THRESHOLD = 0.80
ALIGNMENT_SCORING = {
    "mode": "global",
    "match_score": 2,
    "mismatch_score": -1,
    "open_gap_score": -2,
    "extend_gap_score": -1,
}

FUTURE_MODELS = {
    "Ridge": {"alpha": (0.01, 0.1, 1.0, 10.0, 100.0)},
    "LogisticRegression": {
        "C": (0.01, 0.1, 1.0, 10.0, 100.0),
        "penalty": ("l2",),
        "solver": ("lbfgs",),
        "max_iter": (5000,),
        "class_weight": (None,),
    },
}

FUTURE_CONTINUOUS_PRIMARY_METRIC = "Spearman rho"
FUTURE_CONTINUOUS_SECONDARY_METRICS = ("MAE", "RMSE", "R2")
FUTURE_CLASSIFICATION_PRIMARY_METRIC = "PR-AUC"
FUTURE_CLASSIFICATION_SECONDARY_METRICS = ("ROC-AUC",)
FUTURE_FINAL_TEST_CONTINUOUS_METRICS = ("Spearman rho", "MAE", "RMSE", "R2", "N")
FUTURE_FINAL_TEST_CLASSIFICATION_METRICS = (
    "PR-AUC",
    "ROC-AUC",
    "positive N",
    "negative N",
    "prevalence",
)

NO_MODEL_TRAINING_IN_PHASE_5A = True
NO_PERFORMANCE_METRICS_IN_PHASE_5A = True
NO_EMBEDDINGS_IN_PHASE_5A = True


def rule48_feature_names_from_manifest(path: Path | str = RULE48_FEATURE_MANIFEST) -> tuple[str, ...]:
    """Return the frozen rule columns present in the existing feature manifest."""

    import csv

    with Path(path).open("r", encoding="utf-8-sig", newline="") as handle:
        header = tuple(next(csv.reader(handle)))
    missing = [name for name in RULE48_FEATURES if name not in header]
    if missing:
        raise ValueError(f"Frozen RULE48 columns missing from feature manifest: {missing}")
    return tuple(name for name in RULE48_FEATURES if name in header)
