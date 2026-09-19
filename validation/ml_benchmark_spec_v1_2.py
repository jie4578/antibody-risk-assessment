"""Frozen Phase 5A.2 internal benchmark specification.

This module is a protocol contract only.  It does not read outcomes, fit
estimators, generate embeddings, or calculate predictive performance.
"""

from __future__ import annotations

from validation.ml_benchmark_spec import (
    CONTROL_FEATURES,
    FUTURE_MODELS,
    RULE48_FEATURES,
    ESM2_CHECKPOINT,
)


SPEC_VERSION = "ML_BENCHMARK_SPEC_V1_2"
BENCHMARK_NAME = "AINTIBODY_INTERNAL_ENTITY_EXACT_V1"
BENCHMARK_TYPE = "internal duplicate/entity-controlled held-out benchmark"
POPULATION = 476
GROUPING_POLICY = "ENTITY_EXACT_V1"
SPLIT_ALGORITHM = (
    "whole-component deterministic greedy allocation at 60/20/20; "
    "component size descending then component_id ascending; "
    "TRAIN, VALIDATION, TEST tie-break"
)
FEATURE_BLOCKS = {
    "LENGTH_CONTROL": CONTROL_FEATURES,
    "RULE48": RULE48_FEATURES,
    "ESM2": (ESM2_CHECKPOINT, "separate VH/VL mean pooling; 640 + 640 dimensions"),
    "ESM2_PLUS_RULE48": (ESM2_CHECKPOINT, RULE48_FEATURES),
}
MODEL_FAMILIES = ("Ridge Regression", "L2 Logistic Regression")
HYPERPARAMETER_GRIDS = FUTURE_MODELS
VALIDATION_METRICS = {"continuous": "Spearman rho", "classification": "PR-AUC"}
TEST_METRICS = ("Spearman rho", "MAE", "RMSE", "R2", "ROC-AUC", "PR-AUC", "N")
TEST_SEAL_POLICY = "sealed_test_labels.csv is accessible only to the one-time Phase 5D evaluation"
STRICT_GENERALIZATION_STATUS = "DEFERRED"
ALLOWED_CLAIMS = (
    "internal held-out generalization within the AIntibody sequence landscape",
    "duplicate/entity-controlled held-out benchmark",
)
PROHIBITED_CLAIMS = (
    "family-independent generalization",
    "strict sequence-generalization benchmark",
    "independent external ML validation",
)
PRIMARY_SPLIT_TARGETS = {"TRAIN": 0.60, "VALIDATION": 0.20, "TEST": 0.20}
NO_OUTCOME_BASED_SPLIT = True
NO_THRESHOLD_SEARCH = True
NO_MODEL_TRAINING_IN_PHASE_5A_2 = True
NO_EMBEDDINGS_IN_PHASE_5A_2 = True
NO_PERFORMANCE_IN_PHASE_5A_2 = True
