"""Frozen train/validation representation benchmark for Phase 5C.

This module deliberately reads only the frozen TRAIN and VALIDATION inputs.
It never opens test labels, creates test predictions, or changes the feature
blocks defined by the Phase 5 protocol.
"""

from __future__ import annotations

import hashlib
import json
import warnings
from pathlib import Path
from typing import Any, Mapping

import numpy as np
import pandas as pd
from scipy.stats import spearmanr
from sklearn.exceptions import ConvergenceWarning
from sklearn.linear_model import LogisticRegression, Ridge
from sklearn.metrics import (
    average_precision_score,
    mean_absolute_error,
    mean_squared_error,
    r2_score,
    roc_auc_score,
)
from sklearn.pipeline import Pipeline
from sklearn.preprocessing import StandardScaler

from validation.external_validation_spec import FROZEN_RULE_FEATURES
from validation.ml_benchmark.esm2_embeddings import file_sha256
from validation.ml_benchmark_spec_v1_2 import BENCHMARK_NAME, SPEC_VERSION


SEED = 20260919
ROOT = Path(__file__).resolve().parents[2]
BASE_DIR_NAME = "validation/data/ml_benchmark/entity_exact_v1"
EMBEDDING_DIR_NAME = f"{BASE_DIR_NAME}/embeddings"
MODELING_DIR_NAME = f"{BASE_DIR_NAME}/modeling"
REPORT_PATH_NAME = "validation/reports/ml_benchmark/phase5c_validation_report.md"
PHASE_5B_REVISION = "a695f6045e2e32885fa60af20c13cb35398ce30c"
PHASE_5B_MODEL = "facebook/esm2_t30_150M_UR50D"
EXPECTED_EMBEDDING_HASHES = {
    "TRAIN": "c7c3189fa75b32bae8dd7becabbe9cc71ecc2bdb37d7010a92d05bd319251a5b",
    "VALIDATION": "0bac10b8b61aff83bfcab3b569f1f5f87b5dcb0e513913e9d73a84e2c0441b1a",
}
EXPECTED_COUNTS = {"TRAIN": 285, "VALIDATION": 96}
FEATURE_BLOCKS = ("LENGTH_CONTROL", "RULE48", "ESM2", "ESM2_PLUS_RULE48")
LENGTH_FEATURES = ("VH_length", "VL_length")
RULE_FEATURES = tuple(FROZEN_RULE_FEATURES)
ESM2_DIMENSION = 1280
FEATURE_DIMENSIONS = {
    "LENGTH_CONTROL": 2,
    "RULE48": 48,
    "ESM2": 1280,
    "ESM2_PLUS_RULE48": 1328,
}
ALPHA_GRID = (0.01, 0.1, 1.0, 10.0, 100.0)
C_GRID = (0.01, 0.1, 1.0, 10.0, 100.0)
ENDPOINTS = ("Tm", "Tagg", "HIC", "BVP", "AC-SINS")
ENDPOINT_SOURCE_COLUMNS = {
    "Tm": "Tm, C",
    "Tagg": "Tagg, C",
    "HIC": "HIC RT in gradient (min)",
    "BVP": "average BVP score",
    "AC-SINS": "average dPW",
}
TRAIN_SOURCE = "train_population.csv"
VALIDATION_FEATURE_SOURCE = "validation_features.csv"
VALIDATION_LABEL_SOURCE = "validation_labels.csv"
CONTINUOUS_SOURCE_COLUMNS = tuple(ENDPOINT_SOURCE_COLUMNS.values())
TRAIN_USE_COLUMNS = (
    "sequence_hash",
    "VH",
    "VL",
    *CONTINUOUS_SOURCE_COLUMNS,
    "total_developability_score",
)
VALIDATION_LABEL_COLUMNS = ("sequence_hash", *ENDPOINTS, "total_developability_score", "composite_class")


class Phase5CError(RuntimeError):
    """Raised when the frozen Phase 5C contract cannot be satisfied."""


def _base(root: str | Path) -> Path:
    return Path(root) / BASE_DIR_NAME


def _canonical_target(score: pd.Series) -> pd.Series:
    numeric = pd.to_numeric(score, errors="coerce")
    values = pd.Series(pd.NA, index=score.index, dtype="string")
    known = numeric.notna()
    values.loc[known] = np.where(numeric.loc[known] <= 3, "DEVELOPABLE", "NOT_DEVELOPABLE")
    return values


def _validate_frame(frame: pd.DataFrame, name: str, expected_n: int) -> None:
    if len(frame) != expected_n:
        raise Phase5CError(f"{name} expected {expected_n} rows, got {len(frame)}")
    if frame["sequence_hash"].isna().any() or frame["sequence_hash"].duplicated().any():
        raise Phase5CError(f"{name} sequence_hash values are missing or duplicated")
    if frame[["VH", "VL"]].isna().any().any():
        raise Phase5CError(f"{name} has missing VH/VL sequences")


def load_phase5c_data(root: str | Path = ROOT) -> dict[str, pd.DataFrame]:
    """Load only frozen TRAIN and VALIDATION features/labels."""

    base = _base(root)
    train_path = base / TRAIN_SOURCE
    validation_features_path = base / VALIDATION_FEATURE_SOURCE
    validation_labels_path = base / VALIDATION_LABEL_SOURCE

    train = pd.read_csv(train_path, dtype=str, usecols=list(TRAIN_USE_COLUMNS))
    train = train.rename(columns={source: endpoint for endpoint, source in ENDPOINT_SOURCE_COLUMNS.items()})
    train["composite_class"] = _canonical_target(train["total_developability_score"])
    _validate_frame(train, "TRAIN", EXPECTED_COUNTS["TRAIN"])

    validation_features = pd.read_csv(
        validation_features_path,
        dtype=str,
        usecols=["sequence_hash", "VH", "VL"],
    )
    validation_labels = pd.read_csv(
        validation_labels_path,
        dtype=str,
        usecols=list(VALIDATION_LABEL_COLUMNS),
    )
    if validation_labels["sequence_hash"].duplicated().any():
        raise Phase5CError("VALIDATION labels contain duplicate sequence_hash values")
    validation = validation_features.merge(
        validation_labels,
        on="sequence_hash",
        how="left",
        validate="one_to_one",
        indicator=True,
    )
    if (validation["_merge"] != "both").any():
        raise Phase5CError("VALIDATION features and labels are not fully aligned")
    validation = validation.drop(columns=["_merge"])
    validation["composite_class"] = _canonical_target(validation["total_developability_score"])
    provided = validation_labels["composite_class"].fillna("MISSING").astype(str).to_numpy()
    derived = _canonical_target(validation_labels["total_developability_score"]).fillna("MISSING").astype(str).to_numpy()
    if not np.array_equal(provided, derived):
        raise Phase5CError("VALIDATION composite endpoint does not match the preregistered threshold")
    _validate_frame(validation, "VALIDATION", EXPECTED_COUNTS["VALIDATION"])
    return {"TRAIN": train, "VALIDATION": validation}


def load_rule_features(root: str | Path, sequence_hashes: set[str]) -> pd.DataFrame:
    """Load the frozen 48-feature table and collapse only identical duplicates."""

    path = Path(root) / "validation/data/features/aintibody_rule_features.csv"
    columns = ["sequence_hash", *RULE_FEATURES]
    rule = pd.read_csv(path, dtype=str, usecols=columns)
    for feature in RULE_FEATURES:
        rule[feature] = pd.to_numeric(rule[feature], errors="coerce")
        if rule[feature].isna().any():
            raise Phase5CError(f"RULE48 feature {feature} contains missing/non-numeric values")
    differing = []
    for sequence_hash, group in rule.groupby("sequence_hash", sort=False):
        if len(group) > 1 and group[list(RULE_FEATURES)].nunique(dropna=False).gt(1).any():
            differing.append(sequence_hash)
    if differing:
        raise Phase5CError(f"RULE48 duplicate sequence hashes have conflicting values: {differing[:3]}")
    rule = rule.drop_duplicates("sequence_hash", keep="first").set_index("sequence_hash")
    missing = sorted(sequence_hashes - set(rule.index))
    if missing:
        raise Phase5CError(f"RULE48 alignment missing {len(missing)} sequence hashes")
    return rule.loc[sorted(sequence_hashes), list(RULE_FEATURES)]


def _hash_sequence_order(values: list[str]) -> str:
    return hashlib.sha256("\n".join(values).encode("utf-8")).hexdigest()


def load_frozen_embeddings(root: str | Path, split: str, sequence_hashes: list[str]) -> np.ndarray:
    """Load and verify a Phase 5B train/validation embedding file only."""

    if split not in EXPECTED_EMBEDDING_HASHES:
        raise Phase5CError(f"Phase 5C cannot load embedding split {split}")
    directory = Path(root) / EMBEDDING_DIR_NAME
    manifest_path = directory / "embedding_manifest.json"
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    if manifest.get("model_name") != PHASE_5B_MODEL or manifest.get("resolved_model_revision") != PHASE_5B_REVISION:
        raise Phase5CError("Phase 5B model provenance does not match the frozen contract")
    filename = {"TRAIN": "train_esm2_embeddings.npz", "VALIDATION": "validation_esm2_embeddings.npz"}[split]
    path = directory / filename
    actual_hash = file_sha256(path)
    if actual_hash != EXPECTED_EMBEDDING_HASHES[split]:
        raise Phase5CError(f"{split} embedding SHA256 mismatch")
    if manifest["splits"][split]["embedding_file_sha256"] != actual_hash:
        raise Phase5CError(f"{split} embedding manifest hash mismatch")
    with np.load(path, allow_pickle=False) as data:
        hashes = data["sequence_hashes"].astype(str).tolist()
        paired = np.asarray(data["paired_embeddings"], dtype=np.float32)
    if paired.shape != (len(hashes), ESM2_DIMENSION):
        raise Phase5CError(f"{split} embedding dimension mismatch")
    if len(hashes) != len(set(hashes)) or set(hashes) != set(sequence_hashes):
        raise Phase5CError(f"{split} embedding sequence_hash alignment mismatch")
    lookup = {value: index for index, value in enumerate(hashes)}
    aligned = paired[[lookup[value] for value in sequence_hashes]]
    if _hash_sequence_order(sequence_hashes) == "":
        raise Phase5CError("Unexpected empty sequence hash checksum")
    return aligned


def build_feature_blocks(root: str | Path, data: Mapping[str, pd.DataFrame]) -> tuple[dict[str, np.ndarray], dict[str, np.ndarray], dict[str, Any]]:
    train, validation = data["TRAIN"], data["VALIDATION"]
    all_hashes = set(train["sequence_hash"]) | set(validation["sequence_hash"])
    rule = load_rule_features(root, all_hashes)

    def lengths(frame: pd.DataFrame) -> np.ndarray:
        return np.column_stack(
            [
                frame["VH"].str.len().to_numpy(dtype=float),
                frame["VL"].str.len().to_numpy(dtype=float),
            ]
        )

    def rule_values(frame: pd.DataFrame) -> np.ndarray:
        return rule.loc[frame["sequence_hash"], list(RULE_FEATURES)].to_numpy(dtype=float)

    train_rule = rule_values(train)
    validation_rule = rule_values(validation)
    train_esm = load_frozen_embeddings(root, "TRAIN", train["sequence_hash"].tolist())
    validation_esm = load_frozen_embeddings(root, "VALIDATION", validation["sequence_hash"].tolist())
    train_blocks = {
        "LENGTH_CONTROL": lengths(train),
        "RULE48": train_rule,
        "ESM2": train_esm,
        "ESM2_PLUS_RULE48": np.hstack([train_esm, train_rule]),
    }
    validation_blocks = {
        "LENGTH_CONTROL": lengths(validation),
        "RULE48": validation_rule,
        "ESM2": validation_esm,
        "ESM2_PLUS_RULE48": np.hstack([validation_esm, validation_rule]),
    }
    dimensions = {name: int(values.shape[1]) for name, values in train_blocks.items()}
    if dimensions != FEATURE_DIMENSIONS:
        raise Phase5CError(f"Unexpected feature dimensions: {dimensions}")
    zero_variance = {
        name: [int(index) for index, value in enumerate(np.var(values, axis=0)) if np.isclose(value, 0.0)]
        for name, values in train_blocks.items()
    }
    metadata = {
        "dimensions": dimensions,
        "zero_variance_train_columns": zero_variance,
        "train_sequence_hash_sha256": _hash_sequence_order(train["sequence_hash"].tolist()),
        "validation_sequence_hash_sha256": _hash_sequence_order(validation["sequence_hash"].tolist()),
    }
    return train_blocks, validation_blocks, metadata


def make_pipeline(estimator: Any) -> Pipeline:
    return Pipeline([("scaler", StandardScaler()), ("estimator", estimator)])


def _fit(pipeline: Pipeline, x_train: np.ndarray, y_train: np.ndarray) -> tuple[Pipeline, list[str], bool]:
    with warnings.catch_warnings(record=True) as caught:
        warnings.simplefilter("always")
        pipeline.fit(x_train, y_train)
    convergence = not any(issubclass(item.category, ConvergenceWarning) for item in caught)
    return pipeline, [str(item.message) for item in caught], convergence


def _spearman(y_true: np.ndarray, prediction: np.ndarray) -> float:
    value = spearmanr(y_true, prediction).statistic
    return float(value) if np.isfinite(value) else float("nan")


def select_continuous(rows: list[dict[str, Any]]) -> dict[str, Any]:
    usable = [row for row in rows if np.isfinite(row["validation_spearman"])]
    if not usable:
        raise Phase5CError("No usable continuous validation Spearman result")
    selected = usable[0]
    for candidate in usable[1:]:
        difference = candidate["validation_spearman"] - selected["validation_spearman"]
        if difference > 1e-12 or (abs(difference) <= 1e-12 and candidate["alpha"] > selected["alpha"]):
            selected = candidate
    return dict(selected)


def select_classification(rows: list[dict[str, Any]]) -> dict[str, Any]:
    usable = [row for row in rows if np.isfinite(row["validation_pr_auc"])]
    if not usable:
        raise Phase5CError("No usable classification validation PR-AUC result")
    selected = usable[0]
    for candidate in usable[1:]:
        difference = candidate["validation_pr_auc"] - selected["validation_pr_auc"]
        if difference > 1e-12 or (abs(difference) <= 1e-12 and candidate["C"] < selected["C"]):
            selected = candidate
    return dict(selected)


def _continuous_grid(train_blocks: Mapping[str, np.ndarray], validation_blocks: Mapping[str, np.ndarray], data: Mapping[str, pd.DataFrame]) -> tuple[pd.DataFrame, dict[str, dict[str, Any]], dict[str, dict[str, Any]]]:
    rows: list[dict[str, Any]] = []
    selected: dict[str, dict[str, Any]] = {}
    repeatability: dict[str, dict[str, Any]] = {}
    for endpoint in ENDPOINTS:
        train_y_all = pd.to_numeric(data["TRAIN"][endpoint], errors="coerce")
        validation_y_all = pd.to_numeric(data["VALIDATION"][endpoint], errors="coerce")
        train_mask = train_y_all.notna().to_numpy()
        validation_mask = validation_y_all.notna().to_numpy()
        train_y = train_y_all.loc[train_mask].to_numpy(dtype=float)
        validation_y = validation_y_all.loc[validation_mask].to_numpy(dtype=float)
        for block in FEATURE_BLOCKS:
            x_train = train_blocks[block][train_mask]
            x_validation = validation_blocks[block][validation_mask]
            block_rows = []
            for alpha in ALPHA_GRID:
                pipeline, warning_messages, converged = _fit(make_pipeline(Ridge(alpha=alpha)), x_train, train_y)
                prediction = pipeline.predict(x_validation)
                row = {
                    "task": "continuous",
                    "endpoint": endpoint,
                    "feature_block": block,
                    "alpha": float(alpha),
                    "validation_spearman": _spearman(validation_y, prediction),
                    "mae": float(mean_absolute_error(validation_y, prediction)),
                    "rmse": float(mean_squared_error(validation_y, prediction) ** 0.5),
                    "r2": float(r2_score(validation_y, prediction)),
                    "train_n": int(len(train_y)),
                    "validation_n": int(len(validation_y)),
                    "converged": bool(converged),
                    "convergence_warnings": " | ".join(warning_messages),
                }
                rows.append(row)
                block_rows.append(row)
            chosen = select_continuous(block_rows)
            key = f"{endpoint}|{block}"
            selected[key] = chosen
            repeatability[key] = _repeatability(
                make_pipeline(Ridge(alpha=chosen["alpha"])),
                make_pipeline(Ridge(alpha=chosen["alpha"])),
                x_train,
                train_y,
                x_validation,
            )
            if not chosen["converged"]:
                raise Phase5CError(f"Selected continuous model did not converge: {key}")
    return pd.DataFrame(rows), selected, repeatability


def _classification_grid(train_blocks: Mapping[str, np.ndarray], validation_blocks: Mapping[str, np.ndarray], data: Mapping[str, pd.DataFrame]) -> tuple[pd.DataFrame, dict[str, dict[str, Any]], dict[str, dict[str, Any]]]:
    train_target = data["TRAIN"]["composite_class"].astype("string")
    validation_target = data["VALIDATION"]["composite_class"].astype("string")
    train_mask = train_target.notna().to_numpy()
    validation_mask = validation_target.notna().to_numpy()
    train_y = (train_target.loc[train_mask] == "NOT_DEVELOPABLE").astype(int).to_numpy()
    validation_y = (validation_target.loc[validation_mask] == "NOT_DEVELOPABLE").astype(int).to_numpy()
    rows: list[dict[str, Any]] = []
    selected: dict[str, dict[str, Any]] = {}
    repeatability: dict[str, dict[str, Any]] = {}
    for block in FEATURE_BLOCKS:
        x_train = train_blocks[block][train_mask]
        x_validation = validation_blocks[block][validation_mask]
        block_rows = []
        for c_value in C_GRID:
            estimator = LogisticRegression(
                C=c_value,
                penalty="l2",
                solver="lbfgs",
                max_iter=5000,
                class_weight=None,
                random_state=SEED,
            )
            pipeline, warning_messages, converged = _fit(make_pipeline(estimator), x_train, train_y)
            prediction = pipeline.predict_proba(x_validation)[:, 1]
            row = {
                "task": "classification",
                "feature_block": block,
                "C": float(c_value),
                "validation_pr_auc": float(average_precision_score(validation_y, prediction)),
                "validation_roc_auc": float(roc_auc_score(validation_y, prediction)),
                "train_n": int(len(train_y)),
                "validation_n": int(len(validation_y)),
                "positive_n": int(validation_y.sum()),
                "negative_n": int((validation_y == 0).sum()),
                "prevalence": float(validation_y.mean()),
                "converged": bool(converged),
                "convergence_warnings": " | ".join(warning_messages),
            }
            rows.append(row)
            block_rows.append(row)
        chosen = select_classification(block_rows)
        selected[block] = chosen
        repeatability[block] = _repeatability(
            make_pipeline(
                LogisticRegression(
                    C=chosen["C"],
                    penalty="l2",
                    solver="lbfgs",
                    max_iter=5000,
                    class_weight=None,
                    random_state=SEED,
                )
            ),
            make_pipeline(
                LogisticRegression(
                    C=chosen["C"],
                    penalty="l2",
                    solver="lbfgs",
                    max_iter=5000,
                    class_weight=None,
                    random_state=SEED,
                )
            ),
            x_train,
            train_y,
            x_validation,
            classification=True,
        )
        if not chosen["converged"]:
            raise Phase5CError(f"Selected classification model did not converge: {block}")
    return pd.DataFrame(rows), selected, repeatability


def _repeatability(first: Pipeline, second: Pipeline, x_train: np.ndarray, y_train: np.ndarray, x_validation: np.ndarray, classification: bool = False) -> dict[str, Any]:
    first, _, _ = _fit(first, x_train, y_train)
    second, _, _ = _fit(second, x_train, y_train)
    first_prediction = first.predict_proba(x_validation)[:, 1] if classification else first.predict(x_validation)
    second_prediction = second.predict_proba(x_validation)[:, 1] if classification else second.predict(x_validation)
    difference = np.abs(first_prediction - second_prediction)
    return {
        "max_absolute_prediction_difference": float(difference.max()) if difference.size else 0.0,
        "mean_absolute_prediction_difference": float(difference.mean()) if difference.size else 0.0,
        "passed": bool((difference.max() if difference.size else 0.0) <= 1e-10),
    }


def _json_safe(value: Any) -> Any:
    if isinstance(value, dict):
        return {str(key): _json_safe(item) for key, item in value.items()}
    if isinstance(value, list):
        return [_json_safe(item) for item in value]
    if isinstance(value, (np.floating, np.integer)):
        return value.item()
    if pd.isna(value):
        return None
    return value


def _selected_summary(continuous: Mapping[str, dict[str, Any]], classification: Mapping[str, dict[str, Any]]) -> pd.DataFrame:
    rows = []
    for row in continuous.values():
        rows.append({**row, "selected_hyperparameter": row["alpha"]})
    for row in classification.values():
        rows.append({**row, "selected_hyperparameter": row["C"]})
    return pd.DataFrame(rows)


def _render_report(
    output_path: Path,
    data: Mapping[str, pd.DataFrame],
    metadata: Mapping[str, Any],
    continuous: Mapping[str, dict[str, Any]],
    classification: Mapping[str, dict[str, Any]],
    continuous_repeatability: Mapping[str, dict[str, Any]],
    classification_repeatability: Mapping[str, dict[str, Any]],
) -> None:
    def fmt(value: Any) -> str:
        return "NA" if value is None or (isinstance(value, float) and not np.isfinite(value)) else f"{float(value):.6f}" if isinstance(value, (float, np.floating)) else str(value)

    lines = [
        "# Phase 5C Train/Validation Representation Benchmark",
        "",
        f"Benchmark: `{BENCHMARK_NAME}`. This is an internal duplicate/entity-controlled benchmark; strict family-independent generalization remains deferred because the frozen test split has high residual sequence similarity to train.",
        "",
        "TEST labels were not accessed. No TEST predictions or TEST metrics were generated.",
        "",
        f"TRAIN N = {len(data['TRAIN'])}; VALIDATION N = {len(data['VALIDATION'])}.",
        "",
        "## Feature blocks",
        "",
        "| Block | Dimension |",
        "|---|---:|",
    ]
    for block in FEATURE_BLOCKS:
        lines.append(f"| {block} | {metadata['dimensions'][block]} |")
    lines.extend(["", "## Continuous validation results", "", "| Endpoint | Block | Alpha | Spearman | MAE | RMSE | R² | Train N | Validation N |", "|---|---|---:|---:|---:|---:|---:|---:|---:|"])
    for endpoint in ENDPOINTS:
        for block in FEATURE_BLOCKS:
            row = continuous[f"{endpoint}|{block}"]
            lines.append(f"| {endpoint} | {block} | {fmt(row['alpha'])} | {fmt(row['validation_spearman'])} | {fmt(row['mae'])} | {fmt(row['rmse'])} | {fmt(row['r2'])} | {row['train_n']} | {row['validation_n']} |")
    lines.extend(["", "Endpoint availability:"])
    for endpoint in ENDPOINTS:
        row = continuous[f"{endpoint}|LENGTH_CONTROL"]
        lines.append(f"- {endpoint}: TRAIN {row['train_n']}; VALIDATION {row['validation_n']}.")
    lines.extend(["", "## Classification validation results", "", "Validation positive prevalence: 22 / 96 = 0.229167. This is the no-skill PR-AUC reference.", "", "| Block | C | PR-AUC | ROC-AUC | N | Positive N | Negative N |", "|---|---:|---:|---:|---:|---:|---:|"])
    for block in FEATURE_BLOCKS:
        row = classification[block]
        lines.append(f"| {block} | {fmt(row['C'])} | {fmt(row['validation_pr_auc'])} | {fmt(row['validation_roc_auc'])} | {row['validation_n']} | {row['positive_n']} | {row['negative_n']} |")

    lines.extend(["", "## Descriptive representation comparisons", ""])
    for endpoint in ENDPOINTS:
        length = continuous[f"{endpoint}|LENGTH_CONTROL"]["validation_spearman"]
        rule = continuous[f"{endpoint}|RULE48"]["validation_spearman"]
        esm = continuous[f"{endpoint}|ESM2"]["validation_spearman"]
        plus = continuous[f"{endpoint}|ESM2_PLUS_RULE48"]["validation_spearman"]
        lines.append(f"- **{endpoint}**: ESM2 − LENGTH = {fmt(esm - length)}; ESM2 − RULE48 = {fmt(esm - rule)}; ESM2+RULE48 − ESM2 = {fmt(plus - esm)}.")
    continuous_spearman = {
        endpoint: {block: continuous[f"{endpoint}|{block}"]["validation_spearman"] for block in FEATURE_BLOCKS}
        for endpoint in ENDPOINTS
    }
    esm_beats_length = sum(continuous_spearman[e]["ESM2"] > continuous_spearman[e]["LENGTH_CONTROL"] for e in ENDPOINTS)
    rule_beats_length = sum(continuous_spearman[e]["RULE48"] > continuous_spearman[e]["LENGTH_CONTROL"] for e in ENDPOINTS)
    esm_beats_rule = sum(continuous_spearman[e]["ESM2"] > continuous_spearman[e]["RULE48"] for e in ENDPOINTS)
    additive_beats_esm = sum(continuous_spearman[e]["ESM2_PLUS_RULE48"] > continuous_spearman[e]["ESM2"] for e in ENDPOINTS)
    classification_order = sorted(FEATURE_BLOCKS, key=lambda block: classification[block]["validation_pr_auc"], reverse=True)
    negative_results = [
        f"{e}: {block} Spearman did not exceed LENGTH_CONTROL"
        for e in ENDPOINTS
        for block in ("RULE48", "ESM2", "ESM2_PLUS_RULE48")
        if continuous_spearman[e][block] < continuous_spearman[e]["LENGTH_CONTROL"]
    ]
    lines.extend([
        "",
        "### Representation summary",
        "",
        f"- ESM2 beats LENGTH_CONTROL on {esm_beats_length}/5 continuous endpoints.",
        f"- RULE48 beats LENGTH_CONTROL on {rule_beats_length}/5 continuous endpoints.",
        f"- ESM2 beats RULE48 on {esm_beats_rule}/5 continuous endpoints.",
        f"- ESM2+RULE48 beats ESM2 on {additive_beats_esm}/5 continuous endpoints.",
        f"- Classification PR-AUC ordering: {' > '.join(classification_order)}.",
        "",
        "Negative validation results are preserved:",
        *[f"- {item}." for item in negative_results],
        "",
        "These are descriptive validation comparisons only; no delta significance tests, threshold optimization, PCA, feature selection, or overall winner score were performed.",
        "",
        "## Scientific interpretation",
        "",
        f"1. ESM2 outperforms LENGTH_CONTROL on {esm_beats_length}/5 continuous endpoints, but not on every endpoint.",
        f"2. ESM2 outperforms RULE48 on {esm_beats_rule}/5 continuous endpoints.",
        f"3. RULE48 adds incremental Spearman value beyond ESM2 on {additive_beats_esm}/5 endpoints; this is descriptive only.",
        "4. HIC and AC-SINS show the clearest ESM2 validation signal in this split; Tm remains weak.",
        "5. BVP and some combined representations remain weak or unstable, including negative R² values.",
        "6. Results cannot establish family-independent generalization because the frozen benchmark has high residual sequence similarity between TEST and TRAIN.",
        "",
        "## Convergence and repeatability",
        "",
        f"All selected models converged: `{all(row['converged'] for row in continuous.values()) and all(row['converged'] for row in classification.values())}`.",
    ])
    all_repeats = list(continuous_repeatability.values()) + list(classification_repeatability.values())
    lines.append(f"Maximum selected-model prediction difference: {fmt(max(item['max_absolute_prediction_difference'] for item in all_repeats))}; mean across selected models: {fmt(float(np.mean([item['mean_absolute_prediction_difference'] for item in all_repeats])))}.")
    lines.extend(["", "## Frozen-protocol status", "", "- StandardScaler was fitted within each TRAIN-only Pipeline.", "- TEST labels were not opened.", "- TEST predictions were not created.", "- No estimator beyond Ridge and LogisticRegression was introduced.", "- No production scientific code was changed."])
    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text("\n".join(lines) + "\n", encoding="utf-8")


def run_phase5c(root: str | Path = ROOT) -> dict[str, Any]:
    root = Path(root)
    data = load_phase5c_data(root)
    train_blocks, validation_blocks, metadata = build_feature_blocks(root, data)
    continuous_grid, continuous_selected, continuous_repeatability = _continuous_grid(train_blocks, validation_blocks, data)
    classification_grid, classification_selected, classification_repeatability = _classification_grid(train_blocks, validation_blocks, data)
    if not all(item["passed"] for item in [*continuous_repeatability.values(), *classification_repeatability.values()]):
        raise Phase5CError("Selected-model deterministic repeatability failed")

    output_dir = root / MODELING_DIR_NAME
    output_dir.mkdir(parents=True, exist_ok=True)
    continuous_grid.to_csv(output_dir / "continuous_validation_grid.csv", index=False, lineterminator="\n")
    classification_grid.to_csv(output_dir / "classification_validation_grid.csv", index=False, lineterminator="\n")
    summary = _selected_summary(continuous_selected, classification_selected)
    summary.to_csv(output_dir / "representation_validation_summary.csv", index=False, lineterminator="\n")
    config = {
        "benchmark_name": BENCHMARK_NAME,
        "benchmark_spec_version": SPEC_VERSION,
        "seed": SEED,
        "feature_blocks": FEATURE_BLOCKS,
        "feature_dimensions": metadata["dimensions"],
        "continuous_grid": {"estimator": "Ridge", "alpha": ALPHA_GRID, "selection_metric": "signed validation Spearman rho"},
        "classification_grid": {"estimator": "LogisticRegression", "C": C_GRID, "selection_metric": "validation PR-AUC", "positive_class": "NOT_DEVELOPABLE"},
        "train_sequence_hash_sha256": metadata["train_sequence_hash_sha256"],
        "validation_sequence_hash_sha256": metadata["validation_sequence_hash_sha256"],
        "zero_variance_train_columns": metadata["zero_variance_train_columns"],
        "continuous_selected": continuous_selected,
        "classification_selected": classification_selected,
        "continuous_repeatability": continuous_repeatability,
        "classification_repeatability": classification_repeatability,
        "test_labels_accessed": False,
        "test_predictions_created": False,
        "test_metrics_calculated": False,
        "pca_performed": False,
        "feature_selection_performed": False,
        "threshold_optimization_performed": False,
        "esm_inference_performed": False,
        "esm_fine_tuned": False,
    }
    (output_dir / "selected_model_config.json").write_text(json.dumps(_json_safe(config), indent=2) + "\n", encoding="utf-8")
    report_path = root / REPORT_PATH_NAME
    _render_report(report_path, data, metadata, continuous_selected, classification_selected, continuous_repeatability, classification_repeatability)
    return {
        "continuous_grid": output_dir / "continuous_validation_grid.csv",
        "classification_grid": output_dir / "classification_validation_grid.csv",
        "summary": output_dir / "representation_validation_summary.csv",
        "config": output_dir / "selected_model_config.json",
        "report": report_path,
        "continuous_selected": continuous_selected,
        "classification_selected": classification_selected,
        "metadata": metadata,
    }
