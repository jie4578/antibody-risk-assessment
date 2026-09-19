# Phase 5A — Protein ML Benchmark Preregistration

Phase 5A freezes the benchmark population, leakage-safe split, feature
blocks, and future model contract. It does not train models, create protein
embeddings, inspect predictive performance, or optimize any threshold.

## Frozen scientific boundary

- Frozen rule-based baseline: `d1487ed74bdfc52fb0b2015a25c4e91ee90af66d`.
- `core.py`, `scoring.py`, rule weights, risk thresholds, rule features, and
  experimental outcomes are not changed or used to tune this benchmark.
- Jain 2017 remains a separate historical benchmark. It is not mixed into the
  primary AIntibody training or model-selection population.
- AIntibody is the prospective held-out test partition from Phase 5A onward.
  It is not described here as an independent external validation cohort.

## Population and endpoints

The primary population is the exact 476 unique VH/VL sequence-hash rows frozen
by Phase 4D1A/4D1B. The 715 raw records and duplicate sequence records remain
traceable but are not silently reintroduced into the primary unit.

Primary experimental endpoints are Tm, Tagg, HIC, BVP, and AC-SINS, retaining
the source column names and missingness. The composite endpoint is
`total_developability_score <= 3` for developable and `> 3` for not
developable. The positive classification label is `NOT_DEVELOPABLE`. HIC is
not promoted to replace the other four assay tasks.

## Frozen feature blocks

1. `LENGTH_CONTROL`: exactly `VH_length`, `VL_length`.
2. `RULE48`: the exact 48 Phase 4B rule-feature columns in the existing frozen
   feature manifest. No features are selected using AIntibody outcomes.
3. `ESM2`: checkpoint `facebook/esm2_t30_150M_UR50D`, evaluated later only;
   strip BOS/EOS/padding, mean-pool VH and VL separately, then concatenate
   640-dimensional VH and VL vectors into 1280 dimensions.
4. `ESM2_PLUS_RULE48`: the frozen ESM2 block plus the exact RULE48 block.

No ESM2 or other embedding is generated in Phase 5A. No outcome-informed
embedding transformation is allowed, and VH/VL are never averaged together.

## Leakage-safe grouping and split

Records are connected into leakage components when they share an antibody ID,
or when global VH identity is at least 0.90, or global VL identity is at least
0.90. Pairwise alignment uses Biopython `PairwiseAligner` in global mode with
match 2, mismatch -1, gap-open -2, and gap-extend -1. Identity is exact
aligned-residue matches divided by alignment columns including gaps; the
measure is symmetric and self-identity is 1.0. Connected components, not
individual rows, are assigned to partitions.

The primary target is 60% train, 20% validation, and 20% test. Components are
sorted by descending size and then component ID. A component is greedily placed
in the partition with the greatest remaining row deficit; ties are resolved
TRAIN, VALIDATION, TEST. No assay value, endpoint, or outcome is read during
assignment. The 0.80 identity threshold is descriptive audit-only and cannot
redesign the split. No component is broken to improve class balance, and no
random seed search is performed. The audit reports component count, singleton
and multi-member counts, largest/median/P95 component sizes, and link reasons.

The split audit is performed only after assignment. It reports row N,
developable/not-developable/missing composite counts and prevalence, plus
available/missing N for each continuous endpoint. Fewer than 10 positive or
negative examples, fewer than 40 evaluable test observations for a continuous
endpoint, or a proportion deviation above five percentage points sets
`SPLIT_REVIEW_REQUIRED`; it does not trigger reshuffling.

## Test-label sealing

`test_features.csv` contains sequence identifiers, VH, VL, and non-outcome
metadata only. Test outcomes are written only to `sealed_test_labels.csv`,
with a SHA256 entry in `test_label_seal.json`. Future benchmark code must not
read this sealed label file before the explicitly authorized Phase 5D analysis
stage. Train and validation populations retain the preregistered endpoint
columns for future model fitting and selection. After Phase 5D, repeated
reuse of the test set for tuning is prohibited; later model changes make the
current test set a development dataset.

## Future model contract (not run in Phase 5A)

Only the following future models are preregistered: Ridge with alpha in
`[0.01, 0.1, 1, 10, 100]`; and L2 LogisticRegression with C in
`[0.01, 0.1, 1, 10, 100]`, solver `lbfgs`, `max_iter=5000`, and
`class_weight=None`. No XGBoost, random forest, neural network, broad
algorithm search, or post-hoc oxidation/HIC-only feature subset is allowed in
the primary benchmark.

For every feature block, preprocessing is fit on TRAIN only. The frozen
StandardScaler is applied unchanged to validation and test; no scaler is fit
on all 476 rows. ESM2 uses no PCA in the primary benchmark. For continuous
endpoints, validation selection uses Spearman rho as primary, with MAE, RMSE,
and R2 secondary; ties prefer larger Ridge alpha. For the composite
classification endpoint, validation selection uses PR-AUC as primary and
ROC-AUC as secondary; ties prefer smaller LogisticRegression C. Final test
reporting is one-time and endpoint-specific: continuous Spearman rho, MAE,
RMSE, R2, N; classification PR-AUC, ROC-AUC, positive N, negative N, and
prevalence. Test thresholds are never optimized, and no single global winner
is reported across unrelated assay types.

Phase 5B is feature/embedding extraction, Phase 5C is training and validation
model selection, and Phase 5D is the one-time frozen test evaluation. No
model, metric, embedding, or performance result is created in Phase 5A.

## Reproducibility and negative results

Generated split and seal artifacts are reproducible and ignored by Git. Raw
third-party data remain governed by the existing validation data policy.
Missing values remain missing, rows are not removed for model convenience, and
any later exclusion requires a documented data-quality reason. All later
statistics must report sample size N. Negative benchmark findings must be
preserved and reported. Jain remains a separate historical benchmark and is
not mixed into the AIntibody split or primary training population. The frozen
RULE48 block must remain intact: no post-hoc selection of oxidation features,
HIC-associated features, or Phase 4 significant features is permitted.
