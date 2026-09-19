"""Outcome-blind Phase 5A.1 amendment metadata.

The V1 specification remains in ``validation.ml_benchmark_spec``.  This file
records the separately versioned PAIRED_90 amendment without changing V1.
"""

from __future__ import annotations


AMENDMENT_ID = "ML_BENCHMARK_SPEC_V1_1"
PRIOR_SPEC = "ML_BENCHMARK_SPEC_V1"
PRIOR_POLICY = "SINGLE_CHAIN_OR_90"
NEW_POLICY = "PAIRED_90"
POPULATION = 476
THRESHOLD = 0.90
PAIRING_RULE = "same antibody_id OR (VH global identity >= 0.90 AND VL global identity >= 0.90)"
AMENDMENT_REASON = "single-chain OR connected-component percolation made the benchmark unsplittable"
TEST_SEALING_POLICY = "test_features without outcomes; sealed_test_labels.csv with SHA256"
TIMING_CONSTRAINT = "before ESM embedding extraction, ML training, hyperparameter selection, validation performance, and test performance"
