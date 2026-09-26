# External family-diverse validation foundation

Phase 7A is an isolated, data-only audit layer for an external antibody
population. It does not change production scoring, Desktop behavior, or the
local ML inference runtime.

The current source is the official SAbDab2 all-summary CSV. The raw file is
kept locally under `data/raw/` and ignored by Git. Its provenance and SHA256
are recorded in `source_manifest.json`.

Run the deterministic normalization and diversity audit from the repository
root with:

```text
python -m validation.run_external_family_validation
```

This writes normalized data, threshold-specific cluster tables, and the JSON
audit report under ignored `data/processed/` and `reports/` directories. No
model is trained and no experimental label is synthesized. Human review is
required before any Phase 7B use.
