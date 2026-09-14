# Phase 4A validation protocol

## Frozen boundary

- Frozen baseline commit: `d1487ed74bdfc52fb0b2015a25c4e91ee90af66d`.
- `core.py` and `scoring.py` cannot be changed during baseline validation.
- Existing scientific behavior is evaluated as-is. Experimental labels are
  never used to tune the rule-based score.

## Data handling rules

1. Raw datasets are immutable after acquisition.
2. Raw experimental values are never silently corrected.
3. Missing values remain missing; no zero or imputed substitute is created.
4. Rows are never removed because they produce poor model results.
5. Any exclusion requires a documented data-quality reason.
6. Jain is the initial retrospective benchmark dataset.
7. AIntibody is an independent external/prospective validation dataset.
8. AIntibody labels and assays must not tune baseline rules before external
   validation.
9. Negative benchmark results must be preserved and reported.
10. Every later reported statistic must include sample size N.
11. Original assay directionality is documented rather than guessed. Unknown
    directionality is recorded as `UNKNOWN`.
12. Derived variables are clearly distinguished from experimentally measured
    variables.

## Dataset policy

Jain source files are the three official PNAS/PMC XLSX supplements: S1
metadata, S2 variable-region sequences, and S3 experimental measurements.
AIntibody uses the official Nature Biotechnology workbook containing
Supplementary Data 1–3. Workbook structure is inspected before semantic
mapping; a row is not assumed to represent a unique antibody.

Processed tables preserve source identifiers, source row/sheet provenance,
sequence hashes, sequence status/reason, raw assay columns, duplicates and
missingness. Processing reads from `data/raw/` and writes only to
`data/processed/` and `reports/data_audit/`.
