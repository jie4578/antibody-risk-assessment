"""Conditional single-substrate kinetics; no persistence, AI, or data selection.

See PHASE_C2A_MM_PROTOCOL.md. Review acknowledges limitations, not validity.
SciPy/NumPy are imported only when an eligible numerical fit is requested.
"""
from copy import deepcopy
from dataclasses import asdict, dataclass
from datetime import datetime, timedelta
import math
from statistics import median

from .initial_rate import (ANALYSIS_VERSION as C1_VERSION, PRODUCT_UNITS, TIME_UNITS,
    Calibration, Observation, RateConfig, analyze_initial_rate, canonical, digest)

ALGORITHM_VERSION = "mm-unweighted-1.0.0"
CONDITION_FIELDS = (
    "protocol_id", "protocol_version", "temperature_c", "pH", "buffer_composition",
    "substrate_name", "substrate_lot", "cofactor_name", "cofactor_concentration",
    "cofactor_concentration_unit", "enzyme_concentration", "enzyme_concentration_unit",
    "reaction_volume", "reaction_volume_unit", "readout_method",
)
NUMERICAL_CONFIG = {
    "method": "trf", "loss": "linear", "ftol": 1e-12, "xtol": 1e-12,
    "gtol": 1e-12, "max_nfev": 5000, "x_scale": 1.0,
}
DIAGNOSTIC_POLICY = {
    "minimum_rates": 4, "minimum_positive_concentrations": 4,
    "log_jacobian_condition_failure": 1e6, "log_jacobian_condition_warning": 1e3,
    "low_only_failure_ratio": 0.1, "high_only_failure_ratio": 10.0,
    "saturation_warning_ratio": 3.0, "low_coverage_warning_ratio": 0.5,
    "narrow_span_ratio": 10.0, "boundary_margin_log": math.log(10),
}


@dataclass(frozen=True)
class RateRecord:
    analysis_id: str
    variant_id: str
    conditions: dict
    c1_result: dict
    provenance: dict


@dataclass(frozen=True)
class FitReview:
    reviewer: str
    reviewed_at_utc: str
    rationale: str
    input_sha256: str
    direction: str = "PRODUCT_FORMATION"
    acknowledge_not_established: bool = False


def input_digest(records):
    """Bind review to complete snapshots, including C.1 configuration and lineage."""
    return digest(sorted((asdict(r) for r in records), key=lambda r: r["analysis_id"]))


def _number(value):
    if isinstance(value, bool):
        raise ValueError("Boolean is not a measurement")
    result = float(value)
    if not math.isfinite(result):
        raise ValueError("A finite measurement is required")
    return result


def _finite_output(value):
    if isinstance(value, float):
        return math.isfinite(value)
    if isinstance(value, dict):
        return all(_finite_output(v) for v in value.values())
    if isinstance(value, (list, tuple)):
        return all(_finite_output(v) for v in value)
    return True


def verify_c1_result(result):
    """Replay in memory, without saving or modifying C.1 observations/results."""
    meta = result["analysis_metadata"]
    if result["status"] != "ESTIMATED" or meta["analysis_version"] != C1_VERSION:
        raise ValueError("An ESTIMATED result from the supported C.1 version is required")
    if meta["initial_rate_validity"] != "NOT_ESTABLISHED":
        raise ValueError("C.1 validity must not be promoted")
    calibration = Calibration(**meta["calibration"]) if meta["calibration"] else None
    expected = analyze_initial_rate(
        [Observation(**r) for r in result["raw_observations"]],
        RateConfig(**meta["configuration"]),
        blanks=[Observation(**r) for r in result["blank_observations"]],
        calibration=calibration, calculated_at=meta["calculated_at_utc"],
    )
    if canonical(expected) != canonical(result):
        raise ValueError("C.1 inputs, configuration, hashes or derived values do not replay")
    if calibration is None or result["derived_initial_rate"]["product_rate"] is None:
        raise ValueError("A traceable, in-range product calibration is required; signal slope alone is insufficient")


def _conditions_valid(c):
    if any(c.get(k) is None or isinstance(c.get(k), bool) or not str(c[k]).strip()
           for k in CONDITION_FIELDS):
        raise ValueError("All assay conditions must be explicitly documented")
    for k in set(CONDITION_FIELDS) - {"temperature_c", "pH", "cofactor_concentration", "enzyme_concentration", "reaction_volume"}:
        if not isinstance(c[k], str):
            raise ValueError("Condition identifiers and units must be text")
    _number(c["pH"])
    if _number(c["temperature_c"]) <= -273.15:
        raise ValueError("Invalid absolute temperature")
    if _number(c["cofactor_concentration"]) < 0 or _number(c["enzyme_concentration"]) <= 0 or _number(c["reaction_volume"]) <= 0:
        raise ValueError("Invalid cofactor/enzyme concentration or volume")
    if c["enzyme_concentration_unit"] not in PRODUCT_UNITS or c["reaction_volume_unit"] not in {"L", "mL", "uL", "µL", "μL"}:
        raise ValueError("Explicit physical enzyme concentration and reaction-volume units are required")
    if c["cofactor_name"] == "NONE":
        if _number(c["cofactor_concentration"]) != 0 or c["cofactor_concentration_unit"] != "dimensionless":
            raise ValueError("No cofactor must be explicitly NONE/0/dimensionless")
    elif c["cofactor_concentration_unit"] not in PRODUCT_UNITS:
        raise ValueError("A cofactor concentration unit is required")


def fit_michaelis_menten(records, review):
    """Fit every supplied record; eligibility failures retain inputs, not estimates.

    Snapshot callers supply provenance; use mm_rate_adapter for byte-verified SQLite
    sources. C.1 replay verifies arithmetic, not instrument calibration authenticity.
    """
    records = deepcopy(tuple(records))
    result = {
        "status": "NOT_ESTIMABLE", "parameters": None, "predictions": [], "statistics": None,
        "reasons": [], "quality_control": [], "diagnostics": {}, "optimizer": None,
        "input_records": [asdict(r) for r in records], "review": asdict(review),
        "metadata": {"algorithm_version": ALGORITHM_VERSION, "input_sha256": input_digest(records),
            "initial_rate_validity": "NOT_ESTABLISHED", "weighting": "UNWEIGHTED_EACH_RECORD",
            "configuration": dict(NUMERICAL_CONFIG), "diagnostic_policy": dict(DIAGNOSTIC_POLICY),
            "parameter_intervals": "NOT_CALCULATED", "experimental_validation": "NOT_ESTABLISHED"},
    }

    def issue(code, message, *, failure=False):
        result["reasons" if failure else "quality_control"].append({"code": code, "message": message})

    def finish():
        # A failed candidate is never exposed as a parameter estimate.
        if result["reasons"]:
            result["status"], result["parameters"] = "NOT_ESTIMABLE", None
        result["metadata"]["result_sha256"] = digest(result)
        return result

    issue("CONDITIONAL_INITIAL_RATES", "C.1 initial-rate validity remains NOT_ESTABLISHED after review.")
    issue("UNCERTAINTY_NOT_PROPAGATED", "No parameter intervals or propagation of calibration/blank/concentration/C.1 uncertainty.")
    try:
        stamp = datetime.fromisoformat(review.reviewed_at_utc.replace("Z", "+00:00"))
        if (not review.reviewer.strip() or not review.rationale.strip()
            or stamp.utcoffset() != timedelta(0) or review.acknowledge_not_established is not True
            or review.direction != "PRODUCT_FORMATION" or review.input_sha256 != input_digest(records)):
            raise ValueError("Explicit input-bound conditional review and product-formation direction required")
    except (AttributeError, TypeError, ValueError) as exc:
        issue("REVIEW_REQUIRED", str(exc), failure=True)
        return finish()
    if len(records) < 4:
        issue("INSUFFICIENT_RATES", "At least four rates are required.", failure=True)
        return finish()
    ordered = sorted(records, key=lambda r: r.analysis_id)
    points, contexts, condition_keys, units, seen_ids, seen_observations = [], set(), set(), set(), set(), set()
    for r in ordered:
        try:
            if not isinstance(r.analysis_id, str) or not r.analysis_id.strip() or r.analysis_id in seen_ids:
                raise ValueError("Duplicate or missing analysis_id; no deduplication")
            seen_ids.add(r.analysis_id)
            verify_c1_result(r.c1_result)
            _conditions_valid(r.conditions)
            d = r.c1_result["derived_initial_rate"]
            if any(not isinstance(v, str) or not v.strip() for v in
                   (r.variant_id, d["sample_id"], d["batch_id"], d["biological_replicate"], d["technical_replicate"])):
                raise ValueError("Variant, sample, batch and biological/technical repeat identities are required")
            raw = r.c1_result["raw_observations"]
            if any(not o["well_id"] for o in raw):
                raise ValueError("Well identity is required")
            obs_ids = {o["observation_id"] for o in raw}
            if seen_observations.intersection(obs_ids):
                raise ValueError("An original observation is reused in multiple rate analyses")
            seen_observations.update(obs_ids)
            s, v = _number(d["substrate_concentration"]), _number(d["product_rate"]["slope"])
            if s < 0 or v < 0:
                raise ValueError("Negative substrate or product rate; no absolute-value conversion")
            su, ru = d["substrate_concentration_unit"], d["product_rate"]["rate_unit"]
            cal = r.c1_result["analysis_metadata"]["calibration"]
            time_unit = r.c1_result["analysis_metadata"]["configuration"]["time_unit"]
            if su not in PRODUCT_UNITS or time_unit not in TIME_UNITS or ru != cal["product_unit"] + "/" + time_unit:
                raise ValueError("Unsupported or missing physical units")
            units.add((su, ru))
            contexts.add((r.variant_id, d["sample_id"], d["batch_id"], d["biological_replicate"]))
            condition_keys.add(canonical({k: r.conditions[k] for k in CONDITION_FIELDS}))
            points.append((r.analysis_id, s, v))
        except (KeyError, TypeError, ValueError, AttributeError, OverflowError) as exc:
            issue("INELIGIBLE_INPUT", str(r.analysis_id) + ": " + str(exc), failure=True)
    if len(contexts) > 1 or len(condition_keys) > 1:
        issue("MIXED_CONTEXT", "Do not pool variants, samples, batches, biological repeats or assay conditions.", failure=True)
    if len(units) > 1:
        issue("MIXED_UNITS", "Units must match literally; no implicit conversion.", failure=True)
    if result["reasons"]:
        return finish()
    positive_s = [s for _, s, _ in points if s > 0]
    if len(set(positive_s)) < 4:
        issue("INSUFFICIENT_CONCENTRATIONS", "At least four different positive concentrations required.", failure=True)
        return finish()
    if not any(v > 0 for _, _, v in points):
        issue("NO_POSITIVE_RATE", "All observed rates are zero; positive parameters are not estimable.", failure=True)
        return finish()
    try:
        import numpy as np
        import scipy
        from scipy.optimize import least_squares
    except ImportError:
        issue("DEPENDENCY_UNAVAILABLE", "SciPy and NumPy are required for this independent kernel.", failure=True)
        return finish()
    result["metadata"]["dependencies"] = {"scipy": scipy.__version__, "numpy": np.__version__}
    try:
        with np.errstate(over="raise", invalid="raise", divide="raise"):
            s_scale, v_scale = median(positive_s), max(v for _, _, v in points)
            x, y = np.asarray([s / s_scale for _, s, _ in points]), np.asarray([v / v_scale for _, _, v in points])
            lower, upper = -math.log(1e8), math.log(1e8)

            def evaluate(p):
                vmax, km = np.exp(p)
                pred = vmax * x / (km + x)
                jac = np.column_stack((pred, -pred * km / (km + x)))
                return pred, jac

            fit = least_squares(lambda p: evaluate(p)[0] - y, [math.log(1.1), 0.0],
                jac=lambda p: evaluate(p)[1], bounds=([lower, lower], [upper, upper]), **NUMERICAL_CONFIG)
            result["optimizer"] = {"success": bool(fit.success), "status": int(fit.status), "message": str(fit.message),
                "nfev": int(fit.nfev), "optimality": float(fit.optimality), "log_parameters": fit.x.tolist(),
                "initial_parameters": {"Vmax": 1.1 * v_scale, "Km": s_scale},
                "bounds": {"Vmax": [v_scale * 1e-8, v_scale * 1e8], "Km": [s_scale * 1e-8, s_scale * 1e8]},
                "scales": {"substrate": s_scale, "rate": v_scale}}
            if not _finite_output(result["optimizer"]):
                raise ValueError("Non-finite optimizer output or numerical bounds")
            if not fit.success:
                issue("OPTIMIZER_NOT_CONVERGED", str(fit.message), failure=True)
                return finish()
            pred, jac = evaluate(fit.x)
            vmax, km = np.exp(fit.x) * [v_scale, s_scale]
            prediction = pred * v_scale
            residuals = np.asarray([v for _, _, v in points]) - prediction
            sse, sst = float(residuals @ residuals), float(((y - y.mean()) * v_scale) @ ((y - y.mean()) * v_scale))
            stats = {"n": len(points), "unique_positive_concentrations": len(set(positive_s)),
                "biological_replicates": 1, "sse": sse, "rmse": math.sqrt(sse / len(points)),
                "r_squared": 1 - sse / sst if sst > 0 else None, "residual_definition": "observed_minus_fitted"}
            singular = np.linalg.svd(jac, compute_uv=False)
            condition = float(singular[0] / singular[-1]) if singular[-1] > 0 else None
            numeric = [vmax, km, *prediction, *residuals, sse, stats["rmse"], fit.optimality, *fit.x, *jac.ravel(), *singular]
            numeric.extend(v for v in (condition, stats["r_squared"]) if v is not None)
            if not all(math.isfinite(float(v)) for v in numeric):
                raise ValueError("Non-finite calculation output")
            result["statistics"] = stats
            result["predictions"] = [{"analysis_id": ident, "substrate_concentration": s, "observed_rate": v,
                "fitted_rate": float(p), "residual": float(e)} for (ident, s, v), p, e in zip(points, prediction, residuals)]
            low_ratio, high_ratio = min(positive_s) / km, max(positive_s) / km
            result["diagnostics"] = {"log_jacobian_condition": condition, "singular_values": singular.tolist(),
                "min_positive_substrate_over_Km": float(low_ratio), "max_substrate_over_Km": float(high_ratio),
                "concentration_span": max(positive_s) / min(positive_s)}
            if condition is None or condition >= 1e6:
                issue("UNIDENTIFIABLE_PARAMETERS", "Log-parameter Jacobian is singular or ill-conditioned.", failure=True)
            elif condition >= 1e3:
                issue("ILL_CONDITIONED_PARAMETERS", "Local log-parameter sensitivity is poorly conditioned.")
            if min(float(min(fit.x - lower)), float(min(upper - fit.x))) <= math.log(10):
                issue("PARAMETER_BOUNDARY", "Candidate is within a factor of ten of a numerical boundary.", failure=True)
            if high_ratio < 0.1 or low_ratio > 10:
                issue("EXTREME_COVERAGE", "Only very low or very high concentrations; separate parameters unsupported.", failure=True)
            if high_ratio < 3:
                issue("SATURATION_NOT_COVERED", "Substrate range insufficient to support saturation estimation.")
            if low_ratio > 0.5:
                issue("LOW_CONCENTRATIONS_NOT_COVERED", "Low-concentration coverage is insufficient.")
            if max(positive_s) / min(positive_s) < 10:
                issue("NARROW_CONCENTRATION_RANGE", "Concentration span is less than tenfold.")
            if len(points) < 6:
                issue("FEW_RATES", "Few residual observations; repeats do not replace concentration coverage.")
            if len(set(s for _, s, _ in points)) < len(points):
                issue("TECHNICAL_REPEATS_RETAINED", "Equal concentrations retained individually; no biological inference.")
            if sst == 0:
                issue("CONSTANT_RATE", "R squared is undefined for constant observed rates.")
            if any(s == 0 and v > 0 for _, s, v in points):
                issue("ZERO_SUBSTRATE_POSITIVE_RATE", "Nonzero rate at zero substrate is inconsistent with this model.")
            means = [sum(v for _, s, v in points if s == level) / sum(s == level for _, s, _ in points)
                     for level in sorted({s for _, s, _ in points})]
            if any(b < a for a, b in zip(means, means[1:])):
                issue("NONMONOTONIC_RATES", "Decreasing concentration-level mean; no points removed or mechanism inferred.")
            if any(abs(float(e)) > 3 * stats["rmse"] for e in residuals):
                issue("LARGE_RESIDUAL", "Residual exceeds 3*RMSE; record retained.")
            result["status"] = "FIT_WITH_LIMITATIONS"
            result["parameters"] = {"Km": float(km), "Km_unit": next(iter(units))[0],
                "Vmax": float(vmax), "Vmax_unit": next(iter(units))[1]}
            if not _finite_output([result[k] for k in ("parameters", "predictions", "statistics", "diagnostics")]):
                raise ValueError("Non-finite derived output")
    except (ValueError, RuntimeError, FloatingPointError, OverflowError, ZeroDivisionError, np.linalg.LinAlgError) as exc:
        issue("NUMERICAL_FAILURE", str(exc), failure=True)
        result["parameters"], result["predictions"], result["statistics"], result["optimizer"], result["diagnostics"] = None, [], None, None, {}
    return finish()
