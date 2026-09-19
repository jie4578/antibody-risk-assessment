# Phase 5A.2 protocol amendment: internal ENTITY_EXACT_V1 benchmark

## Timing and frozen baseline

The rule-based scientific baseline remains frozen at
`d1487ed74bdfc52fb0b2015a25c4e91ee90af66d`. This amendment was made after
the Phase 5A.1 structural diagnostic and before ESM embedding extraction,
estimator fitting, validation performance, or test performance. No ML result
influenced the redesign.

## Why the benchmark changed

The original V1 policy, `SINGLE_CHAIN_OR_90`, produced one connected
476-row component. The V1.1 `PAIRED_90` policy also produced one connected
476-row component, and the 0.98 paired diagnostic remained dominated by a
444-row component. A strict family-separated 60/20/20 benchmark was therefore
not feasible on this AIntibody population.

Strict family-level generalization is **DEFERRED** and requires a future,
more sequence-diverse external dataset. No additional similarity threshold
search is performed in this amendment.

## New benchmark

`AINTIBODY_INTERNAL_ENTITY_EXACT_V1` is an internal duplicate/entity-
controlled held-out benchmark over the frozen 476 paired VH/VL rows.

`ENTITY_EXACT_V1` connects rows only when they have the same non-empty
`antibody_id`, or when both normalized VH and VL sequences are exactly equal.
The connected components are indivisible. Exact paired identity uses direct
normalized sequence equality for canonical gap-free sequences; it is not a
tunable similarity threshold.

Components are allocated deterministically at 60% TRAIN, 20% VALIDATION,
and 20% TEST using the frozen greedy deficit algorithm. The split manifest is
written before outcomes are loaded. No class balance, endpoint distribution,
or model performance is used for allocation.

## Claims

Allowed claim: internal held-out generalization within the AIntibody sequence
landscape while controlling exact paired-sequence duplicates and antibody
entity overlap.

Prohibited claims: family-independent generalization, strict
sequence-generalization, or independent external ML validation. Residual
single-chain and paired sequence similarity between partitions is audited and
reported descriptively; it does not change the split.

## Future phase firewall

Phase 5B may extract features and ESM2 embeddings only. Phase 5C may fit
TRAIN models and select hyperparameters using VALIDATION. Phase 5D alone may
read `sealed_test_labels.csv` for one-time test evaluation. No Phase 5B or
5C code may load the sealed test labels.

No model, embedding, prediction, correlation, classification metric, or other
performance result is produced in Phase 5A.2.
