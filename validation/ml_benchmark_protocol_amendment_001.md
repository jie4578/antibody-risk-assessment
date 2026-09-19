# Phase 5A.1 — Similarity Graph Diagnostic and Policy Amendment 001

This amendment is frozen after the Phase 5A preregistration checkpoint
`f00d479328742a11116b74641db4eca8d510581d` and before any Phase 5B feature or
embedding extraction, ML training, hyperparameter selection, validation
performance, or test performance.

## Versioned policy record

- Original spec: `ML_BENCHMARK_SPEC_V1`
- Original policy: `SINGLE_CHAIN_OR_90`
- Original result: 1 connected component containing all 476 paired sequences;
  deterministic assignment produced 476 / 0 / 0 rows.
- Amended spec: `ML_BENCHMARK_SPEC_V1_1`
- New policy: `PAIRED_90`
- Amendment ID: `ML_BENCHMARK_SPEC_V1_1`
- Population: 476 unique paired VH/VL sequences
- Threshold: 0.90
- Pairing rule: same `antibody_id`, or both VH and VL global identity at least
  0.90. Connected components remain indivisible.
- Test sealing: `test_features.csv` contains no outcomes; test outcomes are
  stored separately in `sealed_test_labels.csv` with a SHA256 seal.

## Rationale

The future Protein LM representation is a paired VH/VL representation. Single-
chain similarity alone does not imply a near-duplicate paired antibody. The
original OR rule allowed transitive percolation through alternating VH-only and
VL-only links. `PAIRED_90` prevents that specific paired-sequence leakage while
retaining the paired-antibody analysis unit.

This amendment does not claim that single-chain family similarity disappears
across partitions. Residual VH/VL single-chain similarity is reported as a
secondary limitation and is not treated as primary paired leakage.

The amendment is outcome-blind. It does not inspect assay values, labels,
correlations, ROC-AUC, PR-AUC, Spearman, MAE, RMSE, R2, predictions,
estimators, or Protein LM embeddings. The historical V1 policy and its failed
split remain reproducible and are not overwritten.

If `PAIRED_90` itself produces one unusable giant component, the process stops
with `SPLIT_POLICY_REVIEW_REQUIRED`; no additional threshold is searched.

## Split and unlock policy

When `PAIRED_90` is usable, the existing deterministic whole-component
assignment is reused: components are ordered by size descending and component
ID ascending, then assigned by greatest remaining deficit toward 60% TRAIN,
20% VALIDATION, and 20% TEST, with TRAIN / VALIDATION / TEST tie-breaking.
Outcomes are audited only after assignment. Phase 5B may begin only after the
split-quality guard passes. Phase 5D is the first phase allowed to read the
sealed test labels.
