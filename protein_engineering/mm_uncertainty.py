"""Conditional unknown-variance normal profile likelihood; no storage or AI.

See PHASE_C2B1_UNCERTAINTY_PROTOCOL.md. Independence is a reviewed assumption,
not a consequence of technical-repeat counts or optimizer convergence.
"""
from copy import deepcopy
from dataclasses import asdict, dataclass, fields, is_dataclass
from datetime import datetime, timedelta
import json
import math
from numbers import Integral, Real

from .initial_rate import canonical, digest
from .mm_kinetics import FitReview, fit_michaelis_menten, input_digest

ANALYSIS_VERSION = "mm-profile-normal-1.0.1"
ERROR_MODEL = "CONDITIONAL_IID_ADDITIVE_NORMAL_UNKNOWN_VARIANCE"
METHOD = "PROFILE_LIKELIHOOD_UNKNOWN_VARIANCE_WILKS_CHI2_1_APPROXIMATE"
POLICY = {
    "minimum_n": 6, "small_sample_n": 20, "normalized_variance_floor": 1e-24,
    "log_scan_step": math.log(2) / 2, "default_scan_steps": 80,
    "nuisance_grid_points": 129, "nuisance_xatol": 1e-13, "nuisance_maxiter": 500,
    "root_xtol": 1e-11, "root_lr_tolerance": 1e-6, "limit_lr_tolerance": 1e-8,
    "weak_correlation": 0.98, "weak_interval_fold": 100,
}
ASSUMPTIONS = (
    "Rate records, not time points, are conditionally independent measurement units; biological N=1.",
    "Conditional iid additive normal rate errors, with a common unknown variance profiled by SSE/N.",
    "Substrate concentration, C.1 windows, observed blanks and calibration coefficients treated as fixed.",
    "Wilks chi-square approximation; no exact finite-sample or 95% coverage guarantee.",
    "No blank/calibration/concentration uncertainty, technical correlation or cross-batch biological propagation.",
    "C.1 initial_rate_validity remains NOT_ESTABLISHED.",
)


@dataclass(frozen=True)
class UncertaintyReview:
    reviewer: str
    reviewed_at_utc: str
    rationale: str
    independence_justification: str
    input_sha256: str
    c2a_result_sha256: str
    independent_units: tuple[tuple[str, str], ...]
    conditional_independence_accepted: bool = False
    homoscedastic_normal_errors_accepted: bool = False
    fixed_calibration_blanks_windows_accepted: bool = False
    error_model: str = ERROR_MODEL


class ProfileNumericalError(ValueError):
    """A profile cannot be trusted; never substitute a search limit for a root."""


class ResultIntegrityError(ProfileNumericalError):
    def __init__(self, code, path, stage="FINAL_RESULT_VALIDATION"):
        self.code, self.path, self.stage = code, path, stage
        super().__init__(f"{code} at {path} ({stage})")

    def issue(self):
        return {"code":self.code,"path":self.path,"stage":self.stage,"message":str(self)}


def _json_tree(value, *, failure_snapshot=False):
    """Normalize real scalars/containers without allowing nonfinite JSON numbers.

    Only an already rejected result may replace invalid leaves, with explicit
    paths/codes. Original caller objects are never changed. NumPy stays optional.
    """
    issues, active = [], set()

    def invalid(code, path):
        error = ResultIntegrityError(code,path)
        if not failure_snapshot:
            raise error
        issues.append(error.issue())
        return None

    def walk(v, path):
        if v is None or isinstance(v,bool):
            return v
        if isinstance(v,str):
            return str(v)
        if isinstance(v,Integral):
            return int(v)
        if isinstance(v,Real):
            try:
                converted = float(v)
            except (OverflowError,ValueError,TypeError):
                return invalid("REAL_SCALAR_CONVERSION_OVERFLOW",path)
            if not math.isfinite(converted):
                return invalid("NONFINITE_RESULT_NUMBER",path)
            return converted
        if type(v).__module__.startswith("numpy") and hasattr(v,"item") and getattr(v,"ndim",0)==0:
            native = v.item()
            if native is not v and type(native) is not type(v):
                return walk(native,path)
        dataclass_value = is_dataclass(v) and not isinstance(v,type)
        if isinstance(v,(dict,list,tuple)) or dataclass_value:
            if id(v) in active:
                return invalid("CYCLIC_RESULT_OBJECT",path)
            active.add(id(v))
            try:
                if dataclass_value:
                    return {f.name:walk(getattr(v,f.name),path+"."+f.name) for f in fields(v)}
                if isinstance(v,dict):
                    output = {}
                    for i,(key,item) in enumerate(v.items()):
                        if not isinstance(key,str):
                            invalid("NON_STRING_JSON_KEY",path+".<key>")
                            key = f"<invalid-key-{i}>"
                        output[str(key)] = walk(item,path+"."+str(key))
                    return output
                return [walk(item,f"{path}[{i}]") for i,item in enumerate(v)]
            finally:
                active.remove(id(v))
        return invalid("NON_JSON_RESULT_TYPE",path)

    return walk(value,"$"),issues


def validate_finite_json(value):
    """Return native JSON values, rejecting nonfinite or unsupported leaves.

    Handles nested dictionaries, lists/tuples, dataclass interval objects, and
    Python/NumPy real scalars. This is validation, never silent success repair.
    """
    normalized,_ = _json_tree(value)
    json.dumps(normalized,allow_nan=False,ensure_ascii=False,sort_keys=True)
    return normalized


def _restore_physical(value, scale, path, *, allow_none=False):
    if value is None:
        if allow_none:
            return None  # An explicit open statistical bound is not IEEE infinity.
        raise ResultIntegrityError("REQUIRED_RESULT_NUMBER",path,"PHYSICAL_UNIT_RESTORATION")
    value = validate_finite_json(value)
    scale = validate_finite_json(scale)
    if any(isinstance(v,bool) or not isinstance(v,(int,float)) or v<=0 for v in (value,scale)):
        raise ResultIntegrityError("POSITIVE_RESULT_NUMBER_REQUIRED",path,"PHYSICAL_UNIT_RESTORATION")
    try:
        restored = float(value)*float(scale)  # Python float overflow can be silent.
    except (OverflowError,ValueError,TypeError):
        raise ResultIntegrityError("PHYSICAL_UNIT_RESTORATION_OVERFLOW",path,"PHYSICAL_UNIT_RESTORATION") from None
    if not math.isfinite(restored):
        raise ResultIntegrityError("PHYSICAL_UNIT_RESTORATION_OVERFLOW",path,"PHYSICAL_UNIT_RESTORATION")
    if restored<=0:
        raise ResultIntegrityError("PHYSICAL_UNIT_RESTORATION_UNDERFLOW",path,"PHYSICAL_UNIT_RESTORATION")
    return restored


def _finalize_result(result):
    try:
        normalized = validate_finite_json(result)
        for name,p in normalized.get("parameters",{}).items():
            if p.get("status") in {"INTERVAL_ESTIMATED","WEAKLY_IDENTIFIABLE"}:
                values = [p.get(k) for k in ("lower","point_estimate","upper")]
                if (any(isinstance(v,bool) or not isinstance(v,(int,float)) for v in values)
                    or not 0 < values[0] < values[1] < values[2]):
                    raise ResultIntegrityError("INTERVAL_RESULT_CONTRACT",f"$.parameters.{name}")
    except (ResultIntegrityError,ValueError,TypeError,OverflowError) as exc:
        issue = exc.issue() if isinstance(exc,ResultIntegrityError) else {
            "code":"STRICT_JSON_SERIALIZATION_FAILED","stage":"FINAL_RESULT_VALIDATION","path":"$","message":str(exc)}
        # Already refused invalid inputs keep NOT_ESTIMABLE; computed results with
        # integrity failures become NUMERICAL_FAILURE, never successful nulls.
        if result["status"] != "NOT_ESTIMABLE":
            result["status"] = "NUMERICAL_FAILURE"
            for p in result.get("parameters",{}).values():
                p.update(status="NUMERICAL_FAILURE",lower=None,upper=None)
                p["reasons"].append(dict(issue))
        result["reasons"].append(issue)
        result["metadata"]["failure_stage"] = "FINAL_RESULT_VALIDATION"
        normalized,invalid_values = _json_tree(result,failure_snapshot=True)
        normalized["metadata"]["failure_snapshot_invalid_values"] = invalid_values
        normalized["metadata"]["failure_snapshot_sanitized"] = bool(invalid_values)
        normalized = validate_finite_json(normalized)
    normalized["metadata"]["result_sha256"] = digest(normalized)
    # Verify the complete object, including the final fingerprint, strictly.
    return validate_finite_json(normalized)


def _utc(stamp):
    return datetime.fromisoformat(stamp.replace("Z", "+00:00")).utcoffset() == timedelta(0)


class _Profile:
    def __init__(self, x, y, baseline, n, parameter, estimate, optimize):
        import numpy as np
        self.np, self.x, self.y = np, x, y
        self.baseline, self.n = baseline, n
        self.parameter, self.estimate, self.optimize = parameter, estimate, optimize
        self.cache = {}
        self.failures = []
        self.beta = float(x @ y / (x @ x))
        linear_residual = y - self.beta * x
        self.upper_sse = float(linear_residual @ linear_residual)
        if parameter == "Km":
            pred = np.where(x > 0, float(y[x > 0].mean()), 0.0)
            self.lower_sse = float((y - pred) @ (y - pred))
        else:
            self.lower_sse = float(y @ y)

    def lr(self, sse):
        if not math.isfinite(sse) or sse < 0:
            raise ProfileNumericalError("Non-finite or negative profile SSE")
        if sse < self.baseline - (1e-8 * self.baseline + self.n * 1e-24):
            raise ProfileNumericalError("Profile improves on C.2A beyond numerical tolerance; point estimate not changed")
        return self.n * math.log1p(max(0.0, sse - self.baseline) / self.baseline)

    def at(self, log_ratio):
        if log_ratio in self.cache:
            return self.cache[log_ratio]
        np, x, y = self.np, self.x, self.y
        target = self.estimate * math.exp(log_ratio)
        if not math.isfinite(target) or target <= 0:
            raise ProfileNumericalError("Target parameter not positive finite")
        domain, detail = "INTERIOR", {}
        if self.parameter == "Km":
            g = x / (target + x)
            gmax = float(g.max())
            if gmax <= 0:
                raise ProfileNumericalError("Underflow of MM response")
            h = g / gmax
            coefficient = float(h @ y / (h @ h))
            nuisance = coefficient / gmax
            residual = y - coefficient * h
            sse = float(residual @ residual)
            detail = {"method": "ANALYTIC_CONDITIONAL_VMAX", "success": True}
        else:
            a = max(1.0, target / self.beta)

            def objective(t):
                if t == 0:
                    predicted = np.where(x > 0, target, 0.0)
                elif t == 1:
                    predicted = np.zeros_like(x)
                else:
                    predicted = target * (x * (1 - t) / (a * t + x * (1 - t)))
                residual = y - predicted
                value = float(residual @ residual)
                if not math.isfinite(value):
                    raise ProfileNumericalError("Non-finite nuisance SSE")
                return value

            grid = np.linspace(0, 1, POLICY["nuisance_grid_points"])
            values = [objective(float(t)) for t in grid]
            candidates = [(values[0], 0.0), (values[-1], 1.0)]
            iterations = []
            brackets = [(float(grid[0]),float(grid[1])),(float(grid[-2]),float(grid[-1]))]
            for i in range(1, len(grid) - 1):
                if values[i] <= values[i-1] and values[i] <= values[i+1] and (values[i] < values[i-1] or values[i] < values[i+1]):
                    brackets.append((float(grid[i-1]),float(grid[i+1])))
            # Always refine edge cells: a shallow minimum can lie before the first
            # interior grid point, while both physical endpoint limits are valid.
            for bracket in sorted(set(brackets)):
                fit = self.optimize(objective, method="bounded", bounds=bracket,
                    options={"xatol": POLICY["nuisance_xatol"], "maxiter": POLICY["nuisance_maxiter"]})
                if not fit.success or not math.isfinite(float(fit.fun)) or not 0 < float(fit.x) < 1:
                    self.failures.append({"target_scaled":target,"log_ratio":log_ratio,
                        "optimizer_success":False,"bracket":list(bracket),"message":str(fit.message)})
                    raise ProfileNumericalError("Nuisance optimizer failed: " + str(fit.message))
                iterations.append({"success": True, "nfev": int(fit.nfev), "t": float(fit.x),"bracket":list(bracket)})
                candidates.append((objective(float(fit.x)), float(fit.x)))
            sse, t = min(candidates)
            nuisance = a * t / (1 - t) if 0 < t < 1 else None
            if t == 0:
                domain = "OPEN_KM_ZERO_LIMIT"
            elif t == 1:
                domain = "OPEN_KM_INFINITY_LIMIT"
            elif min(t, 1-t) < 1e-10:
                domain = "NEAR_OPEN_KM_LIMIT"
            detail = {"method": "BOUNDED_T_ALL_VISIBLE_GRID_MINIMA_AND_DOMAIN_LIMITS", "success": True,
                "t_scale": a, "t": t, "local_optimizations": iterations}
        if nuisance is not None and (not math.isfinite(nuisance) or nuisance <= 0):
            raise ProfileNumericalError("Nuisance parameter not positive finite")
        point = {"log_ratio": float(log_ratio), "target_scaled": target, "nuisance_scaled": nuisance,
            "scaled_sse": sse, "lr": self.lr(sse), "nuisance_domain": domain, "optimizer": detail}
        self.cache[log_ratio] = point
        return point

    def side(self, direction, critical, steps, brentq):
        limit_lr = self.lr(self.lower_sse if direction < 0 else self.upper_sse)
        result = {"value_scaled": None, "status": None, "domain_limit_lr": limit_lr,
            "log_search_limit": direction * steps * POLICY["log_scan_step"], "crossings": 0}
        if abs(limit_lr - critical) <= POLICY["limit_lr_tolerance"]:
            result["status"] = "LIMIT_THRESHOLD_UNRESOLVED"
            return result
        if limit_lr < critical:
            result["status"] = "OPEN_DOMAIN_LIMIT"
            return result
        previous_log, previous = 0.0, self.at(0.0)["lr"] - critical
        brackets, values = [], [previous + critical]
        for i in range(1, steps + 1):
            current_log = direction * i * POLICY["log_scan_step"]
            current = self.at(current_log)["lr"] - critical
            values.append(current + critical)
            if (current >= 0) != (previous >= 0):
                brackets.append(sorted((previous_log, current_log)))
            previous_log, previous = current_log, current
        result["crossings"] = len(brackets)
        if not brackets:
            result["status"] = "NUMERICAL_SEARCH_LIMIT"
        elif len(brackets) > 1:
            result["status"] = "DISCONNECTED_ACCEPTANCE_SET"
        else:
            low, high = brackets[0]
            root = float(brentq(lambda z: self.at(z)["lr"] - critical, low, high, xtol=POLICY["root_xtol"], maxiter=200))
            point = self.at(root)
            if abs(point["lr"] - critical) > min(POLICY["root_lr_tolerance"],critical*1e-6):
                raise ProfileNumericalError("Root LR does not satisfy declared threshold")
            result["root_lr"] = point["lr"]
            if point["nuisance_domain"] != "INTERIOR":
                result["status"] = "NUISANCE_DOMAIN_LIMIT"
            else:
                result["status"], result["value_scaled"] = "FINITE_ROOT", point["target_scaled"]
        # Decreasing LR away from the point estimate is an informative profile warning.
        result["nonmonotonic"] = any(b < a - 1e-6 for a, b in zip(values, values[1:]))
        return result


def analyze_mm_uncertainty(records, fit_review, c2a_result, review, *, confidence_level=0.95, scan_steps=80):
    """Return conditional profile intervals, retaining original inputs and results.

    No implicit iid assumption: UncertaintyReview must explicitly cover all IDs.
    All calculations are in memory; no database, file, Provider or model access.
    """
    records, c2a_result = deepcopy(tuple(records)), deepcopy(c2a_result)
    result = {"status": "NOT_ESTIMABLE", "parameters": {}, "reasons": [], "quality_control": [],
        "c2a_result": c2a_result, "statistical_model": {"error_model": ERROR_MODEL, "assumptions": list(ASSUMPTIONS)},
        "metadata": {"analysis_version": ANALYSIS_VERSION, "initial_rate_validity": "NOT_ESTABLISHED",
            "serialization_contract":"FINITE_JSON_V1",
            "parameter_space": "Km>0, Vmax>0", "confidence_level": confidence_level,
            "scan_steps": scan_steps, "policy": dict(POLICY), "method": METHOD}}
    def fail(code, message, status="NOT_ESTIMABLE", stage="INPUT_QUALIFICATION"):
        result["status"] = status
        result["metadata"]["failure_stage"] = stage
        result["reasons"].append({"code": code, "message": message, "stage": stage})
    def finish():
        return _finalize_result(result)
    try:
        if isinstance(confidence_level, bool) or not math.isfinite(float(confidence_level)) or not 0 < confidence_level < 1:
            raise ValueError("Confidence level must be a finite probability")
        if isinstance(scan_steps, bool) or not isinstance(scan_steps, int) or not 1 <= scan_steps <= 80:
            raise ValueError("Explicit scan_steps must be an integer in 1..80; no endpoint is a confidence bound")
        if c2a_result.get("status") != "FIT_WITH_LIMITATIONS":
            raise ValueError("C.2A status is not eligible")
        replay = fit_michaelis_menten(records, fit_review)
        if canonical(replay) != canonical(c2a_result):
            raise ValueError("C.2A inputs/configuration/result do not replay exactly")
        if any(not isinstance(r.provenance,dict) or not r.provenance for r in records):
            raise ValueError("Explicit source provenance is required for every rate record")
        result["metadata"].update(input_sha256=input_digest(records), c2a_result_sha256=c2a_result["metadata"]["result_sha256"])
        result["review"] = asdict(review)
        units = dict(review.independent_units)
        if (not _utc(review.reviewed_at_utc) or any(not isinstance(v,str) or not v.strip()
            for v in (review.reviewer, review.rationale, review.independence_justification))
            or review.error_model != ERROR_MODEL
            or review.conditional_independence_accepted is not True
            or review.homoscedastic_normal_errors_accepted is not True
            or review.fixed_calibration_blanks_windows_accepted is not True
            or review.input_sha256 != input_digest(records)
            or review.c2a_result_sha256 != c2a_result["metadata"]["result_sha256"]
            or len(units) != len(review.independent_units) or set(units) != {r.analysis_id for r in records}
            or len(set(units.values())) != len(records)
            or any(not isinstance(v,str) or not v.strip() for v in units.values())):
            raise ValueError("Explicit input-bound conditional error/independence review with unique measurement units required")
    except (ValueError, TypeError, KeyError, AttributeError, OverflowError) as exc:
        fail("INPUT_OR_ASSUMPTIONS_INELIGIBLE", str(exc))
        return finish()
    p = c2a_result["parameters"]
    for name in ("Km", "Vmax"):
        result["parameters"][name] = {"point_estimate": p[name], "unit": p[name+"_unit"],
            "lower": None, "upper": None, "confidence_level": confidence_level, "method": METHOD,
            "assumptions": list(ASSUMPTIONS), "status": "NOT_ESTIMABLE", "reasons": [], "diagnostics": {}, "profile": []}
    points = c2a_result["predictions"]
    n = len(points)
    result["statistical_model"].update(n=n, biological_n=1, independent_measurement_n=len(units),
        variance_estimator="MLE_SSE_DIVIDED_BY_N", variance_mle=c2a_result["statistics"]["sse"] / n,
        variance_unit="("+p["Vmax_unit"]+")^2")
    if n < POLICY["minimum_n"]:
        fail("INSUFFICIENT_RATE_RECORDS", "N<6; conservative implementation policy, not a universal minimum theorem")
        for r in result["parameters"].values():r["reasons"] = deepcopy(result["reasons"])
        return finish()
    try:
        import numpy as np
        import scipy
        from scipy.optimize import brentq, minimize_scalar
        from scipy.stats import chi2
    except ImportError as exc:
        fail("DEPENDENCY_UNAVAILABLE", str(exc), stage="DEPENDENCY_INITIALIZATION")
        return finish()
    try:
        with np.errstate(over="raise", divide="raise", invalid="raise"):
            rate_scale = max(abs(r["observed_rate"]) for r in points)
            substrate_scale = c2a_result["optimizer"]["scales"]["substrate"]
            x = np.asarray([r["substrate_concentration"] / substrate_scale for r in points])
            y = np.asarray([r["observed_rate"] / rate_scale for r in points])
            baseline = math.fsum(((r["observed_rate"] - r["fitted_rate"]) / rate_scale)**2 for r in points)
            critical = float(chi2.ppf(confidence_level, 1))
            if not math.isfinite(critical) or critical <= 0:
                raise ProfileNumericalError("Confidence cutoff is below finite positive numerical resolution")
            result["metadata"].update(dependencies={"numpy":np.__version__,"scipy":scipy.__version__},
                scales={"rate":rate_scale,"substrate":substrate_scale})
            result["statistical_model"].update(lr_definition="N*log(SSE_profile/SSE_min)",
                critical_distribution="ASYMPTOTIC_CHI_SQUARE_1", critical_value=critical,
                sse_ratio_cutoff=math.exp(critical/n), scaled_sse_min=baseline)
            if baseline / n <= POLICY["normalized_variance_floor"]:
                fail("VARIANCE_DEGENERATE", "Zero/near-zero residual variance: no point interval and no invented noise floor", stage="VARIANCE_ESTIMATION")
                for r in result["parameters"].values():r["reasons"] = deepcopy(result["reasons"])
                return finish()
            if n < POLICY["small_sample_n"]:
                result["quality_control"].append({"code":"SMALL_SAMPLE_APPROXIMATION","message":"Nonlinear Wilks intervals may have poor finite-sample coverage"})
            km, vmax = p["Km"] / substrate_scale, p["Vmax"] / rate_scale
            fitted = vmax * x / (km+x)
            jac = np.column_stack((fitted, -fitted*km/(km+x)))
            gram = jac.T @ jac
            correlation = float(-gram[0,1] / np.sqrt(gram[0,0]*gram[1,1]))
            cond = float(np.linalg.cond(jac))
            if not all(math.isfinite(v) for v in (critical, correlation, cond)):
                raise ProfileNumericalError("Non-finite local diagnostic")
            result["local_diagnostics"] = {"log_parameter_correlation":correlation,"log_jacobian_condition":cond,
                "interpretation":"Local approximation only; no covariance confidence interval calculated"}
            c2a_warnings = {q["code"] for q in c2a_result["quality_control"]}
            for name, estimate, scale in (("Km",km,substrate_scale),("Vmax",vmax,rate_scale)):
                output = result["parameters"][name]
                profile = _Profile(x, y, baseline, n, name, estimate, minimize_scalar)
                try:
                    profile.at(0.0)
                    lower = profile.side(-1,critical,scan_steps,brentq)
                    upper = profile.side(1,critical,scan_steps,brentq)
                    output["diagnostics"] = {"lower_endpoint":lower,"upper_endpoint":upper,
                        "log_parameter_correlation":correlation,"log_jacobian_condition":cond}
                    output["lower"] = _restore_physical(lower["value_scaled"],scale,f"$.parameters.{name}.lower",allow_none=True)
                    output["upper"] = _restore_physical(upper["value_scaled"],scale,f"$.parameters.{name}.upper",allow_none=True)
                    if upper["status"] == "OPEN_DOMAIN_LIMIT":
                        output["status"] = "NOT_IDENTIFIABLE"
                        output["reasons"].append({"code":"ACCEPTED_UNBOUNDED_TAIL","message":"Analytic domain limit is accepted; structural versus practical cause not determined"})
                    elif lower["status"] != "FINITE_ROOT" or upper["status"] != "FINITE_ROOT":
                        output["status"] = "BOUNDARY_LIMITED"
                        output["reasons"].append({"code":"ENDPOINT_NOT_RELIABLY_FINITE","message":"An open domain, disconnected set or numerical search limit is not a finite interval"})
                    else:
                        if not 0 < output["lower"] < p[name] < output["upper"]:
                            raise ProfileNumericalError("Finite interval endpoints do not resolve both sides of the estimate")
                        weak = (abs(correlation)>POLICY["weak_correlation"]
                            or output["upper"]/output["lower"]>POLICY["weak_interval_fold"]
                            or lower.get("nonmonotonic") or upper.get("nonmonotonic")
                            or bool(c2a_warnings.intersection({"SATURATION_NOT_COVERED","LOW_CONCENTRATIONS_NOT_COVERED","NARROW_CONCENTRATION_RANGE","ILL_CONDITIONED_PARAMETERS"})))
                        output["status"] = "WEAKLY_IDENTIFIABLE" if weak else "INTERVAL_ESTIMATED"
                        output["diagnostics"]["interval_fold"] = output["upper"]/output["lower"]
                        output["diagnostics"]["asymmetry_ratio"] = (output["upper"]-p[name])/(p[name]-output["lower"])
                        if weak:output["reasons"].append({"code":"FINITE_BUT_WEAK","message":"Finite conditional interval with strong correlation, limited coverage, width or profile warning"})
                except ResultIntegrityError as exc:
                    output.update(status="NUMERICAL_FAILURE",lower=None,upper=None)
                    output["reasons"].append(exc.issue())
                    result["reasons"].append(exc.issue())
                    result["metadata"]["failure_stage"] = exc.stage
                except (ValueError, RuntimeError, FloatingPointError, OverflowError) as exc:
                    output.update(status="NUMERICAL_FAILURE",lower=None,upper=None)
                    output["reasons"].append({"code":"PROFILE_NUMERICAL_FAILURE","message":str(exc),"stage":"PROFILE_OPTIMIZATION_OR_ROOT"})
                    result["metadata"]["failure_stage"] = "PROFILE_OPTIMIZATION_OR_ROOT"
                output["diagnostics"]["optimizer_failures"] = deepcopy(profile.failures)
                # Preserve the full normalized trace first. Restore physical units
                # atomically; an overflowing partial trace is never returned.
                output["profile"] = [deepcopy(point) for _,point in sorted(profile.cache.items())]
                output["profile_representation"] = "SCALED_ONLY"
                try:
                    restored = [dict(point,
                        target_value=_restore_physical(point["target_scaled"],scale,f"$.parameters.{name}.profile[{i}].target_value"),
                        nuisance_value=_restore_physical(point["nuisance_scaled"],rate_scale if name=="Km" else substrate_scale,
                            f"$.parameters.{name}.profile[{i}].nuisance_value",allow_none=point["nuisance_domain"]!="INTERIOR")) for i,point in enumerate(output["profile"])]
                    output["profile"] = restored
                    output["profile_representation"] = "SCALED_AND_PHYSICAL"
                except ResultIntegrityError as exc:
                    output.update(status="NUMERICAL_FAILURE",lower=None,upper=None)
                    output["reasons"].append(exc.issue())
                    output["diagnostics"]["physical_unit_restoration"] = exc.issue()
                    result["reasons"].append(exc.issue())
                    result["metadata"]["failure_stage"] = exc.stage
            priority = {"INTERVAL_ESTIMATED":0,"WEAKLY_IDENTIFIABLE":1,"BOUNDARY_LIMITED":2,"NOT_IDENTIFIABLE":3,"NOT_ESTIMABLE":4,"NUMERICAL_FAILURE":5}
            result["status"] = max((o["status"] for o in result["parameters"].values()),key=priority.get)
    except (ValueError, RuntimeError, FloatingPointError, OverflowError, np.linalg.LinAlgError) as exc:
        fail("NUMERICAL_FAILURE",str(exc),"NUMERICAL_FAILURE",stage="UNCERTAINTY_COMPUTATION")
        for r in result["parameters"].values():r.update(status="NUMERICAL_FAILURE",lower=None,upper=None,reasons=deepcopy(result["reasons"]))
    return finish()
