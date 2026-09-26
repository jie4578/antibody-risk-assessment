# Phase 7C.1 — GDPa3 Official Workbook Audit

Audit date: 2026-09-26. This is a data/provenance and assay-compatibility audit only.

## Source integrity and provenance

- Local source: `GDPa3_20260106_full.xlsx` (user-provided as the official GDPa3 workbook; no download performed in this audit).
- Size: 112,571 bytes; SHA256: `06daa55cb609278574d008c5509d90a63f9a8f1aa3949f34fc50a2e654b008f7`.
- ZIP/XLSX package integrity: PASS; source workbook was opened read-only and not modified.
- The file-specific redistribution license and exact original retrieval date are not recorded in the workbook and remain unverified. Keep the raw file local/ignored pending terms review.
- Official source describes GDPa3 competition targets as HIC, PR-CHO, AC-SINS pH 7.4, Tm2 and titer ([Ginkgo competition page](https://datapoints.ginkgo.bio/ai-competitions/2025-abdev-competition)).

## Actual workbook structure

| Sheet | Non-empty first-column rows | Columns |
| --- | ---: | ---: |
| `Definitions` | 21 | 4 |
| `Sequences` | 80 | 7 |
| `Assay Data - tidy format` | 320 | 15 |
| `Assay Data - average` | 80 | 40 |
| `Versioning` | 2 | 3 |

Exact assay and identity headers are preserved in the machine-readable audit JSON; this report intentionally omits sequence strings and assay values.

## VH/VL sequence audit

- Sequence rows / unique IDs: 80 / 80; duplicate ID rows: 0.
- VH/VL fields: `vh_protein_sequence` / `lc_protein_sequence`; the Sequences tab uses `lc_protein_sequence`, while Definitions names the light-chain protein field `vl_protein_sequence`.
- Project validator status: 80 VALID, 0 PARTIAL, 0 INVALID.
- Unique valid VH / VL / paired hashes: 80 / 80 / 80.
- Missing VH / VL: 0 / 0; sequence normalization needed: 0 rows.
- VH length min/median/max: 111 / 122.0 / 132 aa; VL: 104 / 108.0 / 113 aa.
- No IGHV/IGKV/IGLV germline calls are present. `hc_subtype` and `lc_subtype` are constant-region subtype metadata; identity clusters are not germline annotations.

## Exact sequence overlap

| Reference | exact VH | exact VL | exact paired VH/VL |
| --- | ---: | ---: | ---: |
| Jain | 0 | 0 | 0 |
| AIntibody_all_715_records | 0 | 0 | 0 |
| SAbDab2 | 0 | 0 | 0 |
| AIntibody TRAIN (hash-only) | — | — | 0 |
| AIntibody VALIDATION (hash-only) | — | — | 0 |
| AIntibody TEST (hash-only) | — | — | 0 |

AIntibody TEST overlap was determined solely from the frozen split manifest’s sequence hashes and split labels; no TEST sequence row, assay value, or label was opened for that check. The additional AIntibody TRAIN+VALIDATION similarity calculation used only paired sequences and global alignment.

## Family-diversity proxy and AIntibody TRAIN+VALIDATION novelty

- Nearest paired-min global identity against 381 unique AIntibody TRAIN+VALIDATION pairs (N=80 GDPa3 pairs): min 0.469, median 0.531, max 0.829.
- GDPa3 nearest-neighbour novelty bins: <0.50=15; 0.50–<0.70=57; 0.70–<0.80=7; 0.80–<0.90=1; ≥0.90=0.

| Paired-min identity edge threshold | Clusters | Largest | Singletons |
| ---: | ---: | ---: | ---: |
| 0.7 | 45 | 16 | 35 |
| 0.8 | 78 | 2 | 76 |
| 0.9 | 80 | 1 | 80 |

Clustering is exact all-pairs connected components with an edge only when both chain identities meet the threshold. It is an identity proxy, not an antibody-family or germline assignment. The 0.70 graph has a largest component of 16/80; at 0.80 the largest is 2/80; at 0.90 all 80 are singleton clusters. Together with zero exact overlaps, this supports a sequence-diverse external cohort for a human-reviewed HIC-only protocol, without claiming strict family-independent generalization.

## Complete experimental assay inventory and field-name crosswalk

| Workbook field | Definition | Tidy nonmissing / N | Average nonmissing / N | Replicate-count / SD nonmissing N |
| --- | --- | ---: | ---: | ---: |
| `acsins_dLmax_ph6` | Self association in a 20 mM histidine, 150 mM arginine.HCl, 0.05% polysorbate 80, pH 6.0 buffer reported as dLmax in nm | 320 / 320 | 80 / 80 | 80 / 80 |
| `acsins_dLmax_ph7.4` | Self association in a PBS pH 7.4 buffer reported as dLmax in nm | 320 / 320 | 80 / 80 | 80 / 80 |
| `hac_rt` | Retention time on heparin affinity chromatography reported in minutes | 61 / 320 | 61 / 80 | 80 / 0 |
| `hic_rt` | Retention time on hydrophobic interaction reported in minutes | 79 / 320 | 79 / 80 | 80 / 0 |
| `polyreactivity_prscore_cho` | Normalized polyreactivity score against CHO SMP | 313 / 320 | 80 / 80 | 80 / 80 |
| `polyreactivity_prscore_ova` | Normalized polyreactivity score against Ovalbumin | 320 / 320 | 80 / 80 | 80 / 80 |
| `sec_%monomer` | %Monomer assessed using size-exclusion chromatography | 80 / 320 | 80 / 80 | 80 / 0 |
| `smac_rt` | Retention time on standup monolayer affinity chromatography reported in minutes | 80 / 320 | 80 / 80 | 80 / 0 |
| `titer` | IgG titer assessed in clarified harvest supernatant reported in ug/mL | 240 / 320 | 80 / 80 | 80 / 80 |
| `tm1_nanodsf` | First transition peak for melting temperature determined using nanoDSF at a ramp rate of 1.5 degC/min reported in degC | 239 / 320 | 80 / 80 | 80 / 80 |
| `tm2_nanodsf` | Second transition peak for melting temperature determined using nanoDSF at a ramp rate of 1.5 degC/min reported in degC | 221 / 320 | 74 / 80 | 80 / 74 |
| `tm3_nanodsf` | Third transition peak for melting temperature determined using nanoDSF at a ramp rate of 1.5 degC/min reported in degC | 74 / 320 | 25 / 80 | 80 / 25 |
| `tonset_nanodsf` | Onset of thermal melting determined using nanoDSF at a ramp rate of 1.5 degC/min reported in degC | 239 / 320 | 80 / 80 | 80 / 80 |

GDPa3’s five named competition endpoints resolve to workbook fields as follows: HIC → `hic_rt` (minutes); PR-CHO → `polyreactivity_prscore_cho`; AC-SINS pH 7.4 → `acsins_dLmax_ph7.4` (dLmax, nm); Tm2 → `tm2_nanodsf` (second nanoDSF transition, °C); Titer → `titer` (µg/mL). The workbook additionally contains AC-SINS pH 6, HAC, SMAC, SEC % monomer, OVA polyreactivity, Tm1, Tm3 and nanoDSF onset. These are distinct readouts, not interchangeable labels.

`Definitions` describes 21 fields. `Assay Data - tidy format` has one row per technical replicate (320 rows, 80 IDs), while `Assay Data - average` has one antibody row (80) and 40 columns: ID plus mean/replicate-count/SD fields for 13 readouts. Missing values are reported, not imputed.

## Frozen model compatibility and protocol shift

- HIC-only candidate: GDPa3 `hic_rt_avg` and the frozen `hic_esm2_v1` target both represent HIC retention time in minutes; GDPa3 has 79/80 nonmissing averaged measurements. This is nominal measurement-family compatibility, not confirmed protocol equivalence.
- Protocol shift remains material: GDPa3 workbook does not specify the HIC column, buffers, gradient, instrument, or detailed run conditions. AIntibody’s published HIC-HPLC method is specified separately and was performed by Mosaic Biosciences ([Nature Biotechnology paper and Methods](https://www.nature.com/articles/s41587-026-03238-6)). Do not transform or threshold GDPa3 values; any future test must be explicitly described as cross-source/protocol external evaluation.
- Composite classifier compatibility: NO. GDPa3 lacks the AIntibody BVP and Tagg endpoints; `AC-SINS dLmax` is not the AIntibody dPW-adjusted metric; and GDPa3 Tm2 is not the AIntibody Tm endpoint. Do not apply the frozen composite classifier or derive a GDPa3 composite label.
- No ML training, tuning, prediction, performance calculation, correlation, thresholding, or label-derived filtering was performed. No production code was changed.

## Phase 7C.1 decision

**READY_HIC_ONLY** — eligible to prepare/review a protocol for a frozen HIC-only external evaluation, with the protocol shift explicitly treated as a limitation. Composite developability validation is not supported. Phase 8 has not started; no prediction or outcome analysis was performed.

Machine-readable details: [gdpa3_phase7c1_audit.json](gdpa3_phase7c1_audit.json). Provenance manifest: [source_manifest.json](../external_developability/source_manifest.json). HIC-only protocol for human review: [Phase 8 draft](../external_developability/phase8_hic_protocol_draft.md).
