# Phase 4A validation data foundation

This directory is isolated from the product implementation. It provides
source inspection, provenance, deterministic normalization and audit reports
for the Jain et al. 2017 and AIntibody 2026 experimental datasets.

The frozen rule-based baseline is `d1487ed74bdfc52fb0b2015a25c4e91ee90af66d`.
No validation code changes `core.py`, `scoring.py`, Desktop behavior, or model
training. Raw experimental values are preserved as supplied by the source;
missing values remain missing, and duplicate records are not silently removed.

Run the source-independent tests with:

```text
python -m pytest validation/tests -q
```

Acquisition is intentionally separate from parsing. Jain files must be
obtained from the official PMC/PNAS supplementary links before its parser can
produce a normalized table. At the time of this foundation run those official
requests returned a download verification page, so no Jain HTML response is
treated as data.

The AIntibody parser targets official Nature Biotechnology Supplementary Data
1–3 (MOESM4) and keeps the source workbook's five sheets/columns available for
traceability. It does not run benchmark correlations, classification, ML
training, or score tuning.

## Phase 4B frozen rule features

Run `python -m validation.run_feature_extraction` after the Phase 4A processed
tables are available. The extractor analyzes VH and VL independently through
the production `core.analyze_sequence()` and `scoring.compute_risk_score()` APIs.
It writes ignored CSV outputs under `data/features/` and prediction-side audit
reports under `reports/data_audit/`.

`calculated_score` is the native production score, where a higher value means
fewer or lower rule penalties. `rule_penalty` is the validation-only derived
field `100 - calculated_score`. No paired antibody score is invented. Assay
values are not read for feature decisions, and repeated AIntibody sequence
records remain separate rows.

## Phase 5 frozen protein benchmark

The Phase 5D TEST evaluation was opened exactly once under the frozen
Phase 5C configuration. The aggregate scientific summary is tracked in
[`PHASE5_ML_BENCHMARK_SUMMARY.md`](PHASE5_ML_BENCHMARK_SUMMARY.md), with the
machine-readable counterpart in `phase5_frozen_summary.json` and the
immutability marker in `PHASE5_TEST_EVALUATED.md`. Raw labels, predictions,
embeddings, and generated benchmark tables remain excluded from Git.

## External HIC Validation — GDPa3

Phase 8C evaluated the frozen `hic_esm2_v1` predictions once against the
independent GDPa3 `hic_rt_avg` population. The frozen Phase 7C.1 sequence audit
reported **zero exact paired VH/VL overlaps** with Jain, AIntibody TRAIN,
VALIDATION, TEST, and ALL, or SAbDab2. This exact-sequence result does not imply
family-independent generalization.

The complete-case population was N=`79`. Paired-min sequence-identity
similarity to AIntibody TRAIN+VALIDATION was `<0.70`: 71, `0.70–<0.80`: 7,
`0.80–<0.90`: 1, and `>=0.90`: 0 (N=79). These are sequence-identity proxy
bins, not germline-family annotations.

The frozen model was `hic_esm2_v1` (`phase5-frozen-v1`), model artifact SHA256
`b6b05c0f5e45bf2b53ef5878bef8f248c3a7ce50ee7b78e5f8cd09044ca309b4`. The
Phase 8B prediction seal SHA256 was
`9ffecbb2621b9760494f72ae94cb04a002a317cc75524785fc5a5efef645193f`; the
sealed sequence snapshot SHA256 was
`5c41700df82dce43b8d379afbf054228818bf868f0ae4b89fa9270e8d1daf3e7`.
The Phase 8B seal commit was `025f3d44c87a614e47a681713d32707b47e92b6e`;
the frozen Phase 8C evaluator commit was
`9caa5a101d679251a29225e69a0ff187b39b6d0a`.

Observed results:

- Primary Spearman rho `0.231901`, N=`79`.
- 95% bootstrap CI `[0.005418, 0.437591]` (2,000 valid, 0 degenerate).
- Secondary Pearson r `0.187175`, N=`79`; Kendall tau-b `0.153571`, N=`79`.
- Frozen result JSON SHA256:
  `31c2b92ca855531f11cef45ec0e7c2703c0ba3b6750474604242041499c8c181`.

A weak positive external HIC rank association was observed. It is weak relative
to the internal AIntibody HIC result (rho `0.834662`, N=`72`); that point
comparison is descriptive only, and no statistical comparison was performed.
The lower confidence bound is close to zero and uncertainty remains
substantial. This was a cross-source / cross-protocol evaluation; assay
equivalence is unconfirmed. It does not establish family-independent
generalization, global developability prediction, clinical utility, or
mutation-effect prediction.

GDPa3 HIC is **OBSERVED AFTER PHASE 8C**. It must not be described as untouched,
unseen, or a prospective holdout for future models; any future evaluation is
post-hoc reuse of an observed external dataset. No model training, tuning,
recalibration, or additional endpoint analysis was performed. See the
[human-readable result](external_developability/PHASE8C_HIC_EXTERNAL_VALIDATION_RESULT.md)
and [observed-status marker](external_developability/PHASE8_GDPA3_HIC_OBSERVED.md).

The evidence hierarchy remains dataset-specific: Jain 2017 rule-feature
retrospective evidence; AIntibody internal entity-controlled ML benchmark;
SAbDab2 external sequence-diversity audit; and GDPa3 one-time external HIC
evaluation. These layers must not be collapsed into a single validation score.
