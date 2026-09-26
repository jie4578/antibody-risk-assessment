# Phase 7B-A — SAbDab2 external diversity audit

## Provenance and population

- Dataset: SAbDab2
- Official source: https://sabdab.opig.stats.ox.ac.uk/api/download/all-summary
- Publication: Capel et al. (2026), SAbDab2: The structural antibody database in the age of machine learning, bioRxiv 2026.06.16.732554, DOI: 10.64898/2026.06.16.732554; foundational SAbDab publication: Dunbar et al. (2014), Nucleic Acids Research, DOI: 10.1093/nar/gkt1043
- Acquisition date: 2026-09-25
- Raw SHA256: `7f992a3ffd7ec33a4b44a9d505fc7a9e0f9fd3d320a2a15ab9ae14bd6dba219f`
- Access/redistribution: Public access through the official OPIG endpoint; no simple redistribution license was confirmed from the inspected source page. Raw file is therefore local-only for this phase.
- Source structure records: 22287
- Valid paired records: 17459
- Unique valid paired VH/VL hashes: 5482
- Internal reference: frozen AIntibody TRAIN 285 + VALIDATION 96 = 381 unique hashes; TEST excluded.
- Descriptive unit: one valid paired VH/VL sequence hash. Repeated structures are retained in the Phase 7A source audit and counted once here.

## Sequence diversity from Phase 7A

| Paired identity threshold | Deterministic representative clusters | Largest cluster | Singletons |
| --- | ---: | ---: | ---: |
| 0.7 | 1017 | 691 | 544 |
| 0.8 | 2928 | 263 | 2139 |
| 0.9 | 4393 | 32 | 3811 |

Paired-min global identity sample: N=10000, median=0.4806, Q1=0.4453, Q3=0.5268.
Clusters are deterministic sequence-similarity proxies, not biological family assignments.

## Frozen RULE48 distribution

Every count-feature prevalence is the fraction with a value above zero among observed unique paired sequences. Scores, penalties, and lengths are continuous and have no prevalence interpretation.

| Count feature | SAbDab2 nonzero / N | SAbDab2 fraction | AIntibody TRAIN+VALIDATION nonzero / N | AIntibody fraction |
| --- | ---: | ---: | ---: | ---: |
| VH_total_sites | 5385 / 5482 | 0.9823 | 381 / 381 | 1.0000 |
| VL_total_sites | 5056 / 5482 | 0.9223 | 381 / 381 | 1.0000 |
| total_sites_combined | 5475 / 5482 | 0.9987 | 381 / 381 | 1.0000 |
| VH_cdr_sites | 4659 / 5482 | 0.8499 | 364 / 381 | 0.9554 |
| VL_cdr_sites | 2571 / 5482 | 0.4690 | 67 / 381 | 0.1759 |
| cdr_sites_combined | 5069 / 5482 | 0.9247 | 367 / 381 | 0.9633 |
| VH_ptm_sites | 643 / 5482 | 0.1173 | 17 / 381 | 0.0446 |
| VL_ptm_sites | 337 / 5482 | 0.0615 | 14 / 381 | 0.0367 |
| ptm_sites_combined | 926 / 5482 | 0.1689 | 30 / 381 | 0.0787 |
| VH_liability_sites | 5366 / 5482 | 0.9788 | 381 / 381 | 1.0000 |
| VL_liability_sites | 5023 / 5482 | 0.9163 | 381 / 381 | 1.0000 |
| liability_sites_combined | 5470 / 5482 | 0.9978 | 381 / 381 | 1.0000 |
| VH_deamidation_count | 3481 / 5482 | 0.6350 | 21 / 381 | 0.0551 |
| VH_isomerization_count | 3890 / 5482 | 0.7096 | 360 / 381 | 0.9449 |
| VH_oxidation_count | 5094 / 5482 | 0.9292 | 381 / 381 | 1.0000 |
| VH_glycosylation_count | 492 / 5482 | 0.0897 | 17 / 381 | 0.0446 |
| VH_o_glycosylation_count | 169 / 5482 | 0.0308 | 0 / 381 | 0.0000 |
| VL_deamidation_count | 2409 / 5482 | 0.4394 | 15 / 381 | 0.0394 |
| VL_isomerization_count | 2425 / 5482 | 0.4424 | 46 / 381 | 0.1207 |
| VL_oxidation_count | 3787 / 5482 | 0.6908 | 381 / 381 | 1.0000 |
| VL_glycosylation_count | 244 / 5482 | 0.0445 | 14 / 381 | 0.0367 |
| VL_o_glycosylation_count | 93 / 5482 | 0.0170 | 0 / 381 | 0.0000 |
| deamidation_count_combined | 4400 / 5482 | 0.8026 | 34 / 381 | 0.0892 |
| isomerization_count_combined | 4602 / 5482 | 0.8395 | 362 / 381 | 0.9501 |
| oxidation_count_combined | 5320 / 5482 | 0.9704 | 381 / 381 | 1.0000 |
| glycosylation_count_combined | 700 / 5482 | 0.1277 | 30 / 381 | 0.0787 |
| o_glycosylation_count_combined | 259 / 5482 | 0.0472 | 0 / 381 | 0.0000 |
| VH_cdr_deamidation_count | 1506 / 5482 | 0.2747 | 7 / 381 | 0.0184 |
| VH_cdr_isomerization_count | 2986 / 5482 | 0.5447 | 332 / 381 | 0.8714 |
| VH_cdr_oxidation_count | 3428 / 5482 | 0.6253 | 174 / 381 | 0.4567 |
| VH_cdr_glycosylation_count | 246 / 5482 | 0.0449 | 4 / 381 | 0.0105 |
| VH_cdr_o_glycosylation_count | 72 / 5482 | 0.0131 | 0 / 381 | 0.0000 |
| VL_cdr_deamidation_count | 1434 / 5482 | 0.2616 | 7 / 381 | 0.0184 |
| VL_cdr_isomerization_count | 1039 / 5482 | 0.1895 | 43 / 381 | 0.1129 |
| VL_cdr_oxidation_count | 369 / 5482 | 0.0673 | 6 / 381 | 0.0157 |
| VL_cdr_glycosylation_count | 38 / 5482 | 0.0069 | 14 / 381 | 0.0367 |
| VL_cdr_o_glycosylation_count | 41 / 5482 | 0.0075 | 0 / 381 | 0.0000 |
| cdr_deamidation_count_combined | 2560 / 5482 | 0.4670 | 14 / 381 | 0.0367 |
| cdr_isomerization_count_combined | 3470 / 5482 | 0.6330 | 337 / 381 | 0.8845 |
| cdr_oxidation_count_combined | 3555 / 5482 | 0.6485 | 176 / 381 | 0.4619 |
| cdr_glycosylation_count_combined | 284 / 5482 | 0.0518 | 17 / 381 | 0.0446 |
| cdr_o_glycosylation_count_combined | 113 / 5482 | 0.0206 | 0 / 381 | 0.0000 |

| Continuous feature | SAbDab2 median [Q1, Q3] (N) | AIntibody TRAIN+VALIDATION median [Q1, Q3] (N) |
| --- | ---: | ---: |
| VH_calculated_score | 80.3000 [74.2000, 87.0000] (5482) | 83.4000 [81.6000, 88.1000] (381) |
| VL_calculated_score | 91.0000 [86.2000, 96.0000] (5482) | 96.0000 [96.0000, 96.0000] (381) |
| VH_rule_penalty | 19.7000 [13.0000, 25.8000] (5482) | 16.6000 [11.9000, 18.4000] (381) |
| VL_rule_penalty | 9.0000 [4.0000, 13.8000] (5482) | 4.0000 [4.0000, 4.0000] (381) |
| VH_length | 121.0000 [118.0000, 124.0000] (5482) | 122.0000 [117.0000, 123.0000] (381) |
| VL_length | 108.0000 [107.0000, 111.0000] (5482) | 107.0000 [107.0000, 107.0000] (381) |

## Liability sites and CDR/framework locations

| Quantity | SAbDab2 | AIntibody TRAIN+VALIDATION |
| --- | ---: | ---: |
| Total detected risk-site rows | 38045 | 2285 |
| Sites per paired sequence, median [Q1, Q3] | 7.0000 [5.0000, 8.0000] | 6.0000 [5.0000, 6.0000] |
| CDR sites | 14039 | 635 |
| Framework sites | 24006 | 1650 |

SAbDab2 categories: N-糖基化: 772, O-糖基化: 1747, 异构化: 9041, 氧化: 17776, 脱酰胺化: 8709.
AIntibody categories: N-糖基化: 31, 异构化: 475, 氧化: 1743, 脱酰胺化: 36.
SAbDab2 regions: CDR1: 4382, CDR2: 6874, CDR3: 2783, FW: 24006.
AIntibody regions: CDR1: 8, CDR2: 95, CDR3: 532, FW: 1650.

## Frozen ESM2 representation geometry

- Model: `facebook/esm2_t30_150M_UR50D` at immutable revision `a695f6045e2e32885fa60af20c13cb35398ce30c`.
- Representation: VH/VL final hidden state residue mean pooling; 640 + 640 float32.
- SAbDab2 embedding rows: 5482; internal reference rows: 381.
- Exact paired sequence-hash overlap: 0.
- External embedding SHA256: `08e1d20efe0306d185ffeda8c2493c30d85d6cc160d29e639f4a696ef28a6d0f`.
- Real extraction repeatability: N=10, maximum absolute difference=0.0.

| Paired cosine statistic | N | Median | Q1 | Q3 |
| --- | ---: | ---: | ---: | ---: |
| SAbDab2 within-space sampled pairs | 10000 | 0.9798 | 0.9741 | 0.9842 |
| AIntibody TRAIN+VALIDATION within-space sampled pairs | 10000 | 0.9958 | 0.9943 | 0.9970 |
| Cross-space sampled pairs | 10000 | 0.9836 | 0.9787 | 0.9867 |
| Each external row's nearest internal neighbor | 5482 | 0.9889 | 0.9866 | 0.9907 |
| Nearest internal, external exact-hash overlaps excluded | 5482 | 0.9889 | 0.9866 | 0.9907 |

No classifier, endpoint comparison, prediction metric, or PCA was calculated.

## Immunoglobulin germline family annotations

- Status: UNAVAILABLE.
- Source annotation columns: none.
- IGHV family counts: unavailable.
- IGKV family counts: unavailable.
- IGLV family counts: unavailable.
- Identity clusters are not mapped to germline families.

## Limitations and next gate

- SAbDab2 is a structure-centered collection. Structure instances are not independent biological experiments; external analyses here count unique paired sequences.
- No requested HIC, Tm, Tagg, AC-SINS, BVP, or aggregation outcome labels are present in the audited summary.
- The rule and embedding comparisons are descriptive distributions only. They support no biological or predictive-performance conclusion.
- Identity clustering used a deterministic representative method with candidate prefilters; it is not an exhaustive germline or lineage assignment.
- Family-diverse external ML validation requires a separately reviewed labeled dataset and a predeclared held-out protocol. Phase 7B-A does not provide that validation.

ML training: NO. Model tuning: NO. Experimental endpoint evaluation: NO. Prediction performance: NOT CALCULATED.
