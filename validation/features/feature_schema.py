"""Schema and production-to-validation mappings for rule features.

This module describes the shape of extracted tables. It does not implement
any scientific rule. Sequence analysis and scoring are delegated to the
production ``core`` and ``scoring`` modules by the extractor.
"""

from __future__ import annotations

from typing import Any

import pandas as pd

from core import RISK_MOTIFS
from scoring import CDR_REGIONS, PTM_CATEGORIES


# Keep the same CDR configuration used by the existing batch/Desktop path.
# This is workflow configuration, not a second CDR implementation.
CDR_ARGS = (31, 35, 50, 65, 99, 110)

DATASET_FEATURE_FILENAMES = {
    "jain_2017": "jain_rule_features.csv",
    "aintibody_2026": "aintibody_rule_features.csv",
}

REGION_COUNT_FIELDS = (
    "total_sites",
    "cdr_sites",
    "framework_sites",
    "ptm_sites",
    "liability_sites",
)

# These are the categories currently emitted by core.py. The right-hand
# names are validation column names; the source category remains unchanged in
# risk_sites.csv and in the feature dictionary.
CATEGORY_FIELD_MAP = {
    "脱酰胺化": "deamidation_count",
    "异构化": "isomerization_count",
    "氧化": "oxidation_count",
    "N-糖基化": "glycosylation_count",
    "O-糖基化": "o_glycosylation_count",
}

PRODUCTION_CATEGORIES = tuple(RISK_MOTIFS) + tuple(
    category for category in sorted(PTM_CATEGORIES) if category not in RISK_MOTIFS
)

CHAIN_IDENTITY_FIELDS = (
    "dataset",
    "record_id",
    "antibody_id",
    "sequence_hash",
    "chain",
    "sequence_length",
    "sequence_status",
    "analysis_status",
    "analysis_error",
)

CHAIN_NATIVE_FIELDS = (
    "calculated_score",
    "risk_level",
)

CHAIN_DERIVED_FIELDS = (
    "rule_penalty",
    *REGION_COUNT_FIELDS,
    *CATEGORY_FIELD_MAP.values(),
    *(f"cdr_{field}" for field in CATEGORY_FIELD_MAP.values()),
)

CHAIN_COLUMNS = (
    *CHAIN_IDENTITY_FIELDS,
    *CHAIN_NATIVE_FIELDS,
    *CHAIN_DERIVED_FIELDS,
)

ANTIBODY_IDENTITY_FIELDS = (
    "dataset",
    "record_id",
    "antibody_id",
    "sequence_hash",
    "sequence_status",
    "analysis_status",
    "analysis_error",
)

ANTIBODY_CHAIN_FIELDS = tuple(
    f"{chain}_{field}"
    for chain in ("VH", "VL")
    for field in ("length", "calculated_score", "rule_penalty", *REGION_COUNT_FIELDS, *CATEGORY_FIELD_MAP.values(), *(f"cdr_{field}" for field in CATEGORY_FIELD_MAP.values()))
)

ANTIBODY_COMBINED_FIELDS = (
    "total_sites_combined",
    "cdr_sites_combined",
    "framework_sites_combined",
    "ptm_sites_combined",
    "liability_sites_combined",
    *(f"{field}_combined" for field in CATEGORY_FIELD_MAP.values()),
    *(f"cdr_{field}_combined" for field in CATEGORY_FIELD_MAP.values()),
)

ANTIBODY_COLUMNS = (
    *ANTIBODY_IDENTITY_FIELDS,
    *ANTIBODY_CHAIN_FIELDS,
    *ANTIBODY_COMBINED_FIELDS,
)

RISK_SITE_COLUMNS = (
    "dataset",
    "record_id",
    "antibody_id",
    "sequence_hash",
    "chain",
    "position",
    "motif",
    "category",
    "region",
    "description",
    "context",
    "evidence_level",
)


def feature_dictionary_frame() -> pd.DataFrame:
    """Return the documented schema without reading experimental values."""

    rows: list[dict[str, Any]] = []

    def add(name: str, level: str, source: str, description: str, direction: str, kind: str, notes: str = "") -> None:
        rows.append({
            "feature_name": name,
            "level": level,
            "source_function": source,
            "description": description,
            "direction": direction,
            "derived_or_native": kind,
            "notes": notes,
        })

    for name in CHAIN_IDENTITY_FIELDS:
        source = "processed validation input" if name not in {"sequence_status", "analysis_status", "analysis_error"} else "validation.features.extract_rule_features"
        add(name, "chain", source, "Record identity or explicit analysis status.", "not applicable", "input/derived")
    add("calculated_score", "chain", "scoring.compute_risk_score", "Existing production rule score.", "higher = lower rule penalty", "native")
    add("risk_level", "chain", "scoring.compute_risk_score", "Existing production risk-level label.", "production label", "native")
    add("rule_penalty", "chain", "validation derived", "100 - calculated_score.", "higher = greater rule-derived penalty", "derived", "Validation convenience field; never fed back into production scoring.")

    for name in REGION_COUNT_FIELDS:
        add(name, "chain", "validation.features.extract_rule_features", f"Count of production risk sites in {name.replace('_', ' ')}.", "higher = more detected sites", "derived")
    for category, field in CATEGORY_FIELD_MAP.items():
        add(field, "chain", "validation.features.extract_rule_features", f"Count of production risk sites with category {category}.", "higher = more detected sites", "derived", f"Production category: {category}.")
        add(f"cdr_{field}", "chain", "validation.features.extract_rule_features", f"Count of {category} sites in CDR1/CDR2/CDR3.", "higher = more detected sites", "derived", f"Production category: {category}.")

    for name in ANTIBODY_COLUMNS:
        if name in ANTIBODY_IDENTITY_FIELDS:
            continue
        if name.startswith("VH_") or name.startswith("VL_"):
            add(name, "antibody", "validation.features.extract_rule_features", "Chain-specific feature retained without combining chain scores.", "as documented by chain feature", "derived", "VH and VL are analyzed independently.")
        else:
            add(name, "antibody", "validation.features.extract_rule_features", "Safe sum of corresponding VH and VL count features.", "higher = more detected sites", "derived", "No paired score is invented.")

    for name in RISK_SITE_COLUMNS:
        add(name, "risk_site", "core.analyze_sequence", "One row per detected production RiskItem.", "not applicable", "native/traceability")

    return pd.DataFrame(rows, columns=[
        "feature_name", "level", "source_function", "description",
        "direction", "derived_or_native", "notes",
    ]).drop_duplicates(subset=["feature_name"], keep="first").reset_index(drop=True)
