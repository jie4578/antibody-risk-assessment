"""Synthetic numerical expectations; no private measurements, AI or fitting models."""
from dataclasses import replace
import math

import pytest

from protein_engineering.initial_rate import Calibration, Observation, RateConfig, analyze_initial_rate

SHA = "a" * 64


def observations(times=(0, 1, 2, 3, 4), slope=2, intercept=5):
    return [Observation(f"SYN-{i}", "B", "S", t, slope*t+intercept, "min", "RFU", "source-1", SHA,
                        "BIO-1", "TECH-1", 1, "mM", "A1") for i, t in enumerate(times)]


def config(**kwargs):
    return RateConfig(**dict(start=0, end=4, time_unit="min", **kwargs))


def codes(result):
    return {i["code"] for i in result["quality_control"] + result["reasons"]}


def calibration(**kwargs):
    fields = dict(calibration_id="SYN-CAL", source_file_id="cal-source", source_sha256="b"*64,
        signal_unit="RFU", product_unit="uM", signal_per_product=2, intercept=5,
        valid_signal_min=0, valid_signal_max=100, blank_mode="none")
    return Calibration(**(fields | kwargs))


@pytest.mark.parametrize("slope", [2, -2, 0])
def test_exact_analytic_slope_and_direction(slope):
    result = analyze_initial_rate(observations(slope=slope, intercept=20), config())
    fit = result["derived_initial_rate"]
    assert result["status"] == "ESTIMATED"
    assert fit["slope"] == slope and fit["intercept"] == 20
    assert fit["slope_standard_error"] == 0
    assert fit["residuals"] == [0]*5
    assert fit["rate_unit"] == "RFU/min" and fit["product_rate"] is None
    assert result["analysis_metadata"]["initial_rate_validity"] == "NOT_ESTABLISHED"
    assert "INITIAL_RATE_NOT_VERIFIED" in codes(result)
    if slope == 0:
        assert fit["r_squared"] is None and "CONSTANT_SIGNAL" in codes(result)


def test_irregular_spacing_and_per_observation_blank():
    raw = [replace(o, raw_signal=o.raw_signal + o.time_value*3, blank_signal=o.time_value*3)
           for o in observations(times=(0, .2, .9, 2.1, 4))]
    result = analyze_initial_rate(raw, config(blank_mode="per_observation"))
    assert result["derived_initial_rate"]["slope"] == pytest.approx(2)
    assert result["raw_observations"][0]["blank_signal"] == 0
    assert all(o["correction_applied"] for o in result["corrected_observations"])


def test_matched_blank_drift_correction_has_own_provenance():
    raw = observations(slope=5)
    blank = [replace(o, observation_id="BLANK-"+o.observation_id, sample_id="BLANK", raw_signal=3*o.time_value,
                     source_file_id="blank-source", source_sha256="b"*64) for o in raw]
    result = analyze_initial_rate(raw, config(blank_mode="matched_time"), blanks=blank)
    assert result["derived_initial_rate"]["slope"] == 2
    assert result["blank_observations"][0]["source_sha256"] == "b"*64
    assert result["corrected_observations"][0]["blank_observation_id"] == "BLANK-SYN-0"
    assert all(d["included"] for d in result["blank_observation_decisions"])


@pytest.mark.parametrize("mutation,expected", [
    (lambda b: b[:-1], "UNMATCHED_BLANK"),
    (lambda b: b+[replace(b[0], observation_id="other")], "DUPLICATE_BLANK_TIME"),
    (lambda b: [replace(x, signal_unit="AU") for x in b], "BLANK_UNIT_OR_BATCH_MISMATCH"),
])
def test_blank_never_interpolated_or_averaged(mutation, expected):
    raw=observations()
    blank=[replace(x, observation_id="BLANK-"+x.observation_id, sample_id="BLANK", raw_signal=0) for x in raw]
    result=analyze_initial_rate(raw, config(blank_mode="matched_time"), blanks=mutation(blank))
    assert result["status"]=="NOT_ESTIMABLE" and expected in codes(result)


def test_calibrated_product_rate_matches_independent_expectation():
    result=analyze_initial_rate(observations(), config(), calibration=calibration())
    product=result["derived_initial_rate"]["product_rate"]
    assert product["slope"] == 1 and product["intercept"] == 0
    assert product["product_concentrations"] == [0,1,2,3,4]
    assert product["rate_unit"] == "uM/min"


def test_negative_calibration_coefficient_for_decreasing_product_reporter():
    result=analyze_initial_rate(observations(slope=-2, intercept=20), config(),
        calibration=calibration(signal_per_product=-2, intercept=20))
    assert result["derived_initial_rate"]["slope"] == -2
    assert result["derived_initial_rate"]["product_rate"]["slope"] == 1


@pytest.mark.parametrize("override", [dict(signal_per_product=0), dict(intercept=None), dict(valid_signal_min=None),
    dict(signal_unit="AU"), dict(product_unit=""), dict(source_sha256="bad"), dict(blank_mode="matched_time"),
    dict(quantity="substrate"), dict(valid_signal_min=100,valid_signal_max=0)])
def test_invalid_calibration_cannot_manufacture_product(override):
    result=analyze_initial_rate(observations(), config(), calibration=calibration(**override))
    assert result["status"]=="NOT_ESTIMABLE" and "INVALID_CALIBRATION" in codes(result)
    assert result["derived_initial_rate"] is None


def test_out_of_calibration_range_or_negative_concentration_preserves_signal_only():
    for c,code in [(calibration(valid_signal_max=8),"OUTSIDE_CALIBRATION_RANGE"),
                   (calibration(intercept=100),"INVALID_CONVERTED_CONCENTRATION")]:
        result=analyze_initial_rate(observations(),config(),calibration=c)
        assert result["status"]=="ESTIMATED" and code in codes(result)
        assert result["derived_initial_rate"]["product_rate"] is None


def test_missing_requires_explicit_rule_zero_is_not_missing():
    raw=observations(intercept=0)
    raw[1]=replace(raw[1],raw_signal=None)
    failed=analyze_initial_rate(raw,config())
    assert failed["status"]=="NOT_ESTIMABLE" and "MISSING_OBSERVATION" in codes(failed)
    result=analyze_initial_rate(raw,config(missing_policy="exclude"))
    assert result["derived_initial_rate"]["n"]==4
    assert result["derived_initial_rate"]["slope"]==2
    assert result["observation_decisions"][0]["included"]
    assert result["observation_decisions"][1]["reason"]=="MISSING_TIME_OR_SIGNAL"


def test_explicit_window_and_exclusion_records_every_input():
    raw=observations()
    raw[2]=replace(raw[2],raw_signal=999)
    cfg=RateConfig(1,4,"min",exclusions=(("SYN-2","synthetic documented instrument failure"),))
    result=analyze_initial_rate(raw,cfg)
    assert result["derived_initial_rate"]["slope"]==2
    assert len(result["raw_observations"])==len(result["observation_decisions"])==5
    assert result["observation_decisions"][0]["reason"]=="OUTSIDE_EXPLICIT_INTERVAL"
    assert result["observation_decisions"][2]["reason"].startswith("USER_EXCLUSION")
    assert "EARLIER_OBSERVATIONS_EXCLUDED" in codes(result)


@pytest.mark.parametrize("raw,cfg,expected", [
    ([],config(),"NO_OBSERVATIONS"),
    (observations(times=(0,1)),config(),"INSUFFICIENT_TIME_POINTS"),
    (observations(times=(0,0,1,1)),config(),"INSUFFICIENT_TIME_POINTS"),
    (observations(),config(measurement_kind="ENDPOINT"),"NOT_TIME_COURSE"),
    (observations(),RateConfig(4,0,"min"),"INVALID_CONFIGURATION"),
    (observations(),RateConfig(0,4,"s"),"UNIT_MISMATCH"),
    (observations(),config(exclusions=(("absent","why"),)),"UNKNOWN_EXCLUSION"),
])
def test_structured_insufficient_or_invalid_inputs(raw,cfg,expected):
    result=analyze_initial_rate(raw,cfg)
    assert result["status"]=="NOT_ESTIMABLE" and expected in codes(result)


def test_duplicate_ids_rejected_repeated_time_with_distinct_id_retained():
    raw=observations()
    assert "DUPLICATE_OBSERVATION_ID" in codes(analyze_initial_rate(raw+[raw[0]],config()))
    result=analyze_initial_rate(raw+[replace(raw[0],observation_id="SYN-repeat")],config())
    assert result["derived_initial_rate"]["n"]==6
    assert result["derived_initial_rate"]["slope"]==2
    assert "REPEATED_TIME_POINTS" in codes(result)


@pytest.mark.parametrize("changes", [dict(sample_id="OTHER"), dict(batch_id="OTHER"), dict(biological_replicate="BIO-2"),
    dict(technical_replicate="TECH-2"),dict(well_id="A2"),dict(substrate_concentration=2),dict(signal_unit="AU")])
def test_never_pool_distinct_samples_or_replicates(changes):
    raw=observations(); raw[2]=replace(raw[2],**changes)
    assert "MIXED_SERIES" in codes(analyze_initial_rate(raw,config()))


def test_nonlinearity_warns_without_changing_window_or_excluding_points():
    raw=[replace(o,raw_signal=o.time_value**2) for o in observations()]
    result=analyze_initial_rate(raw,config())
    assert result["status"]=="ESTIMATED"
    assert {"LOW_LINEARITY","CURVATURE_SUSPECTED"} <= codes(result)
    assert result["derived_initial_rate"]["n"]==5
    assert result["derived_initial_rate"]["slope"]==4
    assert result["derived_initial_rate"]["residuals"]==[2,-1,-2,-1,2]
    # Analytical x' x = 10, SSE = 14, df = 3.
    assert result["derived_initial_rate"]["slope_standard_error"]==pytest.approx(math.sqrt(14/30))


def test_provenance_and_fingerprint_reproducible_independent_of_calculation_time():
    a=analyze_initial_rate(observations(),config(),calculated_at="2026-11-09T00:00:00+00:00")
    b=analyze_initial_rate(observations(),config(),calculated_at="2026-11-09T00:00:01+00:00")
    assert a["analysis_metadata"]["analysis_fingerprint"]==b["analysis_metadata"]["analysis_fingerprint"]
    assert a["raw_observations"][0]["source_sha256"]==SHA
    assert a["raw_observations"][0]["source_file_id"]=="source-1"
    assert a["derived_initial_rate"]["sample_id"]=="S"
    raw=observations();raw[0]=replace(raw[0],source_sha256="bad")
    assert "INCOMPLETE_PROVENANCE" in codes(analyze_initial_rate(raw,config()))


@pytest.mark.parametrize("value", [float("nan"),float("inf"),True,"bad"])
def test_invalid_numeric_is_never_silently_discarded(value):
    raw=observations();raw[0]=replace(raw[0],raw_signal=value)
    result=analyze_initial_rate(raw,config(missing_policy="exclude"))
    assert result["status"]=="NOT_ESTIMABLE" and "INVALID_NUMERIC_VALUE" in codes(result)


def test_missing_blank_never_defaults_to_zero_and_unused_blank_is_recorded():
    raw=observations()
    result=analyze_initial_rate(raw,config(blank_mode="per_observation"))
    assert result["status"]=="NOT_ESTIMABLE" and "MISSING_OR_INVALID_BLANK" in codes(result)
    blanks=[replace(o,observation_id="B-"+o.observation_id,sample_id="BLANK",raw_signal=0) for o in raw]
    result=analyze_initial_rate(raw,RateConfig(0,3,"min",blank_mode="matched_time"),blanks=blanks)
    assert result["blank_observation_decisions"][-1]==dict(observation_id="B-SYN-4",included=False,reason="NOT_USED_FOR_SELECTED_OBSERVATIONS")


def test_unknown_concentration_unit_and_ambiguous_timestamp_are_not_guessed():
    result=analyze_initial_rate(observations(),config(),calibration=calibration(product_unit="unknown"))
    assert result["status"]=="NOT_ESTIMABLE" and "INVALID_CALIBRATION" in codes(result)
    result=analyze_initial_rate(observations(),config(),calculated_at="2026-11-09T10:00:00")
    assert result["status"]=="NOT_ESTIMABLE" and "INVALID_CONFIGURATION" in codes(result)
