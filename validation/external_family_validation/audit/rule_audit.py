"""Compare frozen RULE48 distributions at the unique paired-sequence unit."""

from __future__ import annotations

from pathlib import Path
from typing import Any

import pandas as pd

from validation.external_validation_spec import FROZEN_RULE_FEATURES
from validation.features.extract_rule_features import extract_features
from validation.schemas.dataset_schema import sequence_hash


ROOT = Path(__file__).resolve().parents[3]
EXTERNAL_NORMALIZED = ROOT / "validation/external_family_validation/data/processed/sabdab2_normalized.csv"
INTERNAL_FEATURES = ROOT / "validation/data/features/aintibody_rule_features.csv"
INTERNAL_SITES = ROOT / "validation/data/features/risk_sites.csv"
INTERNAL_SPLIT_DIR = ROOT / "validation/data/ml_benchmark/entity_exact_v1"
COUNT_FEATURES = tuple(
    feature for feature in FROZEN_RULE_FEATURES
    if feature.endswith("_sites") or feature.endswith("_combined") or feature.endswith("_count")
)


def load_external_pairs(path: str | Path = EXTERNAL_NORMALIZED) -> pd.DataFrame:
    """Read only identity/sequences, then select one valid row per paired hash."""

    columns = ["dataset", "record_id", "antibody_id", "VH", "VL", "sequence_status", "sequence_hash"]
    frame = pd.read_csv(path, usecols=columns, dtype=str, keep_default_na=False)
    valid = frame.loc[frame["sequence_status"].eq("VALID") & frame["VH"].ne("") & frame["VL"].ne("")]
    pairs = valid.sort_values(["sequence_hash", "record_id"], kind="mergesort").drop_duplicates("sequence_hash").reset_index(drop=True)
    if any(sequence_hash(row.VH, row.VL) != row.sequence_hash for row in pairs.itertuples(index=False)):
        raise ValueError("SAbDab2 normalized sequence hash mismatch")
    return pairs


def load_internal_hashes(split_dir: str | Path = INTERNAL_SPLIT_DIR) -> set[str]:
    """Read only hashes from the frozen TRAIN and VALIDATION populations."""

    base = Path(split_dir)
    train = pd.read_csv(base / "train_population.csv", usecols=["sequence_hash"], dtype=str)
    validation = pd.read_csv(base / "validation_features.csv", usecols=["sequence_hash"], dtype=str)
    hashes = set(train["sequence_hash"]) | set(validation["sequence_hash"])
    if len(train) != 285 or len(validation) != 96 or len(hashes) != 381:
        raise ValueError("Frozen TRAIN/VALIDATION identity population changed")
    return hashes


def load_internal_rule_tables(
    hashes: set[str],
    features_path: str | Path = INTERNAL_FEATURES,
    sites_path: str | Path = INTERNAL_SITES,
) -> tuple[pd.DataFrame, pd.DataFrame]:
    """Select the existing Phase 4B features/sites without reading outcomes."""

    columns = ["sequence_hash", *FROZEN_RULE_FEATURES]
    features = pd.read_csv(features_path, usecols=columns)
    selected = features.loc[features["sequence_hash"].isin(hashes)].copy()
    if set(selected["sequence_hash"]) != hashes:
        raise ValueError("Frozen internal RULE48 hashes are incomplete")
    if selected.duplicated("sequence_hash").any():
        disagreement = selected.groupby("sequence_hash", sort=False)[list(FROZEN_RULE_FEATURES)].nunique(dropna=False).gt(1).any(axis=1)
        if disagreement.any():
            raise ValueError("Duplicate internal sequence hashes disagree on RULE48")
    selected = selected.sort_values("sequence_hash", kind="mergesort").drop_duplicates("sequence_hash").reset_index(drop=True)

    site_columns = ["dataset", "sequence_hash", "chain", "position", "motif", "category", "region"]
    sites = pd.read_csv(sites_path, usecols=site_columns, dtype=str, keep_default_na=False)
    sites = sites.loc[sites["dataset"].eq("aintibody_2026") & sites["sequence_hash"].isin(hashes)]
    sites = sites.drop_duplicates(["sequence_hash", "chain", "position", "motif", "category", "region"])
    return selected, sites.reset_index(drop=True)


def _distribution(values: pd.Series) -> dict[str, float | int | None]:
    numeric = pd.to_numeric(values, errors="coerce").dropna()
    if numeric.empty:
        return {"n": 0, "median": None, "q25": None, "q75": None, "mean": None}
    return {
        "n": int(len(numeric)),
        "median": float(numeric.median()),
        "q25": float(numeric.quantile(0.25)),
        "q75": float(numeric.quantile(0.75)),
        "mean": float(numeric.mean()),
    }


def summarize_rule_tables(features: pd.DataFrame, sites: pd.DataFrame) -> dict[str, Any]:
    if features["sequence_hash"].duplicated().any():
        raise ValueError("RULE48 summary requires unique sequence hashes")
    if not set(sites["sequence_hash"]).issubset(set(features["sequence_hash"])):
        raise ValueError("Risk sites contain unknown sequence hashes")
    n = len(features)
    prevalence = {}
    continuous = {}
    for feature in FROZEN_RULE_FEATURES:
        values = pd.to_numeric(features[feature], errors="coerce")
        if feature in COUNT_FEATURES:
            observed = values.dropna()
            nonzero = int(observed.gt(0).sum())
            prevalence[feature] = {
                "n": int(len(observed)),
                "nonzero_n": nonzero,
                "nonzero_fraction": nonzero / len(observed) if len(observed) else None,
                "mean_count": float(observed.mean()) if len(observed) else None,
            }
        else:
            continuous[feature] = _distribution(values)
    per_pair = sites.groupby("sequence_hash").size().reindex(features["sequence_hash"], fill_value=0)
    return {
        "unit": "unique valid paired VH/VL sequence_hash",
        "n": n,
        "feature_prevalence": prevalence,
        "continuous_feature_distribution": continuous,
        "sites_per_pair": _distribution(per_pair),
        "total_risk_sites": int(len(sites)),
        "site_category_counts": {str(k): int(v) for k, v in sites["category"].value_counts().items()},
        "region_counts": {str(k): int(v) for k, v in sites["region"].value_counts().items()},
        "chain_counts": {str(k): int(v) for k, v in sites["chain"].value_counts().items()},
        "cdr_sites": int(sites["region"].isin(["CDR1", "CDR2", "CDR3"]).sum()),
        "framework_sites": int(sites["region"].eq("FW").sum()),
    }


def run_rule_audit(
    external_pairs: pd.DataFrame,
    internal_hashes: set[str],
) -> tuple[dict[str, Any], pd.DataFrame, pd.DataFrame]:
    external_tables = extract_features(external_pairs, dataset="SAbDab2")
    if external_tables.audit["failed_analyses"] or external_tables.audit["partial_analyses"]:
        raise ValueError("Frozen rule extraction did not succeed for every selected external pair")
    external_features = external_tables.antibody.loc[:, ["sequence_hash", *FROZEN_RULE_FEATURES]].copy()
    external_sites = external_tables.risk_sites
    internal_features, internal_sites = load_internal_rule_tables(internal_hashes)
    summary = {
        "feature_set": "frozen Phase 4B RULE48",
        "feature_count": len(FROZEN_RULE_FEATURES),
        "feature_order": list(FROZEN_RULE_FEATURES),
        "external": summarize_rule_tables(external_features, external_sites),
        "internal_train_validation": summarize_rule_tables(internal_features, internal_sites),
        "limitations": [
            "Sequence-only distributions; no experimental outcome or predictor performance was evaluated.",
            "Structural sampling and selected internal population differ; this is descriptive only.",
        ],
    }
    return summary, external_features, external_sites
