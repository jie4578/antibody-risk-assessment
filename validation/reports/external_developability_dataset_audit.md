# Phase 7C — External Developability Dataset Audit

Audit date: 2026-09-26

## Result

**GDPa3 acquired locally and audited. Decision: READY_HIC_ONLY for human review of a future frozen HIC-only protocol; composite validation is unsupported and no Phase 8 analysis has started.**

The workbook was supplied locally by the user as the untouched official file; this audit did not download or edit it. SHA256, workbook contents, sequence overlap, family-diversity proxies, and per-assay missingness were checked. Its origin is not cryptographically authenticated, the original retrieval date is unknown, and file-specific reuse terms remain unverified.

## Candidate comparison

| Candidate | Publication/source | Sequences and experimental labels | Access / provenance | Decision |
| --- | --- | --- | --- | --- |
| **GDPa3 (Ginkgo Datapoints antibody dataset 3)** | 2025 AbDev Competition outcomes paper, DOI [10.1080/19420862.2026.2634216](https://doi.org/10.1080/19420862.2026.2634216); [official Ginkgo dataset access page](https://datapoints.ginkgo.bio/dataset-access) | Workbook confirms 80 paired VH/VL records. Five named challenge endpoints map to exact workbook fields; 13 readouts are present across the raw assay columns. HIC, PR-CHO, AC-SINS pH 7.4 and titer are present in 80/80 averages; Tm2 in 74/80; HIC in 79/80. | Local workbook: 112,571 bytes; SHA256 recorded in the manifest. File-specific reuse license and original retrieval date remain unverified. | **Sequence-independent at exact-hash level** versus Jain, all 715 normalized AIntibody rows, frozen AIntibody split hashes, and SAbDab2. Eligible for HIC-only protocol review; protocol equivalence is not confirmed. |
| GDPa1 | PROPHET-Ab paper, DOI [10.1080/19420862.2025.2593055](https://doi.org/10.1080/19420862.2025.2593055); official [Ginkgo Hugging Face dataset](https://huggingface.co/datasets/ginkgo-datapoints/GDPa1) | 246 IgGs; paired sequence fields and ten experimental assay types are described by the authors. | The repository requires agreement to share contact information before file access. Its dataset license is CC BY 4.0 with stated restrictions. | Not selected as the independent cohort: it is a clinical-antibody panel with a documented Jain-referenced 20-antibody comparison subset, creating known overlap risk. Do not accept gated terms or assume independence. |
| GDPa4 | [Official Ginkgo dataset access page](https://datapoints.ginkgo.bio/dataset-access) | 160 bispecifics plus 65 IgGs; experimental developability measurements. | Official release listing. | Reject for this purpose: the release is explicitly derived from GDPa1 and is not an independent cohort. |
| GDPa5 | [Official Ginkgo dataset access page](https://datapoints.ginkgo.bio/dataset-access) | 160 VHHs, including clinical and non-clinical sequences, with ten developability assay types. | Official release listing; file-specific license not verified. | Not selected for the paired VH/VL project: VHH is a single-domain format, not paired VH/VL. Potential future VHH-specific validation dataset. |
| DOTAD 2.0 | [Official release center](https://i.uestc.edu.cn/DOTAD2.0/Download.html); publication record [PMID 38530613](https://pubmed.ncbi.nlm.nih.gov/38530613/) | Integrated sequence and experimental developability records from multiple sources. | Academic/non-commercial reuse note; underlying source terms apply. The release center says source evidence is retained where available. | Not selected as one independent cohort: mixed-source records require source-by-source provenance, license, and overlap filtering first. |
| FLAb2 collection | [Primary paper and supplement](https://pmc.ncbi.nlm.nih.gov/articles/PMC12767642/) | Multi-study collection of antibody developability datasets; sequence and assay coverage varies by contributing source. | Public article/supplement, but component-dataset terms and sequence availability must be audited separately. | Not selected as a single cohort: it is a heterogeneous collection, not one independently sourced population. |

## GDPa3 audit status

- **Workbook:** `GDPa3_20260106_full.xlsx`; 5 sheets: Definitions (21 data rows), Sequences (80), Assay Data - tidy format (320 technical-replicate rows), Assay Data - average (80 antibody rows), Versioning (2 entries). Workbook history records v3.1 on 2026-01-06 and v3.2 on 2026-02-09 adding AC-SINS data.
- **Integrity:** valid XLSX package; SHA256 `06daa55cb609278574d008c5509d90a63f9a8f1aa3949f34fc50a2e654b008f7`; file remains ignored by Git and unmodified.
- **VH/VL:** `vh_protein_sequence` and `lc_protein_sequence`; 80/80 valid paired sequences, 80 unique VH, 80 unique VL and 80 unique pairs. No normalization was required. Definitions calls the light-chain protein field `vl_protein_sequence`, a source-header discrepancy documented in the detailed audit.
- **Exact overlap:** zero exact VH, VL or paired hashes with Jain, AIntibody's 715 sequence rows or SAbDab2. Frozen AIntibody TRAIN/VALIDATION/TEST/ALL paired-hash overlaps are each zero; the TEST check used only hash/split membership and did not open labels.
- **Similarity:** against 381 unique AIntibody TRAIN+VALIDATION sequences, GDPa3 nearest paired-min global identity has median 0.531 and max 0.829. Novelty bins and deterministic exact identity-proxy clusters at 0.70/0.80/0.90 are recorded in the detailed report. These clusters are not germline families.
- **Germline metadata:** no IGHV/IGKV/IGLV calls. `hc_subtype` / `lc_subtype` describe constant-region subtypes and must not be treated as germline annotations.
- **Assay crosswalk:** HIC → `hic_rt` (min); PR-CHO → `polyreactivity_prscore_cho`; AC-SINS pH 7.4 → `acsins_dLmax_ph7.4` (nm); Tm2 → `tm2_nanodsf` (second nanoDSF transition, °C); Titer → `titer` (µg/mL). Other readouts include AC-SINS pH 6, HAC, SMAC, SEC % monomer, PR-OVA, Tm1, Tm3 and nanoDSF onset.
- **HIC compatibility:** nominally compatible measurement family with the frozen `hic_esm2_v1` output because both are HIC retention-time values in minutes. GDPa3's workbook omits column, buffer and gradient details, so protocol equivalence is unconfirmed; any future comparison is a cross-source/protocol test, not same-protocol validation.
- **Composite compatibility:** unsupported. GDPa3 lacks BVP and Tagg; its AC-SINS dLmax and nanoDSF Tm2 are not interchangeable with AIntibody's dPW-adjusted AC-SINS and Tm endpoints. No GDPa3 composite label was created.

Full exact headers, per-field missingness, definitions, identity statistics and source hash are in [the Phase 7C.1 audit](gdpa3_phase7c1_audit.md) and [source manifest](../external_developability/source_manifest.json).

## Readiness decision

**READY_HIC_ONLY.** Exact-hash independence and sequence diversity support review of a future HIC-only protocol. The future protocol must freeze the existing `hic_esm2_v1`, use only GDPa3 `hic_rt_avg` with its original minute scale, retain the missing assay as missing, record protocol shift, and forbid tuning/recalibration. It must not use the frozen composite classifier. Phase 8 has not started; no predictions, performance statistics, or correlations were calculated.

Raw third-party data remains local-only until its applicable reuse terms are verified. No model was trained or tuned, and no production scientific code was changed.

No model was trained or tuned. No prediction performance, correlations, or endpoint relationships were analyzed. No labels were inferred or generated.
