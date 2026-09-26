"""One-time preregistered GDPa3 HIC evaluation; no other assay is read."""

from __future__ import annotations

import hashlib
import json
import math
import subprocess
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import numpy as np
import pandas as pd
from openpyxl import load_workbook
from scipy import stats

from validation.schemas.dataset_schema import assess_sequences, sequence_hash


ROOT = Path(__file__).resolve().parents[2]
RAW_WORKBOOK = ROOT / "validation/external_developability/raw/GDPa3_20260106_full.xlsx"
PREDICTION_PATH = ROOT / "validation/data/external_developability/gdpa3_phase8b/gdpa3_hic_blind_predictions.csv"
SNAPSHOT_PATH = ROOT / "validation/data/external_developability/gdpa3_phase8a/gdpa3_hic_sequence_snapshot.csv"
MODEL_PATH = ROOT / "artifacts/ml_models/hic_esm2_v1.joblib"
SEAL_PATH = ROOT / "validation/external_developability/phase8b_prediction_seal.json"
RESULT_JSON_PATH = ROOT / "validation/external_developability/phase8c_hic_external_result.json"
RESULT_REPORT_PATH = ROOT / "validation/external_developability/PHASE8C_HIC_EXTERNAL_VALIDATION_RESULT.md"
OBSERVED_MARKER_PATH = ROOT / "validation/external_developability/PHASE8_GDPA3_HIC_OBSERVED.md"

EXPECTED_RAW_SHA256 = "06daa55cb609278574d008c5509d90a63f9a8f1aa3949f34fc50a2e654b008f7"
EXPECTED_PREDICTION_SHA256 = "9ffecbb2621b9760494f72ae94cb04a002a317cc75524785fc5a5efef645193f"
EXPECTED_SNAPSHOT_SHA256 = "5c41700df82dce43b8d379afbf054228818bf868f0ae4b89fa9270e8d1daf3e7"
EXPECTED_MODEL_SHA256 = "b6b05c0f5e45bf2b53ef5878bef8f248c3a7ce50ee7b78e5f8cd09044ca309b4"
EXPECTED_PHASE8B_SEAL_COMMIT = "025f3d44c87a614e47a681713d32707b47e92b6e"
EXPECTED_EVALUATION_N = 79
EXPECTED_SOURCE_N = 80
BOOTSTRAP_RESAMPLES = 2000
BOOTSTRAP_SEED = 20260926
SEQUENCE_SHEET = "Sequences"
AVERAGE_SHEET = "Assay Data - average"
SEQUENCE_COLUMNS = ("antibody_id", "vh_protein_sequence", "lc_protein_sequence")
PREDICTION_COLUMNS = ("antibody_id", "paired_hash", "hic_prediction", "model_version")
SNAPSHOT_COLUMNS = ("antibody_id", "VH", "VL", "VH_hash", "VL_hash", "paired_hash")
LABEL_COLUMNS = ("antibody_id", "paired_hash", "hic_rt_avg")
NOVELTY_BINS = {
    "<0.70": 71,
    "0.70–<0.80": 7,
    "0.80–<0.90": 1,
    ">=0.90": 0,
}


class Phase8CInputError(ValueError):
    """Raised when a frozen Phase 8C input or join fails integrity checks."""


def sha256_file(path: str | Path) -> str:
    digest = hashlib.sha256()
    with Path(path).open("rb") as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _find_one_header(header: tuple[Any, ...] | list[Any], required: str) -> int:
    positions = [index for index, value in enumerate(header) if value is not None and str(value) == required]
    if len(positions) != 1:
        raise Phase8CInputError(f"Workbook must contain exactly one {required!r} column")
    return positions[0]


def _read_column(worksheet: Any, column_index: int) -> list[Any]:
    return [row[0] for row in worksheet.iter_rows(min_row=2, min_col=column_index + 1, max_col=column_index + 1, values_only=True)]


def read_gdpa3_hic_label_table(
    workbook_path: str | Path,
    *,
    expected_raw_sha256: str = EXPECTED_RAW_SHA256,
    expected_n: int = EXPECTED_EVALUATION_N,
    expected_source_n: int = EXPECTED_SOURCE_N,
) -> pd.DataFrame:
    """Read only antibody IDs, paired sequence identity, and `hic_rt_avg`.

    The raw-file checksum is verified before openpyxl opens the workbook.
    Only the required three sequence columns and two HIC-sheet columns are
    read from data rows; no other assay cell values are loaded.
    """

    path = Path(workbook_path)
    if sha256_file(path) != expected_raw_sha256:
        raise Phase8CInputError("GDPa3 workbook SHA256 differs from the frozen source")

    workbook = load_workbook(path, read_only=True, data_only=True)
    try:
        if SEQUENCE_SHEET not in workbook.sheetnames or AVERAGE_SHEET not in workbook.sheetnames:
            raise Phase8CInputError("GDPa3 workbook is missing a preregistered HIC/sequence sheet")
        sequence_ws = workbook[SEQUENCE_SHEET]
        average_ws = workbook[AVERAGE_SHEET]
        sequence_header = next(sequence_ws.iter_rows(min_row=1, max_row=1, values_only=True))
        average_header = next(average_ws.iter_rows(min_row=1, max_row=1, values_only=True))

        sequence_indices = [_find_one_header(sequence_header, name) for name in SEQUENCE_COLUMNS]
        average_id_index = _find_one_header(average_header, "antibody_id")
        hic_index = _find_one_header(average_header, "hic_rt_avg")

        sequence_columns = [_read_column(sequence_ws, index) for index in sequence_indices]
        average_ids = _read_column(average_ws, average_id_index)
        hic_values = _read_column(average_ws, hic_index)
        if len(set(map(len, sequence_columns))) != 1 or len(average_ids) != len(hic_values):
            raise Phase8CInputError("GDPa3 required columns have inconsistent row lengths")

        sequence_by_id: dict[str, tuple[str, str, str]] = {}
        for antibody_id_raw, vh_raw, vl_raw in zip(*sequence_columns):
            if antibody_id_raw is None or str(antibody_id_raw) == "":
                if vh_raw not in (None, "") or vl_raw not in (None, ""):
                    raise Phase8CInputError("A GDPa3 sequence row has chains but no antibody identifier")
                continue
            antibody_id = str(antibody_id_raw)
            if antibody_id != antibody_id.strip():
                raise Phase8CInputError("GDPa3 antibody identifiers contain surrounding whitespace")
            vh, vl, status, _ = assess_sequences(vh_raw, vl_raw)
            if status != "VALID" or vh != str(vh_raw) or vl != str(vl_raw):
                raise Phase8CInputError("GDPa3 sequence row is not unchanged and valid under the frozen validator")
            if antibody_id in sequence_by_id:
                raise Phase8CInputError("GDPa3 sequence identifiers are duplicated")
            sequence_by_id[antibody_id] = (vh, vl, sequence_hash(vh, vl))

        average_id_strings: list[str | None] = []
        for value in average_ids:
            if value is None or str(value) == "":
                average_id_strings.append(None)
            else:
                antibody_id = str(value)
                if antibody_id != antibody_id.strip():
                    raise Phase8CInputError("GDPa3 HIC-sheet identifiers contain surrounding whitespace")
                average_id_strings.append(antibody_id)
        complete_ids = [value for value, hic in zip(average_id_strings, hic_values) if value is not None]
        if len(complete_ids) != expected_source_n or len(set(complete_ids)) != expected_source_n:
            raise Phase8CInputError("GDPa3 HIC sheet must contain 80 unique source antibody identifiers")
        if len(sequence_by_id) != expected_source_n or set(complete_ids) != set(sequence_by_id):
            raise Phase8CInputError("GDPa3 sequence and HIC source identifiers do not match one-to-one")

        label_rows: list[dict[str, Any]] = []
        for antibody_id, hic_value in zip(average_id_strings, hic_values):
            if antibody_id is None:
                if hic_value is not None and str(hic_value) != "":
                    raise Phase8CInputError("A GDPa3 HIC value has no antibody identifier")
                continue
            if hic_value is None or str(hic_value) == "":
                continue
            try:
                hic_rt_avg = float(hic_value)
            except (TypeError, ValueError) as error:
                raise Phase8CInputError("A preregistered hic_rt_avg value is not numeric") from error
            if not math.isfinite(hic_rt_avg):
                raise Phase8CInputError("A preregistered hic_rt_avg value is not finite")
            label_rows.append(
                {
                    "antibody_id": antibody_id,
                    "paired_hash": sequence_by_id[antibody_id][2],
                    "hic_rt_avg": hic_rt_avg,
                }
            )

        labels = pd.DataFrame(label_rows, columns=LABEL_COLUMNS)
        if len(labels) != expected_n or labels["antibody_id"].duplicated().any() or labels["paired_hash"].duplicated().any():
            raise Phase8CInputError(f"Expected {expected_n} unique nonmissing HIC labels")
        return labels
    finally:
        workbook.close()


def validate_prediction_and_snapshot(predictions: pd.DataFrame, snapshot: pd.DataFrame, *, expected_n: int = EXPECTED_EVALUATION_N) -> None:
    if tuple(predictions.columns) != PREDICTION_COLUMNS:
        raise Phase8CInputError("Prediction artifact schema differs from the sealed schema")
    if tuple(snapshot.columns) != SNAPSHOT_COLUMNS:
        raise Phase8CInputError("Sequence snapshot schema differs from Phase 8A")
    if len(predictions) != expected_n or len(snapshot) != expected_n:
        raise Phase8CInputError(f"Expected exactly {expected_n} predictions and frozen sequences")
    if not predictions["model_version"].astype(str).eq("phase5-frozen-v1").all():
        raise Phase8CInputError("Prediction artifact contains an unexpected model version")
    for frame, key in ((predictions, "antibody_id"), (predictions, "paired_hash"), (snapshot, "antibody_id"), (snapshot, "paired_hash")):
        if frame[key].duplicated().any():
            raise Phase8CInputError(f"Duplicate frozen prediction/snapshot key: {key}")
    values = pd.to_numeric(predictions["hic_prediction"], errors="coerce").to_numpy(dtype=np.float64)
    if not np.isfinite(values).all():
        raise Phase8CInputError("Sealed HIC predictions must be finite numeric values")
    if predictions["antibody_id"].astype(str).tolist() != snapshot["antibody_id"].astype(str).tolist():
        raise Phase8CInputError("Prediction antibody ID order differs from the frozen snapshot")
    if predictions["paired_hash"].astype(str).tolist() != snapshot["paired_hash"].astype(str).tolist():
        raise Phase8CInputError("Prediction paired-hash order differs from the frozen snapshot")


def join_hic_labels(
    predictions: pd.DataFrame,
    snapshot: pd.DataFrame,
    labels: pd.DataFrame,
    *,
    expected_n: int = EXPECTED_EVALUATION_N,
) -> tuple[pd.DataFrame, dict[str, int]]:
    validate_prediction_and_snapshot(predictions, snapshot, expected_n=expected_n)
    if tuple(labels.columns) != LABEL_COLUMNS:
        raise Phase8CInputError("Temporary HIC label table has fields outside the authorized scope")
    if len(labels) != expected_n:
        raise Phase8CInputError(f"Expected {expected_n} nonmissing HIC label rows")
    if labels[["antibody_id", "paired_hash"]].isna().any().any():
        raise Phase8CInputError("HIC label identity fields must be complete")
    if labels["antibody_id"].duplicated().any() or labels["paired_hash"].duplicated().any():
        raise Phase8CInputError("HIC label identifiers and paired hashes must be unique")
    target = pd.to_numeric(labels["hic_rt_avg"], errors="coerce").to_numpy(dtype=np.float64)
    if not np.isfinite(target).all():
        raise Phase8CInputError("HIC label values must be finite numeric values")

    prediction_by_id = dict(zip(predictions["antibody_id"].astype(str), predictions["paired_hash"].astype(str)))
    label_by_id = dict(zip(labels["antibody_id"].astype(str), labels["paired_hash"].astype(str)))
    shared_ids = set(prediction_by_id).intersection(label_by_id)
    hash_mismatches = sum(prediction_by_id[record_id] != label_by_id[record_id] for record_id in shared_ids)
    prediction_keys = set(zip(predictions["antibody_id"].astype(str), predictions["paired_hash"].astype(str)))
    label_keys = set(zip(labels["antibody_id"].astype(str), labels["paired_hash"].astype(str)))
    prediction_only = len(prediction_keys - label_keys)
    label_only = len(label_keys - prediction_keys)
    integrity = {
        "matched_rows": len(prediction_keys.intersection(label_keys)),
        "prediction_only_rows": prediction_only,
        "label_only_rows": label_only,
        "hash_mismatches": int(hash_mismatches),
    }
    if integrity != {"matched_rows": expected_n, "prediction_only_rows": 0, "label_only_rows": 0, "hash_mismatches": 0}:
        raise Phase8CInputError(f"Prediction/HIC join integrity failed: {integrity}")

    label_map = {
        (str(row.antibody_id), str(row.paired_hash)): float(row.hic_rt_avg)
        for row in labels.itertuples(index=False)
    }
    joined = predictions.loc[:, PREDICTION_COLUMNS].copy()
    joined["hic_prediction"] = pd.to_numeric(joined["hic_prediction"], errors="raise").astype(float)
    joined["hic_rt_avg"] = [label_map[(str(row.antibody_id), str(row.paired_hash))] for row in joined.itertuples(index=False)]
    if len(joined) != expected_n or joined["hic_rt_avg"].isna().any():
        raise Phase8CInputError("Joined HIC evaluation population is incomplete")
    return joined, integrity


def _finite_or_none(value: Any) -> float | None:
    number = float(value)
    return number if math.isfinite(number) else None


def compute_preregistered_statistics(joined: pd.DataFrame) -> dict[str, Any]:
    """Compute only the preregistered correlations and Spearman percentile CI."""

    prediction = joined["hic_prediction"].to_numpy(dtype=np.float64)
    target = joined["hic_rt_avg"].to_numpy(dtype=np.float64)
    if len(prediction) != len(target) or len(prediction) == 0:
        raise Phase8CInputError("Cannot evaluate mismatched or empty HIC vectors")

    if np.unique(prediction).size < 2 or np.unique(target).size < 2:
        spearman_value = pearson_value = kendall_value = None
    else:
        spearman_value = _finite_or_none(stats.spearmanr(prediction, target).statistic)
        pearson_value = _finite_or_none(stats.pearsonr(prediction, target).statistic)
        kendall_value = _finite_or_none(stats.kendalltau(prediction, target, variant="b").statistic)

    rng = np.random.default_rng(BOOTSTRAP_SEED)
    if not isinstance(rng.bit_generator, np.random.PCG64):
        raise RuntimeError("NumPy default_rng did not resolve to the preregistered PCG64 generator")
    boot_rhos: list[float] = []
    degenerate = 0
    n = len(prediction)
    for _ in range(BOOTSTRAP_RESAMPLES):
        indices = rng.integers(0, n, size=n)
        pred_sample = prediction[indices]
        target_sample = target[indices]
        if np.unique(pred_sample).size < 2 or np.unique(target_sample).size < 2:
            degenerate += 1
            continue
        rho = float(stats.spearmanr(pred_sample, target_sample).statistic)
        if not math.isfinite(rho):
            degenerate += 1
        else:
            boot_rhos.append(rho)

    if boot_rhos:
        lower, upper = np.quantile(np.asarray(boot_rhos, dtype=np.float64), [0.025, 0.975], method="linear")
        confidence_interval: list[float] | None = [float(lower), float(upper)]
    else:
        confidence_interval = None

    return {
        "primary": {"metric": "Spearman rho", "estimate": spearman_value, "n": n},
        "bootstrap": {
            "resamples": BOOTSTRAP_RESAMPLES,
            "seed": BOOTSTRAP_SEED,
            "bit_generator": "PCG64",
            "valid_n": len(boot_rhos),
            "degenerate_n": degenerate,
            "confidence_level": 0.95,
            "method": "percentile",
            "ci": confidence_interval,
        },
        "secondary": {
            "pearson_r": {"estimate": pearson_value, "n": n},
            "kendall_tau_b": {"estimate": kendall_value, "n": n},
        },
        "similarity_bins": {"counts": NOVELTY_BINS.copy(), "n": sum(NOVELTY_BINS.values())},
    }


def build_result(
    statistics: dict[str, Any],
    join_integrity: dict[str, int],
    *,
    raw_sha256: str,
    prediction_sha256: str,
    snapshot_sha256: str,
    model_sha256: str,
    phase8c_code_commit: str,
    timestamp_utc: str,
) -> dict[str, Any]:
    return {
        "status": "OBSERVED_ONE_TIME_EXTERNAL_EVALUATION",
        "dataset": "GDPa3",
        "endpoint": "hic_rt_avg",
        "unit": "minutes",
        "n": EXPECTED_EVALUATION_N,
        "prediction_artifact_sha256": prediction_sha256,
        "raw_workbook_sha256": raw_sha256,
        "sequence_snapshot_sha256": snapshot_sha256,
        "model_id": "hic_esm2_v1",
        "model_version": "phase5-frozen-v1",
        "model_artifact_sha256": model_sha256,
        "phase8b_seal_commit": EXPECTED_PHASE8B_SEAL_COMMIT,
        "phase8c_evaluator_code_commit": phase8c_code_commit,
        "join_integrity": join_integrity,
        **statistics,
        "cross_source_cross_protocol": True,
        "model_trained": False,
        "model_tuned": False,
        "post_hoc_filtering": False,
        "absolute_error_metrics": "NOT_CALCULATED",
        "other_gdpa3_endpoints_analyzed": False,
        "composite_classifier_evaluated": False,
        "aintibody_test_labels_accessed": False,
        "timestamp_utc": timestamp_utc,
    }


def _git_output(*args: str) -> str:
    return subprocess.check_output(["git", "-C", str(ROOT), *args], text=True).strip()


def _verify_committed_evaluator() -> str:
    branch = _git_output("branch", "--show-current")
    head = _git_output("rev-parse", "HEAD")
    remote = _git_output("rev-parse", "origin/main")
    if branch != "main" or head != remote:
        raise Phase8CInputError("Phase 8C evaluator must run from synchronized main")
    for relative_path in (
        "validation/external_developability/run_phase8c_hic_external_evaluation.py",
        "validation/external_developability/tests/test_phase8c_hic_external_evaluation.py",
    ):
        subprocess.run(["git", "-C", str(ROOT), "diff", "--quiet", "HEAD", "--", relative_path], check=True)
        subprocess.run(["git", "-C", str(ROOT), "diff", "--cached", "--quiet", "--", relative_path], check=True)
    return head


def _verify_prediction_seal(predictions: pd.DataFrame, snapshot: pd.DataFrame, seal: dict[str, Any]) -> None:
    if seal.get("status") != "SEALED_BEFORE_LABEL_REVEAL":
        raise Phase8CInputError("Phase 8B seal is not in the required frozen state")
    if seal.get("phase8b_code_commit") != "73b278014a059b68c830c39cffc37d29ff1e705f":
        raise Phase8CInputError("Phase 8B code commit in the seal is unexpected")
    if seal.get("prediction_sha256") != EXPECTED_PREDICTION_SHA256:
        raise Phase8CInputError("Prediction SHA in Phase 8B seal differs from the frozen value")
    if seal.get("sequence_snapshot_sha256") != EXPECTED_SNAPSHOT_SHA256:
        raise Phase8CInputError("Snapshot SHA in Phase 8B seal differs from the frozen value")
    if seal.get("model_artifact_sha256") != EXPECTED_MODEL_SHA256:
        raise Phase8CInputError("Model SHA in Phase 8B seal differs from the frozen value")
    validate_prediction_and_snapshot(predictions, snapshot)


def _format_number(value: float | None) -> str:
    return "not estimable" if value is None else f"{value:.6g}"


def build_human_report(result: dict[str, Any], result_sha256: str) -> str:
    rho = result["primary"]["estimate"]
    ci = result["bootstrap"]["ci"]
    if rho is None:
        association_text = "The primary rank association was not estimable."
    elif rho > 0:
        association_text = "A positive external HIC rank association was observed."
    elif rho < 0:
        association_text = "A negative external HIC rank association was observed."
    else:
        association_text = "The observed external HIC rank association was zero."
    if ci is None:
        uncertainty_text = "The bootstrap interval was not estimable."
    elif ci[0] <= 0 <= ci[1]:
        uncertainty_text = "The 95% percentile interval spans zero; uncertainty remains substantial."
    else:
        uncertainty_text = "The 95% percentile interval does not span zero; no success threshold was preregistered."
    internal_note = (
        "The point estimate is numerically lower than the frozen internal AIntibody estimate (rho=0.834662, N=72); "
        "this is descriptive only, and the datasets/protocols differ. No statistical test comparing the correlations was run."
        if rho is not None and rho < 0.834662
        else "The frozen internal AIntibody estimate (rho=0.834662, N=72) is provided only as descriptive context; "
        "no statistical test comparing the correlations was run."
    )
    return f"""# Phase 8C — GDPa3 External HIC Evaluation

**Status:** `OBSERVED_ONE_TIME_EXTERNAL_EVALUATION`

**Result JSON SHA256:** `{result_sha256}`

## 1. Objective

Evaluate once the sealed `hic_esm2_v1` predictions against the preregistered GDPa3 `hic_rt_avg` endpoint. GDPa3 HIC is now observed and is not an untouched dataset for future model development.

## 2. Frozen protocol

The Phase 8A protocol and Phase 8B prediction seal were frozen before label reveal. Phase 8C evaluator code commit: `{result['phase8c_evaluator_code_commit']}`. Primary statistic: Spearman rho; bootstrap: 2,000 resamples, NumPy `default_rng`/PCG64, seed 20260926, percentile 95% interval. Secondary statistics: Pearson r and Kendall tau-b. Absolute-error metrics were omitted as preregistered.

## 3. Dataset independence

The frozen Phase 7C.1 sequence audit reported no exact paired-sequence overlap with Jain, AIntibody TRAIN/VALIDATION/TEST/ALL, or SAbDab2. Similarity figures are sequence-identity proxies, not germline-family annotations. This does not establish family-independent generalization.

## 4. Prediction seal verification

Prediction SHA256 `{result['prediction_artifact_sha256']}`; sequence snapshot SHA256 `{result['sequence_snapshot_sha256']}`; model artifact SHA256 `{result['model_artifact_sha256']}`. The sealed artifact contained N=79 rows. Phase 8B code commit: `{result['phase8b_seal_commit']}`.

## 5. Label reveal / join integrity

The only experimental endpoint read was `hic_rt_avg`. Raw workbook SHA256: `{result['raw_workbook_sha256']}`. Predictions and labels were joined on both antibody ID and paired sequence hash: {result['join_integrity']['matched_rows']}/{result['n']} matched, prediction-only={result['join_integrity']['prediction_only_rows']}, label-only={result['join_integrity']['label_only_rows']}, hash mismatches={result['join_integrity']['hash_mismatches']}.

## 6. Primary external result

Spearman rho = {_format_number(rho)}, N={result['primary']['n']}. No success threshold was applied.

## 7. Bootstrap uncertainty

95% percentile CI = `{ci if ci is not None else 'not estimable'}`; valid replicates={result['bootstrap']['valid_n']}, degenerate replicates={result['bootstrap']['degenerate_n']}, total=2,000.

## 8. Secondary metrics

Pearson r = {_format_number(result['secondary']['pearson_r']['estimate'])}, N={result['secondary']['pearson_r']['n']}. Kendall tau-b = {_format_number(result['secondary']['kendall_tau_b']['estimate'])}, N={result['secondary']['kendall_tau_b']['n']}. Neither replaces the primary endpoint.

## 9. Sequence novelty context

Frozen paired-min identity bins versus AIntibody TRAIN+VALIDATION, descriptive only (N=79): `<0.70` = 71; `0.70–<0.80` = 7; `0.80–<0.90` = 1; `>=0.90` = 0. No subgroup correlations were calculated.

## 10. Cross-source / cross-protocol limitation

This is cross-source, cross-protocol HIC evaluation. GDPa3 assay conditions are not sufficiently specified to establish same-protocol or assay-equivalent replication.

## 11. Interpretation

{association_text} {uncertainty_text} {internal_note}

## 12. Scientific limitations

The sample is N=79 from one external source and one endpoint. Similarity bins are not immunoglobulin family labels. Assay protocol shift and measurement-scale differences remain unresolved.

## 13. What this result does NOT establish

It does not establish family-independent or universal antibody generalization, clinical utility, causality, mutation-effect prediction, global developability prediction, or same-protocol replication. It is not a product claim or a wet-lab replacement.

## 14. Future work

GDPa3 HIC is permanently marked OBSERVED for future development. Any further analysis requires a separately authorized, explicitly post-hoc protocol. No model or product claims were changed here.
"""


def run_one_time_evaluation() -> dict[str, Any]:
    code_commit = _verify_committed_evaluator()
    paths = (RESULT_JSON_PATH, RESULT_REPORT_PATH, OBSERVED_MARKER_PATH)
    if any(path.exists() for path in paths):
        raise Phase8CInputError("Phase 8C result/marker already exists; refusing a second evaluation")

    seal = json.loads(SEAL_PATH.read_text(encoding="utf-8"))
    prediction_sha = sha256_file(PREDICTION_PATH)
    snapshot_sha = sha256_file(SNAPSHOT_PATH)
    model_sha = sha256_file(MODEL_PATH)
    if prediction_sha != EXPECTED_PREDICTION_SHA256:
        raise Phase8CInputError("Sealed prediction artifact SHA256 mismatch")
    if snapshot_sha != EXPECTED_SNAPSHOT_SHA256:
        raise Phase8CInputError("Frozen sequence snapshot SHA256 mismatch")
    if model_sha != EXPECTED_MODEL_SHA256:
        raise Phase8CInputError("Frozen model artifact SHA256 mismatch")

    predictions = pd.read_csv(PREDICTION_PATH, dtype={"antibody_id": str, "paired_hash": str, "model_version": str}, keep_default_na=False)
    snapshot = pd.read_csv(SNAPSHOT_PATH, dtype=str, keep_default_na=False)
    _verify_prediction_seal(predictions, snapshot, seal)

    # This is the first operation in Phase 8C that parses the raw workbook.
    # The reader first re-hashes it, then accesses only sequence identity and hic_rt_avg.
    labels = read_gdpa3_hic_label_table(RAW_WORKBOOK)
    joined, join_integrity = join_hic_labels(predictions, snapshot, labels)
    statistics = compute_preregistered_statistics(joined)
    timestamp = datetime.now(timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z")
    result = build_result(
        statistics,
        join_integrity,
        raw_sha256=EXPECTED_RAW_SHA256,
        prediction_sha256=prediction_sha,
        snapshot_sha256=snapshot_sha,
        model_sha256=model_sha,
        phase8c_code_commit=code_commit,
        timestamp_utc=timestamp,
    )

    json_text = json.dumps(result, indent=2, ensure_ascii=False, allow_nan=False) + "\n"
    RESULT_JSON_PATH.write_text(json_text, encoding="utf-8", newline="\n")
    result_sha = sha256_file(RESULT_JSON_PATH)
    report_text = build_human_report(result, result_sha)
    RESULT_REPORT_PATH.write_text(report_text, encoding="utf-8", newline="\n")
    marker = (
        "# GDPa3 HIC Observed Status\n\n"
        "GDPa3 HIC labels were first revealed for model-performance evaluation during Phase 8C.\n\n"
        "From this point forward, GDPa3 HIC is **OBSERVED**. It must not be described as untouched, unseen, or a prospective external holdout for future revised models.\n"
    )
    OBSERVED_MARKER_PATH.write_text(marker, encoding="utf-8", newline="\n")
    return result


def main() -> None:
    result = run_one_time_evaluation()
    print("Phase 8C one-time evaluation complete.")
    print(f"Result JSON: {RESULT_JSON_PATH}")
    print(f"Result JSON SHA256: {sha256_file(RESULT_JSON_PATH)}")
    print(f"Evaluation N: {result['n']}")


if __name__ == "__main__":
    main()
