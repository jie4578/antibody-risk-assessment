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
