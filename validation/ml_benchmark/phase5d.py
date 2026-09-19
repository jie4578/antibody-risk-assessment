"""One-time frozen TEST evaluation for the Phase 5C-selected models.

The runner opens the sealed TEST labels exactly once after verifying the
Phase 5C checkpoint, selected configurations, and label SHA256.  No model
selection, threshold tuning, or alternative representation is implemented.
"""

from __future__ import annotations

import hashlib
import json
import warnings
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Mapping

import numpy as np
import pandas as pd
from scipy.stats import spearmanr
from sklearn.exceptions import ConvergenceWarning
from sklearn.linear_model import LogisticRegression, Ridge
from sklearn.metrics import average_precision_score, mean_absolute_error, mean_squared_error, r2_score, roc_auc_score
from sklearn.pipeline import Pipeline
from sklearn.preprocessing import StandardScaler

from validation.ml_benchmark.esm2_embeddings import file_sha256
from validation.ml_benchmark.phase5c import (
    BENCHMARK_NAME,
    ENDPOINTS,
    FEATURE_BLOCKS,
    FEATURE_DIMENSIONS,
    PHASE_5B_MODEL,
    PHASE_5B_REVISION,
    ROOT,
    _canonical_target,
    build_feature_blocks,
    load_phase5c_data,
    load_rule_features,
)


PHASE_5C_COMMIT = "83ec67429640fcdeb142f6dc52711a51a834eda1"
EXPECTED_TEST_LABEL_SHA256 = "36e802f6c3d615b5f636bb1186c03e24421b2e3b004f0e7e249ace4b3673fca3"
EXPECTED_TEST_EMBEDDING_SHA256 = "5e64dc87c447914f73bad7cabde79216822dd3be2e9458ad2f538534f23512e1"
TEST_LABEL_PATH = "validation/data/ml_benchmark/entity_exact_v1/sealed_test_labels.csv"
TEST_FEATURE_PATH = "validation/data/ml_benchmark/entity_exact_v1/test_features.csv"
TEST_SIMILARITY_PATH = "validation/data/ml_benchmark/entity_exact_v1/test_similarity_audit.csv"
EMBEDDING_DIR = "validation/data/ml_benchmark/entity_exact_v1/embeddings"
FINAL_OUTPUT_DIR = "validation/data/ml_benchmark/entity_exact_v1/final_test"
REPORT_PATH = "validation/reports/ml_benchmark/phase5d_final_test_report.md"
CONFIG_PATH = "validation/data/ml_benchmark/entity_exact_v1/modeling/selected_model_config.json"
BOOTSTRAP_SEED = 20260919
BOOTSTRAP_RESAMPLES = 2000
TEST_N = 95
NOVELTY_BIN_COUNTS = {"BIN_2": 11, "BIN_3": 35, "BIN_4": 49}
NOVELTY_BIN_LABELS = {
    "BIN_2": "0.80–<0.90",
    "BIN_3": "0.90–<0.95",
    "BIN_4": "0.95–<1.00",
}
TEST_LABEL_COLUMNS = ("sequence_hash", *ENDPOINTS, "total_developability_score", "composite_class")


class Phase5DError(RuntimeError):
    """Raised when the one-time frozen TEST evaluation cannot proceed."""


class Phase5DSealMismatch(Phase5DError):
    """Raised before TEST labels are opened when the seal does not match."""


def verify_test_seal(path: str | Path) -> str:
    actual = file_sha256(path)
    if actual != EXPECTED_TEST_LABEL_SHA256:
        raise Phase5DSealMismatch("TEST_SEAL_MISMATCH")
    return actual


def _load_selected_config(root: str | Path) -> dict[str, Any]:
    config = json.loads((Path(root) / CONFIG_PATH).read_text(encoding="utf-8"))
    expected_continuous = {f"{endpoint}|{block}" for endpoint in ENDPOINTS for block in FEATURE_BLOCKS}
    if set(config.get("continuous_selected", {})) != expected_continuous:
        raise Phase5DError("Phase 5C continuous selected configuration set changed")
    if set(config.get("classification_selected", {})) != set(FEATURE_BLOCKS):
        raise Phase5DError("Phase 5C classification selected configuration set changed")
    if tuple(config.get("feature_blocks", ())) != FEATURE_BLOCKS:
        raise Phase5DError("Phase 5C feature blocks changed")
    if config.get("test_labels_accessed") or config.get("test_predictions_created") or config.get("test_metrics_calculated"):
        raise Phase5DError("Phase 5C config already contains TEST results")
    return config


def _load_test_features(root: str | Path) -> pd.DataFrame:
    path = Path(root) / TEST_FEATURE_PATH
    frame = pd.read_csv(path, dtype=str, usecols=["sequence_hash", "VH", "VL", "split"])
    if len(frame) != TEST_N or set(frame["split"]) != {"TEST"}:
        raise Phase5DError("Frozen TEST feature population is not 95 rows")
    if frame["sequence_hash"].duplicated().any():
        raise Phase5DError("Frozen TEST features contain duplicate sequence_hash values")
    return frame.drop(columns=["split"])


def _load_novelty(root: str | Path, sequence_hashes: list[str]) -> pd.DataFrame:
    path = Path(root) / TEST_SIMILARITY_PATH
    novelty = pd.read_csv(path, dtype=str, usecols=["sequence_hash", "novelty_bin"])
    if len(novelty) != TEST_N or novelty["sequence_hash"].duplicated().any():
        raise Phase5DError("Frozen TEST novelty audit is not a unique 95-row table")
    if novelty.groupby("novelty_bin").size().to_dict() != NOVELTY_BIN_COUNTS:
        raise Phase5DError("Frozen TEST novelty bin counts changed")
    if set(novelty["sequence_hash"]) != set(sequence_hashes):
        raise Phase5DError("Frozen TEST novelty hashes do not align")
    return novelty.set_index("sequence_hash").loc[sequence_hashes].reset_index()


def _load_test_embeddings(root: str | Path, sequence_hashes: list[str]) -> np.ndarray:
    directory = Path(root) / EMBEDDING_DIR
    manifest = json.loads((directory / "embedding_manifest.json").read_text(encoding="utf-8"))
    if manifest.get("model_name") != PHASE_5B_MODEL or manifest.get("resolved_model_revision") != PHASE_5B_REVISION:
        raise Phase5DError("Frozen TEST embedding provenance changed")
    path = directory / "test_esm2_embeddings.npz"
    actual_hash = file_sha256(path)
    if actual_hash != EXPECTED_TEST_EMBEDDING_SHA256:
        raise Phase5DError("TEST embedding SHA256 mismatch")
    if manifest["splits"]["TEST"]["embedding_file_sha256"] != actual_hash:
        raise Phase5DError("TEST embedding manifest SHA256 mismatch")
    with np.load(path, allow_pickle=False) as data:
        hashes = data["sequence_hashes"].astype(str).tolist()
        paired = np.asarray(data["paired_embeddings"], dtype=np.float32)
    if len(hashes) != TEST_N or paired.shape != (TEST_N, FEATURE_DIMENSIONS["ESM2"]):
        raise Phase5DError("Frozen TEST embedding shape changed")
    if set(hashes) != set(sequence_hashes) or len(set(hashes)) != len(hashes):
        raise Phase5DError("Frozen TEST embedding hashes do not align")
    lookup = {value: index for index, value in enumerate(hashes)}
    return paired[[lookup[value] for value in sequence_hashes]]


def _build_test_blocks(root: str | Path, features: pd.DataFrame) -> dict[str, np.ndarray]:
    sequence_hashes = features["sequence_hash"].tolist()
    rule = load_rule_features(root, set(sequence_hashes))
    length = np.column_stack([features["VH"].str.len().to_numpy(dtype=float), features["VL"].str.len().to_numpy(dtype=float)])
    rule_values = rule.loc[sequence_hashes].to_numpy(dtype=float)
    esm = _load_test_embeddings(root, sequence_hashes)
    blocks = {
        "LENGTH_CONTROL": length,
        "RULE48": rule_values,
        "ESM2": esm,
        "ESM2_PLUS_RULE48": np.hstack([esm, rule_values]),
    }
    if {name: value.shape[1] for name, value in blocks.items()} != FEATURE_DIMENSIONS:
        raise Phase5DError("TEST feature dimensions changed")
    return blocks


def _load_test_labels_once(path: str | Path, sequence_hashes: list[str]) -> pd.DataFrame:
    labels = pd.read_csv(path, dtype=str, usecols=list(TEST_LABEL_COLUMNS))
    if len(labels) != TEST_N or labels["sequence_hash"].duplicated().any():
        raise Phase5DError("TEST labels do not contain exactly 95 unique rows")
    if set(labels["sequence_hash"]) != set(sequence_hashes):
        raise Phase5DError("TEST labels do not align with TEST features")
    expected = _canonical_target(labels["total_developability_score"]).fillna("MISSING").astype(str)
    provided = labels["composite_class"].fillna("MISSING").astype(str)
    if not np.array_equal(expected.to_numpy(), provided.to_numpy()):
        raise Phase5DError("TEST composite labels do not match the frozen threshold")
    counts = provided.value_counts().to_dict()
    if counts.get("DEVELOPABLE", 0) != 63 or counts.get("NOT_DEVELOPABLE", 0) != 32:
        raise Phase5DError(f"Unexpected TEST composite composition: {counts}")
    return labels


def _fit_final_pipeline(estimator: Any, x_train: np.ndarray, y_train: np.ndarray) -> tuple[Pipeline, list[str], bool]:
    pipeline = Pipeline([("scaler", StandardScaler()), ("estimator", estimator)])
    with warnings.catch_warnings(record=True) as caught:
        warnings.simplefilter("always")
        pipeline.fit(x_train, y_train)
    convergence = not any(issubclass(item.category, ConvergenceWarning) for item in caught)
    return pipeline, [str(item.message) for item in caught], convergence


def _spearman(y_true: np.ndarray, prediction: np.ndarray) -> float:
    if len(np.unique(y_true)) < 2 or len(np.unique(prediction)) < 2:
        return float("nan")
    value = spearmanr(y_true, prediction).statistic
    return float(value) if np.isfinite(value) else float("nan")


def _bootstrap_continuous(y_true: np.ndarray, prediction: np.ndarray) -> list[dict[str, Any]]:
    rng = np.random.default_rng(BOOTSTRAP_SEED)
    values: list[tuple[float, float, float]] = []
    for _ in range(BOOTSTRAP_RESAMPLES):
        indices = rng.integers(0, len(y_true), size=len(y_true))
        rho = _spearman(y_true[indices], prediction[indices])
        mae = float(mean_absolute_error(y_true[indices], prediction[indices]))
        rmse = float(mean_squared_error(y_true[indices], prediction[indices]) ** 0.5)
        if np.isfinite(rho) and np.isfinite(mae) and np.isfinite(rmse):
            values.append((rho, mae, rmse))
    array = np.asarray(values, dtype=float)
    estimates = {
        "Spearman rho": _spearman(y_true, prediction),
        "MAE": float(mean_absolute_error(y_true, prediction)),
        "RMSE": float(mean_squared_error(y_true, prediction) ** 0.5),
    }
    output = []
    for index, metric in enumerate(("Spearman rho", "MAE", "RMSE")):
        output.append({
            "metric": metric,
            "estimate": estimates[metric],
            "ci_low": float(np.percentile(array[:, index], 2.5)),
            "ci_high": float(np.percentile(array[:, index], 97.5)),
            "bootstrap_valid_n": int(len(array)),
        })
    return output


def _bootstrap_classification(y_true: np.ndarray, prediction: np.ndarray) -> list[dict[str, Any]]:
    rng = np.random.default_rng(BOOTSTRAP_SEED)
    positive = np.flatnonzero(y_true == 1)
    negative = np.flatnonzero(y_true == 0)
    values: list[tuple[float, float]] = []
    for _ in range(BOOTSTRAP_RESAMPLES):
        indices = np.concatenate([
            rng.choice(positive, size=len(positive), replace=True),
            rng.choice(negative, size=len(negative), replace=True),
        ])
        pr_auc = float(average_precision_score(y_true[indices], prediction[indices]))
        roc_auc = float(roc_auc_score(y_true[indices], prediction[indices]))
        if np.isfinite(pr_auc) and np.isfinite(roc_auc):
            values.append((pr_auc, roc_auc))
    array = np.asarray(values, dtype=float)
    estimates = {
        "PR-AUC": float(average_precision_score(y_true, prediction)),
        "ROC-AUC": float(roc_auc_score(y_true, prediction)),
    }
    output = []
    for index, metric in enumerate(("PR-AUC", "ROC-AUC")):
        output.append({
            "metric": metric,
            "estimate": estimates[metric],
            "ci_low": float(np.percentile(array[:, index], 2.5)),
            "ci_high": float(np.percentile(array[:, index], 97.5)),
            "bootstrap_valid_n": int(len(array)),
        })
    return output


def _json_safe(value: Any) -> Any:
    if isinstance(value, dict):
        return {str(key): _json_safe(item) for key, item in value.items()}
    if isinstance(value, list):
        return [_json_safe(item) for item in value]
    if isinstance(value, tuple):
        return [_json_safe(item) for item in value]
    if isinstance(value, (np.floating, np.integer)):
        return value.item()
    return value


def _fmt(value: Any) -> str:
    if value is None or (isinstance(value, float) and not np.isfinite(value)):
        return "NA"
    return f"{float(value):.6f}" if isinstance(value, (float, np.floating)) else str(value)


def _novelty_results(
    novelty: pd.DataFrame,
    continuous_predictions: Mapping[tuple[str, str], np.ndarray],
    classification_predictions: Mapping[str, np.ndarray],
    labels: pd.DataFrame,
) -> pd.DataFrame:
    rows = []
    label_by_hash = labels.set_index("sequence_hash")
    for block_endpoint, prediction in continuous_predictions.items():
        block, endpoint = block_endpoint
        for novelty_bin, group in novelty.groupby("novelty_bin", sort=True):
            hashes = group["sequence_hash"].tolist()
            y = pd.to_numeric(label_by_hash.loc[hashes, endpoint], errors="coerce")
            mask = y.notna().to_numpy()
            yv = y.to_numpy(dtype=float)[mask]
            pv = prediction[[novelty["sequence_hash"].tolist().index(value) for value in hashes]][mask]
            estimable = len(yv) >= 15
            rows.append({
                "task": "continuous",
                "endpoint": endpoint,
                "feature_block": block,
                "novelty_bin": novelty_bin,
                "novelty_range": NOVELTY_BIN_LABELS[novelty_bin],
                "n": int(len(yv)),
                "positive_n": "",
                "negative_n": "",
                "spearman": _spearman(yv, pv) if estimable else "NOT_ESTIMABLE",
                "mae": float(mean_absolute_error(yv, pv)) if estimable else "NOT_ESTIMABLE",
                "rmse": float(mean_squared_error(yv, pv) ** 0.5) if estimable else "NOT_ESTIMABLE",
                "pr_auc": "",
                "roc_auc": "",
                "status": "ESTIMABLE" if estimable else "NOT_ESTIMABLE",
            })
    for block, prediction in classification_predictions.items():
        for novelty_bin, group in novelty.groupby("novelty_bin", sort=True):
            hashes = group["sequence_hash"].tolist()
            y = (label_by_hash.loc[hashes, "composite_class"].astype(str) == "NOT_DEVELOPABLE").astype(int).to_numpy()
            pv = prediction[[novelty["sequence_hash"].tolist().index(value) for value in hashes]]
            positive_n, negative_n = int(y.sum()), int((y == 0).sum())
            estimable = positive_n >= 5 and negative_n >= 5
            rows.append({
                "task": "classification",
                "endpoint": "composite",
                "feature_block": block,
                "novelty_bin": novelty_bin,
                "novelty_range": NOVELTY_BIN_LABELS[novelty_bin],
                "n": int(len(y)),
                "positive_n": positive_n,
                "negative_n": negative_n,
                "spearman": "",
                "mae": "",
                "rmse": "",
                "pr_auc": float(average_precision_score(y, pv)) if estimable else "NOT_ESTIMABLE",
                "roc_auc": float(roc_auc_score(y, pv)) if estimable else "NOT_ESTIMABLE",
                "status": "ESTIMABLE" if estimable else "NOT_ESTIMABLE",
            })
    return pd.DataFrame(rows)


def _render_report(
    path: Path,
    continuous: pd.DataFrame,
    classification: pd.DataFrame,
    comparisons: pd.DataFrame,
    bootstrap: pd.DataFrame,
    novelty: pd.DataFrame,
    manifest: Mapping[str, Any],
) -> None:
    lines = [
        "# Phase 5D One-Time Sealed TEST Evaluation",
        "",
        f"Benchmark: `{BENCHMARK_NAME}`. Phase 5C checkpoint: `{PHASE_5C_COMMIT}`.",
        "",
        f"TEST evaluation number: **{manifest['TEST_EVALUATION_NUMBER']}**. TEST seal matched before opening labels. TEST labels were opened once for this authorized evaluation.",
        "",
        "This is an internal duplicate/entity-controlled benchmark, not family-independent generalization. The frozen TEST set has high residual similarity to TRAIN: 84/95 at paired-min ≥0.90, 49/95 at ≥0.95, and 21/95 at ≥0.98.",
        "",
        "Selected Phase 5C hyperparameters were used unchanged. Preprocessing was fit only on TRAIN+VALIDATION. No TEST-driven tuning, threshold optimization, PCA, or ESM fine-tuning occurred.",
        "",
        "## Final continuous TEST results",
        "",
        "| Endpoint | Block | Validation rho | TEST rho | Delta | 95% CI rho | MAE | RMSE | R² | N |",
        "|---|---|---:|---:|---:|---|---:|---:|---:|---:|",
    ]
    for row in continuous.itertuples(index=False):
        ci = bootstrap[(bootstrap.task == "continuous") & (bootstrap.endpoint == row.endpoint) & (bootstrap.feature_block == row.feature_block) & (bootstrap.metric == "Spearman rho")].iloc[0]
        lines.append(f"| {row.endpoint} | {row.feature_block} | {_fmt(row.validation_spearman)} | {_fmt(row.test_spearman)} | {_fmt(row.test_minus_validation_spearman)} | [{_fmt(ci.ci_low)}, {_fmt(ci.ci_high)}] | {_fmt(row.test_mae)} | {_fmt(row.test_rmse)} | {_fmt(row.test_r2)} | {row.test_n} |")
    lines.extend(["", "## Final classification TEST results", "", "| Block | Validation PR-AUC | TEST PR-AUC | Delta | 95% CI | Validation ROC-AUC | TEST ROC-AUC | Delta | N | Positive N | Negative N |", "|---|---:|---:|---:|---|---:|---:|---:|---:|---:|---:|"])
    for row in classification.itertuples(index=False):
        ci = bootstrap[(bootstrap.task == "classification") & (bootstrap.feature_block == row.feature_block) & (bootstrap.metric == "PR-AUC")].iloc[0]
        lines.append(f"| {row.feature_block} | {_fmt(row.validation_pr_auc)} | {_fmt(row.test_pr_auc)} | {_fmt(row.test_minus_validation_pr_auc)} | [{_fmt(ci.ci_low)}, {_fmt(ci.ci_high)}] | {_fmt(row.validation_roc_auc)} | {_fmt(row.test_roc_auc)} | {_fmt(row.test_minus_validation_roc_auc)} | {row.test_n} | {row.positive_n} | {row.negative_n} |")
    lines.extend(["", "## Novelty-stratified secondary analysis", "", "Novelty bins were frozen before evaluation and were not used for model selection. Results with insufficient N or class counts are marked `NOT_ESTIMABLE`.", "", "| Task | Endpoint | Block | Bin | N | Spearman | PR-AUC | ROC-AUC | Status |", "|---|---|---|---|---:|---:|---:|---:|---|"])
    for row in novelty.itertuples(index=False):
        lines.append(f"| {row.task} | {row.endpoint} | {row.feature_block} | {row.novelty_range} | {row.n} | {row.spearman} | {row.pr_auc} | {row.roc_auc} | {row.status} |")
    lines.extend(["", "## Frozen interpretation", "", "- All primary TEST results use the complete frozen TEST population; no TEST rows were filtered.", "- Negative rho, negative R², weak PR-AUC, and validation-to-TEST declines are preserved.", "- This evaluation does not support distant sequence-family generalization or broad clinical developability prediction.", "- TEST evaluation was performed once; no retraining or configuration changes followed label access."])
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text("\n".join(lines) + "\n", encoding="utf-8")


def run_phase5d(root: str | Path = ROOT) -> dict[str, Any]:
    root = Path(root)
    output_dir = root / FINAL_OUTPUT_DIR
    manifest_path = output_dir / "final_test_manifest.json"
    marker_path = output_dir / "evaluation_1_started.json"
    if manifest_path.exists() or marker_path.exists():
        raise Phase5DError("Phase 5D evaluation #1 already started or completed; no rerun permitted")
    config = _load_selected_config(root)
    test_label_path = root / TEST_LABEL_PATH
    test_label_sha256 = verify_test_seal(test_label_path)
    opened_at = datetime.now(timezone.utc).isoformat()
    output_dir.mkdir(parents=True, exist_ok=True)
    marker_path.write_text(json.dumps({"TEST_EVALUATION_NUMBER": 1, "test_open_timestamp": opened_at}) + "\n", encoding="utf-8")

    test_features = _load_test_features(root)
    novelty = _load_novelty(root, test_features["sequence_hash"].tolist())
    data = load_phase5c_data(root)
    train_blocks, validation_blocks, _ = build_feature_blocks(root, data)
    test_blocks = _build_test_blocks(root, test_features)
    final_blocks = {name: np.vstack([train_blocks[name], validation_blocks[name]]) for name in FEATURE_BLOCKS}
    final_data = pd.concat([data["TRAIN"], data["VALIDATION"]], ignore_index=True)
    if len(final_data) != 381:
        raise Phase5DError("Final TRAIN+VALIDATION population is not 381 rows")

    # This is the single authorized opening of TEST label values.
    test_labels = _load_test_labels_once(test_label_path, test_features["sequence_hash"].tolist())
    test_hashes = test_features["sequence_hash"].tolist()
    continuous_rows = []
    bootstrap_rows = []
    continuous_predictions: dict[tuple[str, str], np.ndarray] = {}
    for endpoint in ENDPOINTS:
        y_all = pd.to_numeric(final_data[endpoint], errors="coerce")
        train_mask = y_all.notna().to_numpy()
        y_train = y_all.loc[train_mask].to_numpy(dtype=float)
        test_y_all = pd.to_numeric(test_labels[endpoint], errors="coerce")
        test_mask = test_y_all.notna().to_numpy()
        for block in FEATURE_BLOCKS:
            key = f"{endpoint}|{block}"
            alpha = float(config["continuous_selected"][key]["alpha"])
            pipeline, warning_messages, converged = _fit_final_pipeline(Ridge(alpha=alpha), final_blocks[block][train_mask], y_train)
            if not converged:
                raise Phase5DError(f"Final continuous model did not converge: {key}")
            prediction = pipeline.predict(test_blocks[block])
            metric_prediction = prediction[test_mask]
            metric_y = test_y_all.to_numpy(dtype=float)[test_mask]
            test_spearman = _spearman(metric_y, metric_prediction)
            row = {
                "endpoint": endpoint,
                "feature_block": block,
                "alpha": alpha,
                "validation_spearman": float(config["continuous_selected"][key]["validation_spearman"]),
                "test_spearman": test_spearman,
                "test_minus_validation_spearman": test_spearman - float(config["continuous_selected"][key]["validation_spearman"]),
                "test_mae": float(mean_absolute_error(metric_y, metric_prediction)),
                "test_rmse": float(mean_squared_error(metric_y, metric_prediction) ** 0.5),
                "test_r2": float(r2_score(metric_y, metric_prediction)),
                "test_n": int(len(metric_y)),
                "converged": converged,
                "warnings": " | ".join(warning_messages),
            }
            continuous_rows.append(row)
            for interval in _bootstrap_continuous(metric_y, metric_prediction):
                bootstrap_rows.append({"task": "continuous", "endpoint": endpoint, "feature_block": block, **interval})
            continuous_predictions[(block, endpoint)] = prediction

    classification_rows = []
    classification_predictions: dict[str, np.ndarray] = {}
    final_target = final_data["composite_class"].astype(str)
    train_mask = final_target.isin(["DEVELOPABLE", "NOT_DEVELOPABLE"]).to_numpy()
    train_y = (final_target.loc[train_mask] == "NOT_DEVELOPABLE").astype(int).to_numpy()
    test_y = (test_labels["composite_class"].astype(str) == "NOT_DEVELOPABLE").astype(int).to_numpy()
    for block in FEATURE_BLOCKS:
        c_value = float(config["classification_selected"][block]["C"])
        estimator = LogisticRegression(C=c_value, penalty="l2", solver="lbfgs", max_iter=5000, class_weight=None, random_state=20260919)
        pipeline, warning_messages, converged = _fit_final_pipeline(estimator, final_blocks[block][train_mask], train_y)
        if not converged:
            raise Phase5DError(f"Final classification model did not converge: {block}")
        prediction = pipeline.predict_proba(test_blocks[block])[:, 1]
        test_pr_auc = float(average_precision_score(test_y, prediction))
        test_roc_auc = float(roc_auc_score(test_y, prediction))
        selected = config["classification_selected"][block]
        classification_rows.append({
            "feature_block": block,
            "C": c_value,
            "validation_pr_auc": float(selected["validation_pr_auc"]),
            "test_pr_auc": test_pr_auc,
            "test_minus_validation_pr_auc": test_pr_auc - float(selected["validation_pr_auc"]),
            "validation_roc_auc": float(selected["validation_roc_auc"]),
            "test_roc_auc": test_roc_auc,
            "test_minus_validation_roc_auc": test_roc_auc - float(selected["validation_roc_auc"]),
            "test_n": int(len(test_y)),
            "positive_n": int(test_y.sum()),
            "negative_n": int((test_y == 0).sum()),
            "positive_prevalence": float(test_y.mean()),
            "converged": converged,
            "warnings": " | ".join(warning_messages),
        })
        for interval in _bootstrap_classification(test_y, prediction):
            bootstrap_rows.append({"task": "classification", "endpoint": "composite", "feature_block": block, **interval})
        classification_predictions[block] = prediction

    continuous_frame = pd.DataFrame(continuous_rows)
    classification_frame = pd.DataFrame(classification_rows)
    bootstrap_frame = pd.DataFrame(bootstrap_rows)
    comparison_rows = []
    for row in continuous_rows:
        comparison_rows.append({"task": "continuous", "endpoint": row["endpoint"], "feature_block": row["feature_block"], "validation_primary": row["validation_spearman"], "test_primary": row["test_spearman"], "test_minus_validation": row["test_minus_validation_spearman"], "metric": "Spearman rho"})
    for row in classification_rows:
        comparison_rows.append({"task": "classification", "endpoint": "composite", "feature_block": row["feature_block"], "validation_primary": row["validation_pr_auc"], "test_primary": row["test_pr_auc"], "test_minus_validation": row["test_minus_validation_pr_auc"], "metric": "PR-AUC"})
    comparison_frame = pd.DataFrame(comparison_rows)
    summary_rows = []
    for endpoint in ENDPOINTS:
        current = continuous_frame[continuous_frame["endpoint"] == endpoint].set_index("feature_block")
        for block in FEATURE_BLOCKS:
            summary_rows.append({"task": "continuous", "endpoint": endpoint, "feature_block": block, "test_spearman": float(current.loc[block, "test_spearman"]), "delta_vs_length": float(current.loc[block, "test_spearman"] - current.loc["LENGTH_CONTROL", "test_spearman"]), "delta_vs_esm2": float(current.loc[block, "test_spearman"] - current.loc["ESM2", "test_spearman"])})
    current_class = classification_frame.set_index("feature_block")
    for block in FEATURE_BLOCKS:
        summary_rows.append({"task": "classification", "endpoint": "composite", "feature_block": block, "test_pr_auc": float(current_class.loc[block, "test_pr_auc"]), "test_roc_auc": float(current_class.loc[block, "test_roc_auc"]), "delta_pr_auc_vs_esm2": float(current_class.loc[block, "test_pr_auc"] - current_class.loc["ESM2", "test_pr_auc"]), "delta_roc_auc_vs_esm2": float(current_class.loc[block, "test_roc_auc"] - current_class.loc["ESM2", "test_roc_auc"])})
    summary_frame = pd.DataFrame(summary_rows)

    prediction_continuous_rows = []
    for (block, endpoint), prediction in continuous_predictions.items():
        prediction_continuous_rows.extend({"sequence_hash": sequence_hash, "endpoint": endpoint, "feature_block": block, "prediction": float(value)} for sequence_hash, value in zip(test_hashes, prediction))
    prediction_classification_rows = []
    for block, prediction in classification_predictions.items():
        prediction_classification_rows.extend({"sequence_hash": sequence_hash, "feature_block": block, "probability_NOT_DEVELOPABLE": float(value)} for sequence_hash, value in zip(test_hashes, prediction))
    prediction_continuous_frame = pd.DataFrame(prediction_continuous_rows)
    prediction_classification_frame = pd.DataFrame(prediction_classification_rows)
    novelty_frame = _novelty_results(novelty, continuous_predictions, classification_predictions, test_labels)

    output_dir.mkdir(parents=True, exist_ok=True)
    continuous_frame.to_csv(output_dir / "continuous_test_results.csv", index=False, lineterminator="\n")
    classification_frame.to_csv(output_dir / "classification_test_results.csv", index=False, lineterminator="\n")
    comparison_frame.to_csv(output_dir / "validation_test_comparison.csv", index=False, lineterminator="\n")
    summary_frame.to_csv(output_dir / "representation_test_summary.csv", index=False, lineterminator="\n")
    bootstrap_frame.to_csv(output_dir / "bootstrap_confidence_intervals.csv", index=False, lineterminator="\n")
    prediction_continuous_frame.to_csv(output_dir / "test_predictions_continuous.csv", index=False, lineterminator="\n")
    prediction_classification_frame.to_csv(output_dir / "test_predictions_classification.csv", index=False, lineterminator="\n")
    novelty_frame.to_csv(output_dir / "test_novelty_results.csv", index=False, lineterminator="\n")
    final_manifest = {
        "benchmark": BENCHMARK_NAME,
        "phase5c_commit": PHASE_5C_COMMIT,
        "test_label_sha256": test_label_sha256,
        "test_open_timestamp": opened_at,
        "TEST_EVALUATION_NUMBER": 1,
        "feature_blocks": FEATURE_BLOCKS,
        "feature_dimensions": FEATURE_DIMENSIONS,
        "selected_hyperparameters": {"continuous": {key: value["alpha"] for key, value in config["continuous_selected"].items()}, "classification": {key: value["C"] for key, value in config["classification_selected"].items()}},
        "model_families": {"continuous": "Ridge", "classification": "LogisticRegression"},
        "training_population": {"rows_before_endpoint_missingness": int(len(final_data)), "source": "TRAIN+VALIDATION"},
        "test_population": {"rows": TEST_N, "positive_n": int(test_y.sum()), "negative_n": int((test_y == 0).sum())},
        "bootstrap_seed": BOOTSTRAP_SEED,
        "bootstrap_resamples": BOOTSTRAP_RESAMPLES,
        "threshold_optimization": False,
        "test_rows_filtered": False,
        "test_driven_iteration": False,
    }
    manifest_path.write_text(json.dumps(_json_safe(final_manifest), indent=2) + "\n", encoding="utf-8")
    _render_report(root / REPORT_PATH, continuous_frame, classification_frame, comparison_frame, bootstrap_frame, novelty_frame, final_manifest)
    marker_path.unlink()
    return {"manifest": manifest_path, "report": root / REPORT_PATH, "continuous": continuous_frame, "classification": classification_frame, "bootstrap": bootstrap_frame, "novelty": novelty_frame}
