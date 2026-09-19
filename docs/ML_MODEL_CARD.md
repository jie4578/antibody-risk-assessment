# Phase 6A Frozen ML Model Card

## Purpose

Phase 6A provides local research decision support using two frozen models from
the Phase 5 benchmark. It is not a clinical predictor, validated production
predictor, family-independent antibody predictor, or wet-lab replacement.

## Supported tasks

1. `hic_esm2_v1`: a HIC model estimate.
2. `developability_esm2_v1`: a numeric probability for the frozen positive
   class `NOT_DEVELOPABLE`.

Tm, Tagg, BVP, and AC-SINS are intentionally not exposed by the Phase 6A
runtime.

## Model architecture

Both tasks use paired VH/VL ESM2 embeddings with VH first and VL second:

- model: `facebook/esm2_t30_150M_UR50D`;
- immutable revision: `a695f6045e2e32885fa60af20c13cb35398ce30c`;
- final hidden-state mean residue pooling with special and padding tokens excluded;
- 640 VH dimensions + 640 VL dimensions = 1280 dimensions;
- `StandardScaler` followed by the frozen Phase 5 estimator;
- HIC: Ridge with the Phase 5-selected alpha;
- composite: L2 LogisticRegression with the Phase 5-selected C.

Models are built from TRAIN+VALIDATION only. The Phase 5 TEST rows are never
used for model fitting.

## Benchmark evidence

The frozen Phase 5 TEST evidence is internal to the AIntibody sequence
landscape:

- HIC ESM2: Spearman `0.834662`, R² `0.625834`, N=72;
- composite ESM2: PR-AUC `0.611665`, ROC-AUC `0.691468`, prevalence `0.336842`, N=95.

These values are benchmark evidence, not expected accuracy on new antibody
families.

## Known limitations

The benchmark is entity-controlled but not family-independent. 84/95 TEST
rows had paired-min identity >=0.90 to TRAIN. Therefore family-independent
performance is unknown. Missing experimental measurements also produce
endpoint-specific sample sizes.

Spearman measures ranking association; R² measures absolute predictive fit.
A positive ranking signal does not imply accurate quantitative prediction.
Experimental verification remains required.

## Input requirements

Both VH and VL must be present, non-empty, and composed of canonical amino
acids. The runtime strips surrounding whitespace and uppercases input. It does
not infer a missing chain, truncate sequences, or mutate residues.

## Outputs

HIC returns a numeric `predicted_hic` value with research-support metadata.
Composite returns only `probability_not_developable` and the explicit positive
class. No LOW/MEDIUM/HIGH threshold or categorical developability judgment is
invented.

User-facing language should remain: “Model estimate based on sequence
representation” and “Use as research support; experimental verification
remains required.”

## Privacy and deployment

Phase 6A inference is local and does not call DeepSeek, OpenAI, Europe PMC,
PubMed, or another external provider. ESM2 weights may require an initial
download; once cached, inference runs locally. CUDA is used when available and
CPU is the fallback, with float32 representation.

Generated joblib artifacts and the model manifest are reproducible local
outputs and are not committed to Git.

## Reproducibility

The build script reads the frozen Phase 5 TRAIN/VALIDATION tables, frozen ESM2
embeddings, and authoritative selected-model configuration. It records model
IDs, hyperparameters, dimensions, training-row counts, ordered training hash,
provenance, and artifact SHA256 in the local manifest.

## Unsupported claims

The runtime does not support claims of universal antibody developability
prediction, family-independent generalization, clinical utility, causal
interpretation, wet-lab replacement, therapeutic efficacy prediction,
affinity prediction, automatic best-antibody selection, or a validated
production-grade predictor.
