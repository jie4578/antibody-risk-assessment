from __future__ import annotations

import ast
from pathlib import Path

import pandas as pd

from validation.ml_benchmark_spec import (
    ESM2_CHECKPOINT,
    ESM2_CONCATENATED_DIMENSION,
    FROZEN_SCIENTIFIC_BASELINE,
    FUTURE_MODELS,
    RULE48_FEATURES,
    rule48_feature_names_from_manifest,
)


ROOT = Path(__file__).resolve().parents[2]


def test_frozen_population_and_baseline_are_explicit() -> None:
    assert FROZEN_SCIENTIFIC_BASELINE == "d1487ed74bdfc52fb0b2015a25c4e91ee90af66d"
    primary = pd.read_csv(ROOT / "validation/data/external_validation/aintibody_primary_population.csv")
    assert len(primary) == 476
    assert primary["sequence_hash"].is_unique


def test_rule48_matches_existing_frozen_feature_manifest() -> None:
    assert len(RULE48_FEATURES) == 48
    assert rule48_feature_names_from_manifest() == RULE48_FEATURES


def test_esm2_contract_is_frozen_without_loading_model() -> None:
    assert ESM2_CHECKPOINT == "facebook/esm2_t30_150M_UR50D"
    assert ESM2_CONCATENATED_DIMENSION == 1280
    protocol = (ROOT / "validation/ml_benchmark_protocol.md").read_text(encoding="utf-8")
    assert "No ESM2 or other embedding is generated in Phase 5A." in protocol


def test_future_linear_model_contract_is_frozen() -> None:
    assert FUTURE_MODELS["Ridge"]["alpha"] == (0.01, 0.1, 1.0, 10.0, 100.0)
    assert FUTURE_MODELS["LogisticRegression"]["C"] == (0.01, 0.1, 1.0, 10.0, 100.0)
    assert FUTURE_MODELS["LogisticRegression"]["max_iter"] == (5000,)
    assert FUTURE_MODELS["LogisticRegression"]["class_weight"] == (None,)
    protocol = (ROOT / "validation/ml_benchmark_protocol.md").read_text(encoding="utf-8")
    for phrase in ("StandardScaler", "Spearman rho", "PR-AUC", "Phase 5D", "post-hoc oxidation/HIC-only feature subset"):
        assert phrase in protocol


def test_phase_5a_modules_do_not_import_estimators_or_production_scientific_code() -> None:
    paths = [
        ROOT / "validation/ml_benchmark_spec.py",
        ROOT / "validation/ml_benchmark/similarity.py",
        ROOT / "validation/ml_benchmark/split.py",
        ROOT / "validation/run_ml_benchmark_split.py",
    ]
    forbidden = {"sklearn", "torch", "transformers", "esm", "core", "scoring"}
    for path in paths:
        tree = ast.parse(path.read_text(encoding="utf-8"))
        imported = {
            alias.name.split(".")[0]
            for node in ast.walk(tree)
            if isinstance(node, ast.Import)
            for alias in node.names
        }
        imported.update(
            node.module.split(".")[0]
            for node in ast.walk(tree)
            if isinstance(node, ast.ImportFrom) and node.module
        )
        assert not imported.intersection(forbidden), (path, imported.intersection(forbidden))
        source = path.read_text(encoding="utf-8").lower()
        assert "roc_auc" not in source
        assert ".fit(" not in source
        assert ".predict(" not in source
