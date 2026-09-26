# Phase 8 — GDPa3 HIC External Validation Protocol

**Status: FROZEN BEFORE PREDICTION**
Freeze date: 2026-09-26
Pre-freeze repository base: `a66a4eb3d425067456c6c3a6ea3f3a35b02f0c21`

This preregistration authorizes a later, separate Phase 8B prediction-only
run and a one-time Phase 8C evaluation. It does not authorize either action
in Phase 8A. No GDPa3 prediction or performance result has been generated.

## 1. Scientific boundary

The product scientific baseline remains v4.0.0 and is not modified by this
validation work. Do not change `core.py`, `scoring.py`, production ML
inference, model parameters, ESM2 preprocessing, or any risk threshold. Do not
train, tune, recalibrate, refit, select features, fit a threshold, or access
AIntibody TEST labels. Do not evaluate another GDPa3 endpoint or the frozen
developability classifier. GDPa3 HIC values are not evidence for causal,
clinical, universal, or family-independent prediction claims.

## 2. Dataset provenance and frozen population

- Dataset: GDPa3, 80 IgG records from the Observed Antibody Space.
- Publisher source: [Ginkgo Datapoints GDPa3 dataset listing](https://datapoints.ginkgo.bio/functional-genomics/gdpx2)
  and [2025 Antibody Developability Competition page](https://datapoints.ginkgo.bio/ai-competitions/2025-abdev-competition).
- Local source filename: `GDPa3_20260106_full.xlsx`.
- Raw file size: 112,571 bytes.
- Raw file SHA256: `06daa55cb609278574d008c5509d90a63f9a8f1aa3949f34fc50a2e654b008f7`.
- The workbook was supplied locally as the official workbook and was not
  downloaded or modified during this phase. Its origin is not cryptographically
  authenticated. File-specific redistribution terms are not verified. Keep
  the raw workbook ignored and out of Git.
- The workbook has 80 sequence records, all 80 with valid paired VH/VL, and
  80 unique VH, VL, and paired sequence hashes. Exact paired-sequence overlap
  with Jain, AIntibody TRAIN, VALIDATION, TEST, ALL, and SAbDab2 is zero.
- GDPa3 versus the 381 unique AIntibody TRAIN+VALIDATION pairs had nearest
  paired-min identity median 0.531 and maximum 0.829 (N=80 GDPa3 sequences).
  Identity-proxy connected components were 45 at 0.70, 78 at 0.80, and 80 at
  0.90 (N=80). These are sequence-identity clusters, not germline families.

The primary population consists of records with both project-valid chains and
a nonmissing value in the preregistered HIC aggregate field. This uses assay
availability only to define complete cases; no HIC magnitude, ranking,
prediction, or model error is used to select a record. The fixed expected
population is N=79 from 80 source records. The single HIC-missing record stays
excluded from the inference snapshot; no assay value is imputed. There is no
workbook-defined disqualifying QC status field in the audited data-sheet
headers. Do not infer QC exclusions from replicate counts, standard
deviations, sequence properties, or assay magnitudes.

## 3. Exact HIC target

- Workbook: `GDPa3_20260106_full.xlsx`.
- Worksheet: `Assay Data - average`.
- Exact column: `hic_rt_avg`.
- Underlying source endpoint: `hic_rt`.
- Unit: minutes, as stated by the workbook `Definitions` entry for `hic_rt`.
- Aggregate definition: use the workbook-supplied `*_avg` field as-is. Do not
  recompute, re-average, rescale, impute, transform, or substitute another
  field. The workbook does not document a more detailed averaging formula.
- Availability: 79 nonmissing of 80 records (N=80 source records); evaluation
  N=79.

The independent assay conditions for GDPa3 are not fully specified in the
workbook. Column, buffers, gradient, instrument, and detailed run conditions
have not been established. AIntibody's target is HIC retention time in a
gradient, in minutes. This protocol therefore concerns **CROSS-SOURCE /
CROSS-PROTOCOL** HIC validation only. It is not same-protocol replication,
assay-equivalent replication, or clinical validation. This limitation must
appear with every Phase 8C result and interpretation.

## 4. Frozen model and representation

- Model ID: `hic_esm2_v1`.
- Model version: `phase5-frozen-v1`.
- Estimator: Ridge, alpha=100.0; feature dimension=1280.
- Model artifact: `artifacts/ml_models/hic_esm2_v1.joblib`.
- Model artifact SHA256: `b6b05c0f5e45bf2b53ef5878bef8f248c3a7ce50ee7b78e5f8cd09044ca309b4`.
- Training population: frozen AIntibody TRAIN+VALIDATION only; 355 training
  rows. AIntibody TEST rows used in training: 0.
- Representation: `facebook/esm2_t30_150M_UR50D`, immutable revision
  `a695f6045e2e32885fa60af20c13cb35398ce30c`, frozen paired VH/VL
  1280-dimensional representation, using the v4.0.0 inference preprocessing.
- No fine-tuning, model selection, refit, recalibration, intercept correction,
  or GDPa3-label-based scaling is allowed.

The local model file must match the SHA256 above at Phase 8B. If it does not,
stop without prediction. Do not commit the model binary.

## 5. Sequence-only inference snapshot and label firewall

The frozen inference population is stored locally at:
`validation/data/external_developability/gdpa3_phase8a/gdpa3_hic_sequence_snapshot.csv`.

- Rows: 79.
- Columns, in exact order: `antibody_id`, `VH`, `VL`, `VH_hash`, `VL_hash`,
  `paired_hash`.
- Snapshot SHA256:
  `5c41700df82dce43b8d379afbf054228818bf868f0ae4b89fa9270e8d1daf3e7`.
- The snapshot is generated, ignored by Git, and contains no experimental
  assay values, QC measurements, or labels. Raw workbook remains immutable.
- For Phase 8B, prediction code may read only this snapshot and the frozen
  `hic_esm2_v1` model artifact plus its frozen ESM2 runtime/cache. It must not
  open the GDPa3 assay workbook or any label-bearing processed table.
- The prediction artifact may contain only `antibody_id`, `paired_hash`,
  `hic_prediction`, `model_version`, and deterministic inference metadata.
  It must not contain VH/VL or experimental data.

This is a **prediction-first seal**: after the prediction artifact is written,
calculate and record its SHA256
before any label join. The seal record must include the prediction-artifact
SHA256, sequence-snapshot SHA256, model-artifact SHA256, ESM2 revision, Phase
8B code commit, timestamp, and row count. Do not modify the artifact after
sealing. Any join mismatch in Phase 8C is a stop condition; do not manually
patch records.

## 6. Preregistered analysis

### Primary metric

The sole primary statistic is Spearman rank correlation (rho) between frozen
`hic_esm2_v1` predictions and GDPa3 `hic_rt_avg`, joined by the preserved
`antibody_id` and verified paired hash. Primary complete-case N is 79. Report
the observed estimate and uncertainty; do not define a success threshold or
make a causal claim.

### Primary uncertainty interval

- Bootstrap resamples: 2,000.
- Seed: `20260926`, using NumPy `default_rng` (PCG64) and the frozen row order
  in the sequence snapshot.
- Each resample draws N=79 paired rows with replacement.
- If a resample has a constant prediction or target vector and Spearman rho
  is undefined, count it as degenerate and omit only that replicate from the
  percentile calculation. Do not redraw it or change the resampling count.
- Report the number of valid and degenerate replicates. Calculate the
  two-sided percentile 95% interval from all valid replicates; if none are
  valid, report the interval as not estimable. Do not choose a different CI
  method after seeing results.

### Secondary and descriptive analyses

- Secondary point estimates: Pearson correlation and Kendall tau-b, each
  reported with its complete-case N. They do not replace or redefine the
  primary metric.
- Absolute-error metrics (MAE, RMSE, R-squared): **OMITTED** because protocol
  equivalence and absolute-scale calibration have not been established.
- Frozen paired-min similarity strata against AIntibody TRAIN+VALIDATION:
  `<0.70`, `0.70–<0.80`, `0.80–<0.90`, and `>=0.90`. Report per-bin counts
  descriptively only. Do not calculate subgroup correlations, merge bins,
  or optimize boundaries. Report empty/sparse bins as such.
- Before prediction, the 79-row frozen snapshot was compared using sequence
  fields only against the 381 unique AIntibody TRAIN+VALIDATION pairs. The
  frozen bins are `<0.70`: 71, `0.70–<0.80`: 7, `0.80–<0.90`: 1, and
  `>=0.90`: 0 (total N=79). Maximum nearest paired-min identity is 0.8293
  (N=79). These are identity-proxy counts, not family annotations. No
  outcome-based strata or bin changes are permitted.
- No rho/metric threshold defines success or failure.

## 7. Explicit exclusions and interpretation limits

- `developability_esm2_v1` is not evaluated: GDPa3 does not have the identical
  AIntibody composite endpoint. Do not synthesize a composite label.
- No GDPa3 model is trained for other endpoints, and no relationship between
  the frozen HIC model and PR-CHO, AC-SINS, Tm2, titer, SEC, or any other assay
  is calculated.
- No AIntibody TEST labels or outcome fields are read for Phase 8A, 8B, or 8C.
- No prediction-based filtering, error-based exclusions, threshold fitting,
  direction flipping, calibration, feature selection, or post-hoc population
  changes are allowed.
- Preserve null, weak, unstable, or negative findings. Every reported
  statistic must include its sample size N.
- Permitted future wording is limited to descriptive external HIC association
  under cross-source/protocol shift. Do not claim family-independent,
  universal, clinical, mutation-effect, or global developability prediction.
- After the one-time Phase 8C evaluation, GDPa3 HIC is observed and may not be
  described as an untouched or unseen test set for future model development.

## 8. Phase gates

Phase 8A freezes this protocol and the sequence-only population only. Phase 8B
requires a separate authorized prediction run and immutable prediction seal.
Phase 8C may reveal and join HIC labels only after that seal. No predictions,
correlations, performance metrics, label-based decisions, model training, or
tuning were performed in Phase 8A.
