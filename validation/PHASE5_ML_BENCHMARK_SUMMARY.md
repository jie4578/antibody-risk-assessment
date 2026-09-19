# Phase 5 Frozen Protein ML Benchmark Summary

Status: **frozen after the one-time Phase 5D TEST evaluation**.

Benchmark: `AINTIBODY_INTERNAL_ENTITY_EXACT_V1`
Phase 5C checkpoint: `83ec67429640fcdeb142f6dc52711a51a834eda1`
TEST evaluation number: `1`
TEST-label SHA256: `36e802f6c3d615b5f636bb1186c03e24421b2e3b004f0e7e249ace4b3673fca3`

No Phase 5D model was rerun to produce this document. The summary reads only
the existing aggregate result files under
`validation/data/ml_benchmark/entity_exact_v1/final_test/`.

## Frozen design

- Train + validation population: N=381.
- TEST population: N=95.
- Composite TEST labels: 63 developable and 32 not-developable; positive prevalence = 0.336842.
- Continuous models: `StandardScaler + Ridge`.
- Classification models: `StandardScaler + LogisticRegression`.
- Feature blocks: LENGTH_CONTROL (2), RULE48 (48), ESM2 (1280), and ESM2_PLUS_RULE48 (1328).
- Scaling and fitting used TRAIN+VALIDATION only; the Phase 5C-selected hyperparameters were used unchanged.
- Bootstrap confidence intervals use 2,000 resamples, seed `20260919`.
- No TEST filtering, threshold optimization, feature selection, PCA, ESM fine-tuning, or TEST-driven retraining occurred.

Spearman rho measures ranking or monotonic association. R² measures absolute
predictive fit. A positive Spearman value can coexist with poor or negative R²;
such a model is not an accurate quantitative predictor.

## All continuous TEST results

The table preserves weak and negative results and does not define a global
winner. Spearman confidence intervals are the frozen 95% bootstrap intervals;
MAE/RMSE bootstrap intervals are preserved in
`bootstrap_confidence_intervals.csv`.

| Endpoint | Representation | alpha | Validation rho | TEST rho [95% CI] | TEST MAE | TEST RMSE | TEST R² | N |
|---|---|---:|---:|---:|---:|---:|---:|---:|
| Tm | LENGTH_CONTROL | 100 | 0.150888 | 0.117613 [-0.071751, 0.301707] | 0.852837 | 1.145986 | -0.056911 | 94 |
| Tm | RULE48 | 0.1 | 0.039728 | 0.244933 [0.045585, 0.418246] | 0.877207 | 1.152965 | -0.069822 | 94 |
| Tm | ESM2 | 100 | 0.020447 | 0.127551 [-0.095695, 0.332891] | 2.647115 | 3.732091 | -10.209445 | 94 |
| Tm | ESM2_PLUS_RULE48 | 100 | 0.031604 | 0.135091 [-0.094564, 0.334116] | 2.643806 | 3.786001 | -10.535622 | 94 |
| Tagg | LENGTH_CONTROL | 100 | -0.316285 | -0.057565 [-0.224802, 0.127093] | 3.216645 | 3.978633 | -0.053096 | 94 |
| Tagg | RULE48 | 1 | 0.405679 | 0.069668 [-0.131552, 0.266099] | 3.428468 | 4.359912 | -0.264607 | 94 |
| Tagg | ESM2 | 100 | 0.278494 | 0.366791 [0.179064, 0.528861] | 3.714556 | 5.293676 | -0.864297 | 94 |
| Tagg | ESM2_PLUS_RULE48 | 100 | 0.287610 | 0.348274 [0.156951, 0.521854] | 3.766756 | 5.453623 | -0.978657 | 94 |
| HIC | LENGTH_CONTROL | 100 | 0.443645 | 0.362798 [0.116826, 0.556373] | 1.550799 | 1.861829 | 0.110871 | 72 |
| HIC | RULE48 | 10 | 0.533278 | 0.659968 [0.491683, 0.776396] | 1.254689 | 1.496536 | 0.425541 | 72 |
| HIC | ESM2 | 100 | 0.760337 | 0.834662 [0.722527, 0.906847] | 0.870609 | 1.207785 | 0.625834 | 72 |
| HIC | ESM2_PLUS_RULE48 | 100 | 0.757280 | 0.830174 [0.717525, 0.903296] | 0.899422 | 1.245837 | 0.601886 | 72 |
| BVP | LENGTH_CONTROL | 100 | 0.062582 | 0.053548 [-0.150177, 0.246295] | 5.538145 | 8.462512 | -0.042059 | 95 |
| BVP | RULE48 | 100 | -0.038072 | 0.162207 [-0.035707, 0.354570] | 5.464058 | 8.491952 | -0.049321 | 95 |
| BVP | ESM2 | 10 | 0.233032 | 0.270620 [0.064524, 0.461739] | 7.001433 | 10.156202 | -0.500915 | 95 |
| BVP | ESM2_PLUS_RULE48 | 1 | 0.204810 | 0.250197 [0.039586, 0.442253] | 9.550002 | 14.464931 | -2.044572 | 95 |
| AC-SINS | LENGTH_CONTROL | 100 | 0.098686 | 0.111757 [-0.085730, 0.317665] | 3.147747 | 4.671001 | -0.090310 | 95 |
| AC-SINS | RULE48 | 100 | 0.146676 | 0.357054 [0.145907, 0.532281] | 2.964736 | 4.478901 | -0.002473 | 95 |
| AC-SINS | ESM2 | 100 | 0.438703 | 0.660179 [0.520894, 0.767434] | 2.747269 | 3.743516 | 0.299692 | 95 |
| AC-SINS | ESM2_PLUS_RULE48 | 100 | 0.424509 | 0.663163 [0.524656, 0.771265] | 2.773788 | 3.761133 | 0.293085 | 95 |

## All classification TEST results

The positive class is the frozen not-developable class. No threshold metrics
were calculated.

| Representation | C | Validation PR-AUC | TEST PR-AUC [95% CI] | Validation ROC-AUC | TEST ROC-AUC [95% CI] | Prevalence | N |
|---|---:|---:|---:|---:|---:|---:|---:|
| LENGTH_CONTROL | 0.01 | 0.277958 | 0.343673 [0.300698, 0.410390] | 0.601658 | 0.466518 [0.361837, 0.583085] | 0.336842 | 95 |
| RULE48 | 10 | 0.487867 | 0.378145 [0.312574, 0.516065] | 0.778870 | 0.546627 [0.420350, 0.672892] | 0.336842 | 95 |
| ESM2 | 1 | 0.388959 | 0.611665 [0.492823, 0.737419] | 0.720516 | 0.691468 [0.578361, 0.792212] | 0.336842 | 95 |
| ESM2_PLUS_RULE48 | 10 | 0.417350 | 0.597708 [0.479016, 0.725064] | 0.715602 | 0.682044 [0.570933, 0.786235] | 0.336842 | 95 |

## Validation-to-TEST stability

| Endpoint/task | Representation | Validation metric | TEST metric | Delta |
|---|---|---:|---:|---:|
| Tm | LENGTH_CONTROL | 0.150888 | 0.117613 | -0.033275 |
| Tm | RULE48 | 0.039728 | 0.244933 | +0.205205 |
| Tm | ESM2 | 0.020447 | 0.127551 | +0.107104 |
| Tm | ESM2_PLUS_RULE48 | 0.031604 | 0.135091 | +0.103487 |
| Tagg | LENGTH_CONTROL | -0.316285 | -0.057565 | +0.258720 |
| Tagg | RULE48 | 0.405679 | 0.069668 | -0.336011 |
| Tagg | ESM2 | 0.278494 | 0.366791 | +0.088297 |
| Tagg | ESM2_PLUS_RULE48 | 0.287610 | 0.348274 | +0.060664 |
| HIC | LENGTH_CONTROL | 0.443645 | 0.362798 | -0.080846 |
| HIC | RULE48 | 0.533278 | 0.659968 | +0.126690 |
| HIC | ESM2 | 0.760337 | 0.834662 | +0.074325 |
| HIC | ESM2_PLUS_RULE48 | 0.757280 | 0.830174 | +0.072894 |
| BVP | LENGTH_CONTROL | 0.062582 | 0.053548 | -0.009033 |
| BVP | RULE48 | -0.038072 | 0.162207 | +0.200278 |
| BVP | ESM2 | 0.233032 | 0.270620 | +0.037588 |
| BVP | ESM2_PLUS_RULE48 | 0.204810 | 0.250197 | +0.045387 |
| AC-SINS | LENGTH_CONTROL | 0.098686 | 0.111757 | +0.013071 |
| AC-SINS | RULE48 | 0.146676 | 0.357054 | +0.210378 |
| AC-SINS | ESM2 | 0.438703 | 0.660179 | +0.221476 |
| AC-SINS | ESM2_PLUS_RULE48 | 0.424509 | 0.663163 | +0.238653 |
| Composite PR-AUC | LENGTH_CONTROL | 0.277958 | 0.343673 | +0.065715 |
| Composite PR-AUC | RULE48 | 0.487867 | 0.378145 | -0.109722 |
| Composite PR-AUC | ESM2 | 0.388959 | 0.611665 | +0.222707 |
| Composite PR-AUC | ESM2_PLUS_RULE48 | 0.417350 | 0.597708 | +0.180357 |

HIC ESM2 strengthened slightly from validation rho 0.760337 to TEST rho
0.834662. Tagg RULE48 attenuated from 0.405679 to 0.069668 and did not
replicate its validation signal. RULE48 classification also attenuated from
PR-AUC 0.487867 / ROC-AUC 0.778870 to 0.378145 / 0.546627. ESM2 improved
TEST PR-AUC, while the combined classifier did not exceed ESM2 alone.

## Endpoint-level interpretation

- **Tm:** weak ranking signal across representations; negative or near-zero R² means no reliable quantitative calibration is demonstrated.
- **Tagg:** ESM2 provides a moderate internal ranking signal, while RULE48 validation performance is unstable on TEST; absolute fit remains poor.
- **HIC:** strongest internal held-out signal. ESM2 and RULE48 both retain substantial association, with ESM2 TEST rho 0.834662 and R² 0.625834 at N=72.
- **BVP:** weak-to-moderate ranking associations but negative R² across all representations; not a reliable quantitative predictor here.
- **AC-SINS:** ESM2 and the combined representation show moderate internal ranking signal and positive R²; RULE48 alone is weaker. The combined result is only marginally above ESM2 in rho and does not establish consistent incremental value.

## Representation conclusions

- **LENGTH_CONTROL:** remains competitive for some weak endpoints, but does not explain the strongest HIC or AC-SINS signal.
- **RULE48:** retains useful assay-specific signal, especially for HIC; its composite classification result does not robustly replicate.
- **ESM2:** shows stronger held-out signal for HIC and AC-SINS and the strongest composite classification TEST results.
- **ESM2_PLUS_RULE48:** does not consistently add value beyond ESM2. It is slightly higher for AC-SINS rho but slightly lower for HIC and composite classification.

## Novelty limitation

The TEST set is not distant from TRAIN:

- paired-min ≥0.90: 84/95 = 88.4211%
- paired-min ≥0.95: 49/95
- paired-min ≥0.98: 21/95
- novelty bins: 0.80–<0.90 = 11, 0.90–<0.95 = 35, 0.95–<1.00 = 49, <0.80 = 0

Therefore Phase 5 does **not** test generalization to distant antibody
families. Novelty-stratified results are descriptive only and were not used
for selection.

## Phase 4 to Phase 5 scientific story

Phase 4C Jain showed broadly weak or null frozen-rule associations across a
broad set of developability assays. Phase 4D AIntibody then showed specific
oxidation/HIC signals, which persisted after controlling for VH length in
Phase 4D2. Phase 5 shows that Protein LM representations capture stronger HIC
signal and meaningful internal composite discrimination. These results do
not invalidate the earlier negative findings; they show assay- and
dataset-dependent predictive structure.

## Supported claims

- ESM2 representations capture experimentally relevant sequence signal for selected developability assays within the AIntibody sequence landscape.
- HIC shows particularly strong held-out association.
- Frozen rule features retain meaningful assay-specific signal, particularly for HIC.
- Protein LM representations outperform simple handcrafted rules on some endpoints but not uniformly.
- Internal composite classification benefits from ESM2 representation.

## Not supported

This benchmark does not support claims of:

- universal antibody developability prediction;
- family-independent generalization;
- clinical utility;
- causal interpretation;
- replacement of wet-lab assays;
- therapeutic efficacy prediction;
- affinity prediction from this benchmark;
- automatic best-antibody selection; or
- a validated production-grade predictor.

## Test-evaluation immutability and future policy

The TEST set was opened exactly once. It is now observed development evidence
and must not be presented as an untouched final test again. Any future Phase
6+ improvement informed by these results requires a new sequence-diverse
external dataset or a genuinely new prospective experimental cohort for
strong validation.

Raw TEST predictions, embeddings, labels, and third-party datasets are not
part of this tracked summary. Aggregate machine-readable results are stored
in `validation/phase5_frozen_summary.json`.
