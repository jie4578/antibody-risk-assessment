"""Pre-registered, outcome-blind specification for Phase 4D validation.

This module contains constants only.  It does not read AIntibody files,
experimental values, or generated validation outputs.
"""

from __future__ import annotations


FROZEN_SCIENTIFIC_BASELINE = "d1487ed74bdfc52fb0b2015a25c4e91ee90af66d"
PHASE_4B_FEATURE_CHECKPOINT = "ec3a2221b6f9f68d3ea0171c8ae9a524d17fc554"
PHASE_4C_BENCHMARK_CHECKPOINT = "abd2001218ef64b85bee0c0d8b485c60262cc399"

DATASET = "aintibody_2026"
EXPECTED_INPUT_RECORDS = 715
EXPECTED_UNIQUE_SEQUENCE_HASHES = 686
EXPECTED_DUPLICATE_GROUP_ROWS = 54

PRIMARY_ASSAYS = ("Tm", "Tagg", "HIC", "BVP", "AC-SINS")

# This is the exact 48-feature Phase 4B set used for the Jain benchmark.
# No feature is selected from AIntibody outcomes, and no paired score exists.
FROZEN_RULE_FEATURES = (
    "VH_calculated_score",
    "VL_calculated_score",
    "VH_rule_penalty",
    "VL_rule_penalty",
    "VH_total_sites",
    "VL_total_sites",
    "total_sites_combined",
    "VH_cdr_sites",
    "VL_cdr_sites",
    "cdr_sites_combined",
    "VH_ptm_sites",
    "VL_ptm_sites",
    "ptm_sites_combined",
    "VH_liability_sites",
    "VL_liability_sites",
    "liability_sites_combined",
    "VH_deamidation_count",
    "VH_isomerization_count",
    "VH_oxidation_count",
    "VH_glycosylation_count",
    "VH_o_glycosylation_count",
    "VL_deamidation_count",
    "VL_isomerization_count",
    "VL_oxidation_count",
    "VL_glycosylation_count",
    "VL_o_glycosylation_count",
    "deamidation_count_combined",
    "isomerization_count_combined",
    "oxidation_count_combined",
    "glycosylation_count_combined",
    "o_glycosylation_count_combined",
    "VH_cdr_deamidation_count",
    "VH_cdr_isomerization_count",
    "VH_cdr_oxidation_count",
    "VH_cdr_glycosylation_count",
    "VH_cdr_o_glycosylation_count",
    "VL_cdr_deamidation_count",
    "VL_cdr_isomerization_count",
    "VL_cdr_oxidation_count",
    "VL_cdr_glycosylation_count",
    "VL_cdr_o_glycosylation_count",
    "cdr_deamidation_count_combined",
    "cdr_isomerization_count_combined",
    "cdr_oxidation_count_combined",
    "cdr_glycosylation_count_combined",
    "cdr_o_glycosylation_count_combined",
    "VH_length",
    "VL_length",
)

CONTROL_FEATURES = ("VH_length", "VL_length")

PRIMARY_ASSOCIATION_STATISTIC = "Spearman rho"
PRIMARY_MULTIPLE_TESTING = "Benjamini-Hochberg FDR"
PRIMARY_Q_THRESHOLD = 0.05
EXPLORATORY_Q_THRESHOLD = 0.10

PRIMARY_CLASSIFICATION_METRICS = ("ROC-AUC", "PR-AUC")
SECONDARY_CLASSIFICATION_METRICS = (
    "sensitivity",
    "specificity",
    "precision",
    "recall",
    "F1",
)

PRIMARY_ANALYSIS_UNIT = "unique VH/VL sequence hash"
NO_PAIRED_SCORE = True
THRESHOLD_OPTIMIZATION_PROHIBITED = True
ML_TRAINING_PROHIBITED = True

FUTURE_DATA_OUTPUT_DIR = "validation/data/external_validation"
FUTURE_REPORT_OUTPUT_DIR = "validation/reports/aintibody_external"
