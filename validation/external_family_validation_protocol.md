# Phase 7A — External Family-Diverse Validation Foundation

## Status and scientific boundary

This document freezes a data-foundation protocol only. The production
rule-based scientific baseline is not changed, and the Phase 5/6 ML
inference runtime is not changed. No model is trained, no threshold is
optimized, no AIntibody TEST row is used, and no external outcome is used to
tune the product.

The selected source is independent of Jain 2017 and AIntibody 2026. Phase 7A
does not claim family-independent performance; it prepares an auditable
population for human review before any later external-validation analysis.

## Dataset and provenance

The initial source is the official SAbDab2 all-summary download from the
[SAbDab2 official page](https://sabdab.opig.stats.ox.ac.uk/about) and its
[official summary endpoint](https://sabdab.opig.stats.ox.ac.uk/api/download/all-summary).
The provenance manifest is `external_family_validation/source_manifest.json`.

SAbDab2 is a structure-centric public database. The manifest records the
source URL, publication references, retrieval date, file size, SHA256, local
raw path, sequence coverage, and label availability. The inspected source
page does not state a simple redistribution license, so the raw third-party
file is local-only and is not committed by this phase.

## Inclusion and exclusion

Every source row is preserved in the normalized table, including repeated
structure instances, duplicate sequences, incomplete chain records, and
records without developability labels. No row is removed because it might be
unhelpful for a future model. Any later exclusion must have a documented
data-quality reason.

Valid paired records require both VH and VL to pass the existing project
sequence validator. Partial and invalid rows remain present with an explicit
status and reason. No sequence is manually corrected, concatenated, swapped,
or silently deduplicated.

## Sequence representation and provenance

The normalized schema contains `record_id`, `antibody_id`, `VH`, `VL`,
`sequence_status`, `sequence_hash`, source/species/format metadata, raw
sequence fields, and a serialized source-row payload. Normalized sequences
are used only in processed outputs; raw source values remain traceable.

The `family` field is intentionally not populated from an invented label.
Identity clusters are sequence-similarity proxies and are not immunogenetic
V-gene families, clonotypes, or lineage calls.

## Similarity audit and clustering

Exact paired-sequence overlap is measured with deterministic SHA256 hashes.
Pairwise VH/VL identity uses the existing project global-alignment helper.
For paired records, `paired_min` is the minimum of VH identity and VL
identity. Identity distributions are deterministic samples when the full
pair count exceeds the configured audit bound; the report records that limit.

Family-proxy clusters are produced independently at thresholds 0.70, 0.80,
and 0.90. A valid unique paired VH/VL sequence is assigned deterministically
to the first representative whose VH and VL global identities both meet the
threshold. A cheap length/k-mer prefilter is used only to reduce work; every
accepted pair is checked with global alignment. The prefilter and greedy
representative method are conservative engineering choices, not a claim of
an exhaustive or biologically definitive family partition.

## Experimental-label audit

The audit checks for HIC, Tm, Tagg, AC-SINS, BVP, and aggregation fields.
Structural method, resolution, and PDB metadata are not substituted for
developability labels. Missing labels remain missing; no label is synthesized,
imputed, or derived in Phase 7A.

Because the selected SAbDab2 summary does not provide a complete requested
developability panel, the current output is diversity/split-foundation data,
not a labeled performance benchmark.

## Split readiness and limitations

The data are ready for human review of family-diversity structure and future
family-held-out design. They are not yet ready for model training or external
performance claims. Future metrics must be pre-specified with sample size N,
preserve negative results, and distinguish structure-instance counts from
independent biological experiments.

Phase 7B may begin only after human review confirms that the selected source,
cluster proxy, label availability, and intended held-out population satisfy
the family-diverse requirement.
