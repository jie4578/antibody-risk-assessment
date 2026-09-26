# Phase 8B — Blind GDPa3 HIC Prediction

This runner is limited to the sequence-only Phase 8A snapshot and the frozen
`hic_esm2_v1` model. It does not accept a workbook, label path, assay field, or
arbitrary input path from the command line. It verifies the snapshot and model
hashes and manifest contract before inference, then calls the existing local
`FrozenMLPredictor` implementation. It does not invoke a provider, calculate
metrics, or access assay data.

Run from the repository root with:

```powershell
python -m validation.run_phase8b_blind_hic_prediction
```

The output is written to the ignored
`validation/data/external_developability/gdpa3_phase8b/` directory and refuses
to overwrite an existing artifact. Its exact columns are `antibody_id`,
`paired_hash`, `hic_prediction`, and `model_version`; rows remain in snapshot
order. Serialization is UTF-8, comma-delimited CSV with one header, no index,
LF line endings, and Python's round-trip-safe `.17g` formatting for prediction
floats. The generated prediction file is not intended for Git tracking.

The prediction artifact must be hashed and sealed before any label-bearing
GDPa3 file is opened. No performance or generalization claim follows from
prediction generation alone.
