"""Deterministic, explicitly windowed OLS of a single experimental time course.

No interval search, imputation, replicate pooling, enzyme model, or AI call.
An estimated slope does NOT establish biochemical initial-rate validity.
"""
from dataclasses import asdict, dataclass
from datetime import datetime, timezone
import hashlib
import json
import math
import re

ANALYSIS_VERSION = "initial-rate-1.0.0"
TIME_UNITS = frozenset({"s", "sec", "second", "seconds", "min", "minute", "minutes", "h", "hour", "hours", "ms"})
PRODUCT_UNITS = frozenset({"M", "mM", "uM", "µM", "μM", "nM", "mol/L", "mmol/L", "umol/L", "µmol/L", "nmol/L"})


@dataclass(frozen=True)
class Observation:
    observation_id: str
    batch_id: str
    sample_id: str
    time_value: object
    raw_signal: object
    time_unit: str
    signal_unit: str
    source_file_id: str
    source_sha256: str
    biological_replicate: object = None
    technical_replicate: object = None
    substrate_concentration: object = None
    substrate_concentration_unit: str | None = None
    well_id: object = None
    blank_signal: object = None


@dataclass(frozen=True)
class Calibration:
    calibration_id: str
    source_file_id: str
    source_sha256: str
    signal_unit: str
    product_unit: str
    signal_per_product: object
    intercept: object
    valid_signal_min: object
    valid_signal_max: object
    blank_mode: str
    quantity: str = "product_concentration"


@dataclass(frozen=True)
class RateConfig:
    start: float
    end: float
    time_unit: str
    blank_mode: str = "none"  # none / per_observation / matched_time
    missing_policy: str = "fail"  # fail / exclude (explicit, recorded)
    exclusions: tuple[tuple[str, str], ...] = ()
    measurement_kind: str = "TIME_COURSE"
    low_r_squared_warning: float = 0.98
    segment_change_warning: float = 0.20


def _safe(value):
    if isinstance(value, float) and not math.isfinite(value):
        return {"nonfinite_numeric": repr(value)}
    if isinstance(value, dict):
        return {str(k): _safe(v) for k, v in value.items()}
    if isinstance(value, (list, tuple)):
        return [_safe(v) for v in value]
    return value


def canonical(value):
    return json.dumps(_safe(value), ensure_ascii=False, sort_keys=True, separators=(",", ":"), allow_nan=False)


def digest(value):
    return hashlib.sha256(canonical(value).encode("utf-8")).hexdigest()


def _number(value):
    if isinstance(value, bool):
        raise ValueError("Boolean is not a measurement")
    result = float(value)
    if not math.isfinite(result):
        raise ValueError("Non-finite measurement")
    return result


def series_key(o):
    """Do not merge wells, substrate levels or biological/technical replicates."""
    return canonical([o.batch_id, o.sample_id, o.biological_replicate, o.technical_replicate,
                      o.well_id, o.substrate_concentration, o.substrate_concentration_unit,
                      o.time_unit, o.signal_unit])


def _provenance_valid(o):
    return bool(o.observation_id and o.batch_id and o.sample_id and o.source_file_id
                and isinstance(o.source_sha256, str) and re.fullmatch("[a-fA-F0-9]{64}", o.source_sha256))


def calibration_parameters(c, signal_unit, blank_mode):
    k, offset = _number(c.signal_per_product), _number(c.intercept)
    lo, hi = _number(c.valid_signal_min), _number(c.valid_signal_max)
    if (not k or lo >= hi or c.signal_unit != signal_unit or c.product_unit not in PRODUCT_UNITS
        or c.blank_mode != blank_mode or blank_mode not in {"none", "per_observation", "matched_time"}
        or c.quantity != "product_concentration" or not c.calibration_id or not c.source_file_id
        or not isinstance(c.source_sha256, str) or not re.fullmatch("[a-fA-F0-9]{64}", c.source_sha256)):
        raise ValueError("Invalid calibration metadata")
    return k, offset, lo, hi


def _ols(points):
    n = len(points)
    mx = math.fsum(x for x, _ in points) / n
    my = math.fsum(y for _, y in points) / n
    xx = math.fsum((x - mx) ** 2 for x, _ in points)
    slope = math.fsum((x - mx) * (y - my) for x, y in points) / xx
    intercept = my - slope * mx
    residuals = [y - (intercept + slope * x) for x, y in points]
    sse = math.fsum(r * r for r in residuals)
    yy = math.fsum((y - my) ** 2 for _, y in points)
    mse = sse / (n - 2)
    return dict(slope=slope, intercept=intercept, residuals=residuals, sse=sse,
                r_squared=1 - sse / yy if yy else None, rmse=math.sqrt(sse / n),
                slope_standard_error=math.sqrt(mse / xx),
                intercept_standard_error=math.sqrt(mse * (1 / n + mx * mx / xx)), n=n, degrees_of_freedom=n - 2)


def analyze_initial_rate(observations, config, *, blanks=(), calibration=None, calculated_at=None):
    observations, blanks = tuple(observations), tuple(blanks)
    raw = [asdict(o) for o in observations]
    raw_blanks = [asdict(o) for o in blanks]
    cfg = asdict(config)
    cal = asdict(calibration) if calibration is not None else None
    payload = {"raw_observations": raw, "blank_observations": raw_blanks, "configuration": cfg, "calibration": cal}
    result = {"status": "NOT_ESTIMABLE", "reasons": [], "raw_observations": raw,
              "blank_observations": raw_blanks, "corrected_observations": [], "derived_initial_rate": None,
              "quality_control": [], "observation_decisions": [],
              "blank_observation_decisions": [{"observation_id": b.observation_id, "included": False, "reason": "NOT_USED_FOR_SELECTED_OBSERVATIONS"} for b in blanks],
              "analysis_metadata": {"analysis_version": ANALYSIS_VERSION, "configuration": cfg, "calibration": cal,
                  "input_sha256": digest(payload), "calculated_at_utc": calculated_at or datetime.now(timezone.utc).isoformat(),
                  "initial_rate_validity": "NOT_ESTABLISHED", "regression": "ordinary least squares with intercept",
                  "uncertainty": "conditional OLS standard errors; no calibration/blank uncertainty propagation; no biological replicate inference"}}
    def warning(code, message):
        result["quality_control"].append({"code": code, "severity": "WARNING", "message": message})
    def fail(code, message):
        result["reasons"].append({"code": code, "message": message})
    def finish():
        timestamp = result["analysis_metadata"].pop("calculated_at_utc")
        result["analysis_metadata"]["analysis_fingerprint"] = digest(result)
        result["analysis_metadata"]["calculated_at_utc"] = timestamp
        return _safe(result)
    warning("INITIAL_RATE_NOT_VERIFIED", "线性拟合本身不能确认初始速率；需人工核实混合延迟、底物消耗、检测范围与实验条件。")
    warning("OLS_UNCERTAINTY_LIMITED", "标准误仅为独立同方差误差假设下的条件 OLS 估计；未传播空白/标定误差或建模时间相关性，不等于生物重复不确定性。")
    try:
        stamp=datetime.fromisoformat(result["analysis_metadata"]["calculated_at_utc"].replace("Z", "+00:00"))
        if stamp.utcoffset() is None or stamp.utcoffset().total_seconds()!=0:
            raise ValueError
        start, end = _number(config.start), _number(config.end)
        if start >= end or config.time_unit not in TIME_UNITS or config.blank_mode not in {"none", "per_observation", "matched_time"} or config.missing_policy not in {"fail", "exclude"}:
            raise ValueError
        if not 0 <= _number(config.low_r_squared_warning) <= 1 or _number(config.segment_change_warning) < 0:
            raise ValueError
        excluded = dict(config.exclusions)
        if len(excluded) != len(config.exclusions) or any(not k or not str(v).strip() for k, v in config.exclusions):
            raise ValueError
    except (ValueError, TypeError):
        fail("INVALID_CONFIGURATION", "区间、单位、缺失处理或排除理由不合法。")
        return finish()
    if config.measurement_kind != "TIME_COURSE":
        fail("NOT_TIME_COURSE", "终点测定不能当作初始速率时间序列。")
    ids = [o.observation_id for o in observations]
    if len(set(ids)) != len(ids):
        fail("DUPLICATE_OBSERVATION_ID", "重复 observation_id；不静默去重。")
    if not observations:
        fail("NO_OBSERVATIONS", "没有时间序列观测。")
    if set(excluded) - set(ids):
        fail("UNKNOWN_EXCLUSION", "排除 ID 不属于当前输入。")
    if any(not _provenance_valid(o) for o in (*observations, *blanks)):
        fail("INCOMPLETE_PROVENANCE", "观测缺少 ID、样品、批次或原件 ID/SHA256。")
    if len({series_key(o) for o in observations}) > 1:
        fail("MIXED_SERIES", "不能混合不同样品/批次、孔位、底物、单位或生物/技术重复。")
    if any(o.time_unit != config.time_unit or not isinstance(o.signal_unit, str) or not o.signal_unit.strip() for o in observations):
        fail("UNIT_MISMATCH", "时间单位必须与区间完全一致，信号单位不能为空；不隐式换算。")
    if result["reasons"]:
        return finish()
    first = observations[0]
    if first.biological_replicate is None or first.technical_replicate is None:
        warning("REPLICATE_ID_MISSING", "缺少重复编号；不推断重复关系或跨重复合并。")
    if first.substrate_concentration is None:
        warning("SUBSTRATE_MISSING", "未报告底物浓度，不能核实初始速率条件。")
    else:
        try:
            if _number(first.substrate_concentration) < 0 or not first.substrate_concentration_unit:
                raise ValueError
        except (ValueError, TypeError):
            fail("INVALID_SUBSTRATE", "底物浓度需有限、非负且有单位。")
    if config.blank_mode == "none":
        warning("NO_BLANK_CORRECTION", "用户选择不作空白校正；不能视为背景为零。")
        if blanks:
            fail("UNUSED_BLANKS", "已提供空白观测但未选择匹配空白模式。")
    elif config.blank_mode != "matched_time" and blanks:
        fail("UNUSED_BLANKS", "逐行空白模式不能同时忽略另行提供的空白序列。")
    blank_map = {}
    if config.blank_mode == "matched_time":
        if not blanks or len({series_key(o) for o in blanks}) != 1:
            fail("INVALID_BLANK_SERIES", "需提供单一空白序列；不平均或混合空白重复。")
        for b in blanks:
            if b.batch_id != first.batch_id or b.time_unit != first.time_unit or b.signal_unit != first.signal_unit:
                fail("BLANK_UNIT_OR_BATCH_MISMATCH", "空白批次及时间/信号单位必须匹配。")
            if b.observation_id in ids or b.observation_id in {v[1] for v in blank_map.values()}:
                fail("BLANK_ID_COLLISION", "空白观测 ID 与样品/其他空白冲突。")
            try:
                t, y = _number(b.time_value), _number(b.raw_signal)
                if t in blank_map:
                    fail("DUPLICATE_BLANK_TIME", "同一时刻有多个空白值；需先经另行协议处理，不自动平均。")
                blank_map[t] = (y, b.observation_id)
            except (ValueError, TypeError):
                fail("INVALID_BLANK_VALUE", "匹配空白必须包含有限时间和信号。")
    if result["reasons"]:
        return finish()
    points, included, selected_times = [], [], []
    for o in observations:
        decision = {"observation_id": o.observation_id, "included": False, "reason": None}
        result["observation_decisions"].append(decision)
        if o.observation_id in excluded:
            decision["reason"] = "USER_EXCLUSION: " + excluded[o.observation_id]
            continue
        if o.time_value is None or o.raw_signal is None:
            decision["reason"] = "MISSING_TIME_OR_SIGNAL"
            if config.missing_policy == "fail":
                fail("MISSING_OBSERVATION", "缺失观测需要显式 exclude 策略或逐条排除理由。")
            continue
        try:
            t, y = _number(o.time_value), _number(o.raw_signal)
        except (ValueError, TypeError):
            decision["reason"] = "INVALID_NUMERIC_VALUE"
            fail("INVALID_NUMERIC_VALUE", "非有限/无效数值不自动过滤。")
            continue
        if not start <= t <= end:
            decision["reason"] = "OUTSIDE_EXPLICIT_INTERVAL"
            continue
        blank_value, blank_id = None, None
        if config.blank_mode == "per_observation":
            try:
                blank_value = _number(o.blank_signal)
            except (ValueError, TypeError):
                fail("MISSING_OR_INVALID_BLANK", "区间内每个观测都需有有效的显式空白。")
                decision["reason"] = "MISSING_OR_INVALID_BLANK"
                continue
        elif config.blank_mode == "matched_time":
            if t not in blank_map:
                fail("UNMATCHED_BLANK", "缺少完全同一时刻的空白；不插值、不外推。")
                decision["reason"] = "UNMATCHED_BLANK"
                continue
            blank_value, blank_id = blank_map[t]
        corrected = y - blank_value if blank_value is not None else y
        if not math.isfinite(corrected):
            fail("NUMERICAL_RANGE", "校正后超出可表示数值范围。")
            continue
        result["corrected_observations"].append({"observation_id": o.observation_id, "time_value": t,
            "raw_signal": y, "blank_value": blank_value, "blank_observation_id": blank_id,
            "corrected_signal": corrected, "correction_applied": blank_value is not None,
            "time_unit": o.time_unit, "signal_unit": o.signal_unit})
        points.append((t, corrected)); included.append(o.observation_id); selected_times.append(t)
        decision.update(included=True, reason="INCLUDED")
    if any(d["reason"] == "MISSING_TIME_OR_SIGNAL" for d in result["observation_decisions"]):
        warning("MISSING_DATA", "存在缺失观测；处理方式和每条排除均保留。")
    used_blank_ids={o["blank_observation_id"] for o in result["corrected_observations"] if o["blank_observation_id"]}
    for decision in result["blank_observation_decisions"]:
        if decision["observation_id"] in used_blank_ids:
            decision.update(included=True,reason="MATCHED_TO_INCLUDED_OBSERVATION")
    if len(points) < 3 or len(set(selected_times)) < 3:
        fail("INSUFFICIENT_TIME_POINTS", "至少需要三个不同时间点；单点终点值和两点差分不作为本模块初始速率拟合。")
    if result["reasons"]:
        return finish()
    if len(set(selected_times)) != len(points):
        warning("REPEATED_TIME_POINTS", "同一重复序列内同一时刻的不同 ID 均保留，未平均；OLS 标准误未建模相关性。")
    try:
        fit = _ols(points)
        if any(isinstance(v, float) and not math.isfinite(v) for v in fit.values()) or any(not math.isfinite(r) for r in fit["residuals"]):
            raise ValueError
    except (ValueError, OverflowError, ZeroDivisionError):
        fail("NUMERICAL_RANGE", "回归数值超出浮点可表示范围；未输出速率。")
        return finish()
    if fit["r_squared"] is None:
        warning("CONSTANT_SIGNAL", "信号无变异；R² 未定义。零斜率是计算值，不等于缺失。")
    elif fit["r_squared"] < _number(config.low_r_squared_warning):
        warning("LOW_LINEARITY", "低于所记录的 R² 警示标准；未自动删点或改变拟合区间。")
    ordered = sorted(points)
    if len(set(selected_times)) >= 4 and len(selected_times) == len(set(selected_times)):
        half = len(ordered) // 2
        def secant(p):
            return (p[-1][1] - p[0][1]) / (p[-1][0] - p[0][0])
        early, late = secant(ordered[:half]), secant(ordered[half:])
        change = abs(early - late) / max(abs(early), abs(late), 1e-300)
        fit["segment_relative_slope_change"] = change
        if change > _number(config.segment_change_warning):
            warning("CURVATURE_SUSPECTED", "前后区段斜率变化超过配置警示值；这只是进程非线性筛查，不能验证反应机制。")
    valid_input_times = []
    for o in observations:
        try:
            valid_input_times.append(_number(o.time_value))
        except (TypeError, ValueError):
            pass
    if min(selected_times) > min(valid_input_times, default=min(selected_times)):
        warning("EARLIER_OBSERVATIONS_EXCLUDED", "窗口未覆盖最早观测；需人工说明为何仍用于初始速率。")
    product = None
    if calibration is None:
        warning("NO_PRODUCT_CALIBRATION", "仅输出信号/时间斜率；无充分标定，不换算产物浓度或酶活。")
    else:
        try:
            k, offset, lo, hi = calibration_parameters(calibration, first.signal_unit, config.blank_mode)
            if any(not lo <= y <= hi for _, y in points):
                warning("OUTSIDE_CALIBRATION_RANGE", "信号超出已报告标定范围；保留信号斜率，不外推产物速率。")
            else:
                concentrations = [(y - offset) / k for _, y in points]
                if any(not math.isfinite(c) or c < 0 for c in concentrations):
                    warning("INVALID_CONVERTED_CONCENTRATION", "标定产生负值或非有限浓度；不截零、不输出产物速率。")
                else:
                    product = {"slope": fit["slope"] / k, "intercept": (fit["intercept"] - offset) / k,
                        "slope_standard_error": fit["slope_standard_error"] / abs(k),
                        "rate_unit": calibration.product_unit + "/" + config.time_unit,
                        "product_concentrations": concentrations, "calibration_id": calibration.calibration_id}
                    if any(not math.isfinite(product[key]) for key in ("slope","intercept","slope_standard_error")):
                        raise ValueError
        except (ValueError, TypeError, OverflowError, ZeroDivisionError):
            fail("INVALID_CALIBRATION", "标定必须有明确公式、非零系数、截距、有效范围、产物单位、校正基准与来源；不猜测。")
            return finish()
    result["status"] = "ESTIMATED"
    result["derived_initial_rate"] = {**fit, "rate_unit": first.signal_unit + "/" + config.time_unit,
        "intercept_unit": first.signal_unit, "included_observation_ids": included,
        "batch_id": first.batch_id, "sample_id": first.sample_id, "biological_replicate": first.biological_replicate,
        "technical_replicate": first.technical_replicate, "substrate_concentration": first.substrate_concentration,
        "substrate_concentration_unit": first.substrate_concentration_unit, "product_rate": product}
    return finish()
