# Phase 8C — GDPa3 External HIC Evaluation

**Status:** `OBSERVED_ONE_TIME_EXTERNAL_EVALUATION`

**Result JSON SHA256:** `31c2b92ca855531f11cef45ec0e7c2703c0ba3b6750474604242041499c8c181`

## 1. Objective

Evaluate once the sealed `hic_esm2_v1` predictions against the preregistered GDPa3 `hic_rt_avg` endpoint. GDPa3 HIC is now observed and is not an untouched dataset for future model development.

## 2. Frozen protocol

The Phase 8A protocol and Phase 8B prediction seal were frozen before label reveal. Phase 8C evaluator code commit: `9caa5a101d679251a29225e69a0ff187b39b6d0a`. Primary statistic: Spearman rho; bootstrap: 2,000 resamples, NumPy `default_rng`/PCG64, seed 20260926, percentile 95% interval. Secondary statistics: Pearson r and Kendall tau-b. Absolute-error metrics were omitted as preregistered.

## 3. Dataset independence

The frozen Phase 7C.1 sequence audit reported no exact paired-sequence overlap with Jain, AIntibody TRAIN/VALIDATION/TEST/ALL, or SAbDab2. Similarity figures are sequence-identity proxies, not germline-family annotations. This does not establish family-independent generalization.

## 4. Prediction seal verification

Prediction SHA256 `9ffecbb2621b9760494f72ae94cb04a002a317cc75524785fc5a5efef645193f`; sequence snapshot SHA256 `5c41700df82dce43b8d379afbf054228818bf868f0ae4b89fa9270e8d1daf3e7`; model artifact SHA256 `b6b05c0f5e45bf2b53ef5878bef8f248c3a7ce50ee7b78e5f8cd09044ca309b4`. The sealed artifact contained N=79 rows. Phase 8B code commit: `025f3d44c87a614e47a681713d32707b47e92b6e`.

## 5. Label reveal / join integrity

The only experimental endpoint read was `hic_rt_avg`. Raw workbook SHA256: `06daa55cb609278574d008c5509d90a63f9a8f1aa3949f34fc50a2e654b008f7`. Predictions and labels were joined on both antibody ID and paired sequence hash: 79/79 matched, prediction-only=0, label-only=0, hash mismatches=0.

## 6. Primary external result

Spearman rho = 0.231901, N=79. No success threshold was applied.

## 7. Bootstrap uncertainty

95% percentile CI = `[0.0054175577212944165, 0.4375911455240819]`; valid replicates=2000, degenerate replicates=0, total=2,000.

## 8. Secondary metrics

Pearson r = 0.187175, N=79. Kendall tau-b = 0.153571, N=79. Neither replaces the primary endpoint.

## 9. Sequence novelty context

Frozen paired-min identity bins versus AIntibody TRAIN+VALIDATION, descriptive only (N=79): `<0.70` = 71; `0.70–<0.80` = 7; `0.80–<0.90` = 1; `>=0.90` = 0. No subgroup correlations were calculated.

## 10. Cross-source / cross-protocol limitation

This is cross-source, cross-protocol HIC evaluation. GDPa3 assay conditions are not sufficiently specified to establish same-protocol or assay-equivalent replication.

## 11. Interpretation

A positive external HIC rank association was observed. The 95% percentile interval does not span zero; no success threshold was preregistered. The point estimate is numerically lower than the frozen internal AIntibody estimate (rho=0.834662, N=72); this is descriptive only, and the datasets/protocols differ. No statistical test comparing the correlations was run.

## 12. Scientific limitations

The sample is N=79 from one external source and one endpoint. Similarity bins are not immunoglobulin family labels. Assay protocol shift and measurement-scale differences remain unresolved.

## 13. What this result does NOT establish

It does not establish family-independent or universal antibody generalization, clinical utility, causality, mutation-effect prediction, global developability prediction, or same-protocol replication. It is not a product claim or a wet-lab replacement.

## 14. Future work

GDPa3 HIC is permanently marked OBSERVED for future development. Any further analysis requires a separately authorized, explicitly post-hoc protocol. No model or product claims were changed here.
