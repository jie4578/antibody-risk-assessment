# SUPERSEDED: Phase 8 GDPa3 HIC External Validation Draft

This historical draft is not authoritative. The protocol is now frozen in
[`PHASE8_HIC_EXTERNAL_VALIDATION_PROTOCOL.md`](PHASE8_HIC_EXTERNAL_VALIDATION_PROTOCOL.md).
Do not use this draft to execute Phase 8B or Phase 8C.

---

# Historical draft (retained for provenance)

**Status: DRAFT — not preregistered, not frozen, and not executed.** This
document is a Phase 7C.1 handoff only. No inference, outcome relationship,
performance statistic, or correlation has been calculated.

## Scope

- Dataset: the local, raw GDPa3 workbook identified in
  `source_manifest.json`; keep it ignored and immutable.
- Unit: one source antibody ID / one paired VH/VL sequence. Retain all source
  rows; the audited workbook has no duplicate IDs or paired sequences.
- Sequence eligibility: both chains must pass the existing canonical
  sequence validator. Do not repair residues or infer a missing chain.
- Exact overlap: the current sequence-only audit found no exact VH, VL, or
  paired-hash overlap with Jain, the normalized AIntibody collection, the
  frozen AIntibody split hashes, or SAbDab2. This is sequence evidence, not a
  germline-family annotation.

## Sole endpoint under consideration

- Endpoint: GDPa3 `hic_rt_avg`, taken as-is from the workbook's average sheet,
  in minutes; no rescaling, thresholding, imputation, or endpoint substitution.
- Expected evaluable N from the current missingness audit: 79 of 80. Keep the
  one missing HIC value missing and document the exact analysis N.
- Existing frozen model only: `hic_esm2_v1`, unchanged weights, ESM2 revision,
  paired representation, and inference runtime. No refit, recalibration,
  hyperparameter change, or model selection.
- The GDPa3 workbook does not specify the HIC column, mobile phases, gradient,
  instrument, or full assay conditions. The AIntibody paper documents a
  separately performed HIC-HPLC protocol. Treat the future evaluation as a
  cross-source/protocol transport test; do not call it same-protocol
  replication. The exact GDPa3 protocol should be sought from its official
  source before the protocol is frozen.

## Planned analysis (requires separate approval and protocol freeze)

1. Run the frozen model once on all 80 eligible paired sequences; do not filter
   samples based on predictions or labels.
2. Pair predictions to the original GDPa3 `hic_rt_avg` by preserved
   `antibody_id`; report N and missingness.
3. If approved at freeze, use Spearman rank association as the single primary
   statistic and report a two-sided 95% interval. MAE and RMSE may be
   descriptive secondary statistics on the unchanged minute scale. Do not
   optimize a threshold, direction, transform, or calibration from GDPa3.
4. Preserve negative, null, or unstable findings. Do not infer assay direction
   from the results. State the protocol-shift limitation in every summary.

## Explicit exclusions

- No composite classifier evaluation: GDPa3 does not provide the frozen
  AIntibody five-assay endpoint set. In particular, GDPa3 PR-CHO is not BVP,
  AC-SINS dLmax is not the AIntibody dPW-adjusted endpoint, nanoDSF Tm2 is not
  the AIntibody Tm endpoint, and GDPa3 has no Tagg endpoint.
- No access to AIntibody TEST outcomes; no AIntibody retraining, tuning,
  threshold transfer, or label inspection.
- No new models, rule-score analysis, correlations between GDPa3 assay fields,
  or claims of clinical/family-independent generalization.

## Freeze gate

Before execution, a human reviewer should verify the GDPa3 file's official
origin and reuse terms, request the missing HIC protocol metadata, approve the
single-endpoint/statistical plan, and freeze the protocol in a separate Phase
8 checkpoint. Until those steps, Phase 8 remains not started.
