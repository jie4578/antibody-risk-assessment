# Phase 4D0 — AIntibody Independent External Validation Pre-registration

Status: pre-registration only. No AIntibody experimental outcomes,
outcome distributions, correlations, ROC-AUC, PR-AUC, or feature-performance
relationships are calculated by this checkpoint.

Pre-registration date: 2026-09-18

## Frozen boundary

- Frozen scientific baseline: `d1487ed74bdfc52fb0b2015a25c4e91ee90af66d`.
- Phase 4B feature checkpoint: `ec3a2221b6f9f68d3ea0171c8ae9a524d17fc554`.
- Phase 4C benchmark checkpoint: `abd2001218ef64b85bee0c0d8b485c60262cc399`.
- Dataset reserved for independent validation: AIntibody 2026.
- The product rule engine, scoring formula, thresholds, CDR definitions,
  feature weights, and scientific code are frozen.
- No feature, threshold, sign convention, duplicate rule, or endpoint will
  be changed after outcome inspection.

Phase 4C is already known and cannot be made blind again: Jain contained 137
records and 576 feature-assay comparisons, with no BH-FDR q < 0.05 result,
no moderate/strong/very strong association, and predominantly weak/null
relationships. This prior result is recorded as context, not as a tuning
target.

## Dataset snapshot before external analysis

The Phase 4B data foundation recorded:

- Dataset identifier: `aintibody_2026`.
- 715 records (input records).
- 686 unique VH/VL hashes (unique VH/VL sequence hashes).
- 54 duplicate-group rows (rows in duplicate sequence groups).

These values are a pre-analysis data snapshot. The duplicate audit must be
completed before any outcome relationship is calculated. No record is silently
discarded or deduplicated.

## Scientific questions

### Q1 — Individual developability assays

Do frozen sequence-rule features show association with individual
experimental developability assays?

Primary assays:

- Tm
- Tagg
- HIC
- BVP
- AC-SINS

The primary association statistic is two-sided Spearman rho. Each frozen
feature-by-assay result must report rho, p-value, BH-FDR q-value, and pairwise
complete-observation N. Missing assay or feature values are not imputed.

### Q2 — Composite developability outcome

Can frozen rule features discriminate the paper-defined composite
developability outcome?

If an explicit paper-provided categorical developability status exists, it is
the primary classification endpoint. If only `total_developability_score`
exists, a binary endpoint may be derived only according to the published paper
rule. Use the published paper rule only. No threshold may be invented,
selected from the observed outcomes, or
optimized for this project. The original score, derived label, and derivation
method must all be preserved.

If neither a paper-provided status nor an unambiguous published derivation rule
is available, composite classification is reported as unavailable rather than
constructed ad hoc.

### Q3 — Generalization of the Jain finding

Does independent AIntibody validation support the conclusion that motif/rule
features have limited value for broad developability prediction? This is an
interpretation question, not a tuning target. Negative or inconsistent results
remain valid outcomes.

## Frozen feature set

The primary rule feature set is the exact 48-feature Phase 4B set used in the
Jain benchmark. No AIntibody-specific feature is added and no feature is
selected using AIntibody outcomes.

### Scores and penalties

- `VH_calculated_score`
- `VL_calculated_score`
- `VH_rule_penalty`
- `VL_rule_penalty`

### Site and region counts

- `VH_total_sites`, `VL_total_sites`, `total_sites_combined`
- `VH_cdr_sites`, `VL_cdr_sites`, `cdr_sites_combined`
- `VH_ptm_sites`, `VL_ptm_sites`, `ptm_sites_combined`
- `VH_liability_sites`, `VL_liability_sites`, `liability_sites_combined`

### Category counts

For VH, VL, and the safe combined count only:

- deamidation
- isomerization
- oxidation
- glycosylation
- O-glycosylation

The same five categories are also retained as CDR-specific counts for VH,
VL, and safe combined counts. These are deterministic frozen rule outputs.

### Controls/descriptive variables

- `VH_length`
- `VL_length`

Lengths are controls/descriptive variables (control/descriptive variables),
not developability predictors and not a basis for feature selection.

The exact frozen feature names are:

```text
VH_calculated_score
VL_calculated_score
VH_rule_penalty
VL_rule_penalty
VH_total_sites
VL_total_sites
total_sites_combined
VH_cdr_sites
VL_cdr_sites
cdr_sites_combined
VH_ptm_sites
VL_ptm_sites
ptm_sites_combined
VH_liability_sites
VL_liability_sites
liability_sites_combined
VH_deamidation_count
VH_isomerization_count
VH_oxidation_count
VH_glycosylation_count
VH_o_glycosylation_count
VL_deamidation_count
VL_isomerization_count
VL_oxidation_count
VL_glycosylation_count
VL_o_glycosylation_count
deamidation_count_combined
isomerization_count_combined
oxidation_count_combined
glycosylation_count_combined
o_glycosylation_count_combined
VH_cdr_deamidation_count
VH_cdr_isomerization_count
VH_cdr_oxidation_count
VH_cdr_glycosylation_count
VH_cdr_o_glycosylation_count
VL_cdr_deamidation_count
VL_cdr_isomerization_count
VL_cdr_oxidation_count
VL_cdr_glycosylation_count
VL_cdr_o_glycosylation_count
cdr_deamidation_count_combined
cdr_isomerization_count_combined
cdr_oxidation_count_combined
cdr_glycosylation_count_combined
cdr_o_glycosylation_count_combined
VH_length
VL_length
```

## Primary analysis unit and population

The primary inferential unit is one unique VH/VL sequence hash where that unit
is scientifically defensible.

The primary population is eligible AIntibody challenge antibody submissions
with identifiable VH and VL sequences and experimentally measured primary
developability outcomes. Controls and parental antibodies remain available
for descriptive and sensitivity analyses, but are excluded from the primary
population unless the paper explicitly defines them as part of the primary
benchmark population. This choice is made from source identity and protocol
metadata, never from rule performance.

The following identity fields must be audited before outcome analysis:

- `sequence_hash`
- `record_id`
- challenge
- record type
- submission identity
- control/parental status

## Duplicate handling

Duplicate VH/VL hashes are preserved in the raw normalized records and are not
silently deduplicated.

1. If identical experimental values are observed, one unique-sequence primary record
   may represent the group.
2. If rows are repeated measurements of the same biological sequence under the
   same assay definition, continuous values are aggregated by the pre-specified
   median. replicate count, minimum, maximum, and median are retained.
3. If rows represent different constructs, conditions, controls, or assay
   contexts, do NOT merge them merely because the VH/VL sequences match.
4. If duplicate identity is ambiguous, exclude that sequence from PRIMARY
   unique-sequence analysis and retain it in sensitivity/descriptive analyses
   with the reason documented.

No duplicate row is selected because it gives a favorable result.
Never overwrite original data.

## Individual-assay statistics

For Tm, Tagg, HIC, BVP, and AC-SINS, every frozen feature-by-assay result
reports:

- Spearman rho
- two-sided p-value
- Benjamini-Hochberg q-value
- pairwise complete-observation N

The primary significance threshold is q < 0.05. q < 0.10 is exploratory
only. Effect size is reported independently of significance using the frozen
descriptive tiers; raw p < 0.05 alone is never called validation.

No imputation, assay-informed transformation, outlier deletion, or outcome-
dependent feature selection is permitted.
Do NOT select features after viewing outcomes.

## Composite classification metrics

Primary metrics, calculated only after the endpoint audit, are:

- ROC-AUC
- PR-AUC

Secondary sensitivity, specificity, precision, recall, and F1 may be reported
only at existing frozen rule thresholds and only when a scientifically valid
mapping between the pre-existing predictor and the paper endpoint exists.
Do NOT optimize a new threshold. Do NOT select a best cutoff on AIntibody.

The current product has no validated paired VH/VL developability score.
Therefore:

- Do NOT average VH and VL scores.
- Do NOT compute a mean risk score.
- Do NOT create a weighted paired score.

Individual `VH_rule_penalty`, `VL_rule_penalty`, and safe count aggregates may
be evaluated independently.

## Directionality

For every primary assay and composite endpoint, directionality is determined
from the AIntibody paper/protocol before outcome relationships are examined.
Each endpoint is recorded as `higher_unfavorable`, `lower_unfavorable`,
`context_dependent`, or `UNKNOWN`, with a source note. Direction is never
inferred from observed rule-feature correlations.

## Primary, secondary, and excluded analyses

Primary analyses:

- unique-sequence population
- five developability assays
- paper-defined composite outcome where available
- frozen rule features and explicit controls
- pre-registered statistics and thresholds

Secondary/sensitivity analyses:

- record-level analysis
- duplicate-aware analysis
- controls/parentals when scientifically appropriate
- SPR and KinExA affinity endpoints as separate biology

Affinity endpoints must not be mixed into the primary developability outcome.

The following are excluded from Phase 4D frozen validation:

- feature tuning or weight changes
- cutoff optimization
- outcome-based outlier removal
- sign-convention changes after seeing results
- Do NOT fit XGBoost or any other predictive model.
- XGBoost, logistic-regression optimization, random forest, neural network,
  ESM, ProtT5, or any other ML training

## Interpretation rules

- Similarly weak/null relationships support limited broad-developability
  predictive scope of motif rules.
- Reproducible moderate relationships may indicate selected assay dimensions
  captured by specific frozen features, without proving broad utility.
- Strong discrimination requires replication and leakage/confound audits before
  any predictive-utility claim.
- Opposite or inconsistent results require dataset-dependence and
  assay/context sensitivity analysis.

Statistical significance is not the sole definition of success. Negative
results remain valid and must be preserved.

## Future outputs — not generated in Phase 4D0

Future result files are pre-registered but must not be created in this phase:

- `validation/data/external_validation/aintibody_primary_population.csv`
- `validation/data/external_validation/aintibody_duplicate_audit.csv`
- `validation/data/external_validation/aintibody_assay_results.csv`
- `validation/data/external_validation/aintibody_classification_results.csv`
- `validation/reports/aintibody_external/report.md`
- assay heatmaps, classification summaries, and duplicate-audit figures

These output directories are gitignored to prevent accidental result
generation from entering version control.

## Pre-registration boundary

This Phase 4D0 checkpoint creates only this protocol, outcome-blind
specification metadata, tests, and output ignore rules. It does not read
AIntibody experimental values, inspect outcome distributions, calculate
statistics, calculate classification metrics, or train any model.
