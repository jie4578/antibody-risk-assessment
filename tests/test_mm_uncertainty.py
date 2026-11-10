"""Conditional profile intervals, all fixtures synthetic; no user DB or ML."""
from copy import deepcopy
from dataclasses import replace
import math
import json

import pytest

from protein_engineering.initial_rate import canonical
from protein_engineering.mm_kinetics import fit_michaelis_menten, input_digest
from protein_engineering.mm_uncertainty import UncertaintyReview, analyze_mm_uncertainty
from test_mm_kinetics import records_for, review_for, make_record, S_VALUES, STAMP

FIXED_NOISE = (0.01,-0.03,0.02,-0.04,0.06,-0.02,0.03)


def prepare(records):
    fit_review=review_for(records)
    fitted=fit_michaelis_menten(records,fit_review)
    review=UncertaintyReview("SYNTHETIC statistical reviewer",STAMP,"Conditional synthetic numerical audit",
        "Distinct synthetic measurement errors; not independent biological repeats",input_digest(records),
        fitted["metadata"]["result_sha256"],tuple((r.analysis_id,"UNIT-"+r.analysis_id) for r in records),
        conditional_independence_accepted=True,homoscedastic_normal_errors_accepted=True,
        fixed_calibration_blanks_windows_accepted=True)
    return fit_review,fitted,review


def analyze(records,**kwargs):
    fit_review,fitted,review=prepare(records)
    return analyze_mm_uncertainty(records,fit_review,fitted,review,**kwargs)


def noisy():
    return records_for(noise=FIXED_NOISE)


def independent_limits_and_roots(fitted):
    """Independent physical-unit profile: analytic V(K), log-K nuisance minimizer.

    The reference uses no production profile, t transform, scan or Jacobian.
    """
    from scipy.optimize import brentq,minimize_scalar
    points=fitted["predictions"]
    x=[p["substrate_concentration"] for p in points]
    y=[p["observed_rate"] for p in points]
    n=len(x);sse=fitted["statistics"]["sse"]
    critical=3.841458820694124
    def k_sse(k):
        g=[s/(k+s) for s in x]
        v=sum(a*b for a,b in zip(g,y))/sum(a*a for a in g)
        return sum((b-v*a)**2 for a,b in zip(g,y))
    def v_sse(v):
        fit=minimize_scalar(lambda z:sum((b-v*a/(math.exp(z)+a))**2 for a,b in zip(x,y)),
            bounds=(math.log(.01),math.log(1e5)),method="bounded",options={"xatol":1e-12})
        assert fit.success
        return fit.fun
    out={}
    for name,fun in (("Km",k_sse),("Vmax",v_sse)):
        p=fitted["parameters"][name]
        cutoff=lambda value:n*math.log(fun(value)/sse)-critical
        out[name]=(brentq(cutoff,p/2,p,xtol=1e-11),brentq(cutoff,p,p*2,xtol=1e-11))
    return out,critical


def test_fixed_noise_intervals_match_independent_unknown_variance_profile():
    records=noisy();fr,fitted,review=prepare(records)
    reference,critical=independent_limits_and_roots(fitted)
    result=analyze_mm_uncertainty(records,fr,fitted,review)
    assert result["status"]=="INTERVAL_ESTIMATED"
    assert result["statistical_model"]["variance_mle"]==pytest.approx(fitted["statistics"]["sse"]/7,rel=1e-13)
    assert result["statistical_model"]["critical_value"]==pytest.approx(critical,abs=1e-13)
    assert result["statistical_model"]["sse_ratio_cutoff"]==pytest.approx(math.exp(critical/7),rel=1e-14)
    for name,unit,true_value in (("Km","uM",20),("Vmax","uM/min",5)):
        p=result["parameters"][name]
        assert p["unit"]==unit and p["confidence_level"]==.95
        assert p["lower"]==pytest.approx(reference[name][0],rel=1e-8)
        assert p["upper"]==pytest.approx(reference[name][1],rel=1e-8)
        assert p["lower"]<true_value<p["upper"]
        assert p["point_estimate"]==fitted["parameters"][name]
        for endpoint in ("lower_endpoint","upper_endpoint"):
            assert p["diagnostics"][endpoint]["root_lr"]==pytest.approx(critical,abs=1e-6)
        assert p["profile"] and all(q["optimizer"]["success"] for q in p["profile"])
    assert result["metadata"]["initial_rate_validity"]=="NOT_ESTABLISHED"
    assert result["statistical_model"]["biological_n"]==1


@pytest.mark.parametrize("noise",[None,(1e-13,-1e-13,0,1e-13,0,-1e-13,0)])
def test_zero_near_zero_residuals_refuse_point_intervals(noise):
    result=analyze(records_for(noise=noise))
    assert result["status"]=="NOT_ESTIMABLE"
    assert result["reasons"][0]["code"]=="VARIANCE_DEGENERATE"
    assert all(p["lower"] is None and p["upper"] is None for p in result["parameters"].values())


def test_small_sample_policy_preserves_eligible_c2a_point_estimate():
    records=records_for((2,10,40,160),noise=(.01,-.02,.02,-.01))
    fr,fit,review=prepare(records)
    assert fit["status"]=="FIT_WITH_LIMITATIONS"
    result=analyze_mm_uncertainty(records,fr,fit,review)
    assert result["reasons"][0]["code"]=="INSUFFICIENT_RATE_RECORDS"
    assert result["status"]=="NOT_ESTIMABLE"
    assert result["parameters"]["Km"]["point_estimate"]==fit["parameters"]["Km"]


@pytest.mark.parametrize("substrates",[(.001,.002,.005,.01,.02,.06),(2000,4000,8000,16000,32000,80000)])
def test_low_high_only_c2a_rejection_cannot_be_promoted(substrates):
    records=records_for(substrates)
    fr,fit,review=prepare(records)
    assert fit["status"]=="NOT_ESTIMABLE"
    result=analyze_mm_uncertainty(records,fr,fit,review)
    assert result["status"]=="NOT_ESTIMABLE" and result["parameters"]=={}


def test_high_r_squared_and_strong_correlation_report_weak_identifiability():
    records=records_for((1,2,3,4,5,6,8),noise=(.002,-.006,.004,-.008,.012,-.004,.006))
    result=analyze(records)
    assert result["c2a_result"]["statistics"]["r_squared"]>.99
    assert abs(result["local_diagnostics"]["log_parameter_correlation"])>.98
    assert result["status"]=="WEAKLY_IDENTIFIABLE"
    assert all(p["lower"] is not None and p["upper"] is not None for p in result["parameters"].values())


def unbounded_fixture():
    import numpy as np
    s=np.array([1.,2.,3.,4.,5.,6.,8.]);g=s/(20+s);y=5*g
    # Independent synthetic construction: residual orthogonal to MM tangent and S.
    design=np.column_stack((g,-5*s/(20+s)**2,s))
    raw=np.array([1.,-1.,1.,-1.,1.,-1.,1.])
    residual=raw-design@np.linalg.lstsq(design,raw,rcond=None)[0]
    linear_error=y-s*float(s@y/(s@s))
    required_sse=2*float(linear_error@linear_error)/(math.exp(3.841458820694124/7)-1)
    y=y+residual*math.sqrt(required_sse/float(residual@residual))
    assert np.all(y>0)
    return records_for(tuple(s),rates=tuple(y))


def test_analytic_accepted_tail_proves_no_finite_upper_not_scan_limit():
    records=unbounded_fixture();result=analyze(records)
    assert result["c2a_result"]["status"]=="FIT_WITH_LIMITATIONS"
    assert result["status"]=="NOT_IDENTIFIABLE"
    n=result["statistical_model"]["n"]
    y=[p["observed_rate"] for p in result["c2a_result"]["predictions"]]
    x=[p["substrate_concentration"] for p in result["c2a_result"]["predictions"]]
    beta=sum(a*b for a,b in zip(x,y))/sum(a*a for a in x)
    sse_line=sum((b-beta*a)**2 for a,b in zip(x,y))
    independent_lr=n*math.log(sse_line/result["c2a_result"]["statistics"]["sse"])
    assert independent_lr<result["statistical_model"]["critical_value"]
    for p in result["parameters"].values():
        assert p["upper"] is None and p["status"]=="NOT_IDENTIFIABLE"
        endpoint=p["diagnostics"]["upper_endpoint"]
        assert endpoint["status"]=="OPEN_DOMAIN_LIMIT"
        assert endpoint["domain_limit_lr"]==pytest.approx(independent_lr,rel=1e-9)


def test_short_search_never_fabricates_finite_confidence_endpoints(monkeypatch):
    from protein_engineering.mm_uncertainty import POLICY
    # Inject a deliberately inadequate numerical budget, not a changed LR cutoff.
    monkeypatch.setitem(POLICY,"log_scan_step",1e-6)
    result=analyze(noisy(),scan_steps=1)
    assert result["status"]=="BOUNDARY_LIMITED"
    endpoints=[p["diagnostics"][s] for p in result["parameters"].values() for s in ("lower_endpoint","upper_endpoint")]
    assert any(e["status"]=="NUMERICAL_SEARCH_LIMIT" and e["value_scaled"] is None for e in endpoints)
    assert not any(e["status"]=="OPEN_DOMAIN_LIMIT" for e in endpoints)


@pytest.mark.parametrize("change",["no_independence","normality_unaccepted","shared_unit","missing_unit","no_justification","stale_hash","bad_utc"])
def test_independence_and_error_model_are_never_assumed(change):
    records=noisy();fr,fit,review=prepare(records)
    if change=="no_independence":review=replace(review,conditional_independence_accepted=False)
    elif change=="normality_unaccepted":review=replace(review,homoscedastic_normal_errors_accepted=False)
    elif change=="shared_unit":review=replace(review,independent_units=tuple((r.analysis_id,"SHARED") for r in records))
    elif change=="missing_unit":review=replace(review,independent_units=review.independent_units[:-1])
    elif change=="no_justification":review=replace(review,independence_justification="")
    elif change=="stale_hash":review=replace(review,c2a_result_sha256="0"*64)
    else:review=replace(review,reviewed_at_utc="2026-11-10")
    result=analyze_mm_uncertainty(records,fr,fit,review)
    assert result["status"]=="NOT_ESTIMABLE" and result["parameters"]=={}


@pytest.mark.parametrize("change",["unit","nonfinite","source","configuration","point","initial_validity"])
def test_source_config_units_and_c2a_result_must_replay(change):
    records=noisy();fr,fit,review=prepare(records)
    if change=="unit":records[0]=make_record(0,2,.5,substrate_unit="mM")
    elif change=="nonfinite":fit["predictions"][0]["observed_rate"]=float("nan")
    elif change=="source":records[0].c1_result["raw_observations"][0]["source_sha256"]=""
    elif change=="configuration":fit["metadata"]["configuration"]["loss"]="soft_l1"
    elif change=="point":fit["parameters"]["Km"]=100
    else:fit["metadata"]["initial_rate_validity"]="VALIDATED"
    assert analyze_mm_uncertainty(records,fr,fit,review)["status"]=="NOT_ESTIMABLE"


@pytest.mark.parametrize("level",[0,1,True,float("nan"),float("inf"),None])
def test_invalid_confidence_level_rejected(level):
    assert analyze(noisy(),confidence_level=level)["status"]=="NOT_ESTIMABLE"


@pytest.mark.parametrize("steps",[0,81,True,1.5])
def test_invalid_search_configuration_rejected(steps):
    assert analyze(noisy(),scan_steps=steps)["status"]=="NOT_ESTIMABLE"


@pytest.mark.parametrize("failure",["nuisance_failure","root_failure","false_root","nonfinite_objective"])
def test_numerical_failures_do_not_return_normal_intervals(monkeypatch,failure):
    import scipy.optimize
    from types import SimpleNamespace
    if failure=="nuisance_failure":
        monkeypatch.setattr(scipy.optimize,"minimize_scalar",lambda *a,**k:SimpleNamespace(success=False,message="SYNTHETIC"))
    elif failure=="root_failure":
        def broken(*a,**k):raise RuntimeError("SYNTHETIC root failure")
        monkeypatch.setattr(scipy.optimize,"brentq",broken)
    elif failure=="false_root":
        monkeypatch.setattr(scipy.optimize,"brentq",lambda *a,**k:0.0)
    else:
        monkeypatch.setattr(scipy.optimize,"minimize_scalar",lambda *a,**k:SimpleNamespace(success=True,fun=float("nan"),x=.5,message="SYNTHETIC"))
    result=analyze(noisy())
    assert result["status"]=="NUMERICAL_FAILURE"
    assert result["metadata"]["failure_stage"]=="PROFILE_OPTIMIZATION_OR_ROOT"
    failed=[p for p in result["parameters"].values() if p["status"]=="NUMERICAL_FAILURE"]
    assert failed and all(p["lower"] is None and p["upper"] is None for p in failed)


@pytest.mark.parametrize("confidence_level",[1e-300,1e-20])
def test_unresolvable_confidence_cutoff_never_produces_zero_width_interval(confidence_level):
    result=analyze(noisy(),confidence_level=confidence_level)
    assert result["status"]=="NUMERICAL_FAILURE"
    assert all(p["lower"] is None and p["upper"] is None for p in result["parameters"].values())


def test_parameter_boundary_c2a_output_is_ineligible():
    records=records_for(rates=(1,1,1,1,1,1,1));fr,fit,review=prepare(records)
    assert fit["status"]=="NOT_ESTIMABLE"
    assert any(r["code"]=="PARAMETER_BOUNDARY" for r in fit["reasons"])
    assert analyze_mm_uncertainty(records,fr,fit,review)["parameters"]=={}


def test_unit_rescaling_preserves_profile_criterion_and_parameter_units():
    original=noisy();baseline=analyze(original)
    points=prepare(original)[1]["predictions"]
    converted=[make_record(i,p["substrate_concentration"]/1000,p["observed_rate"],substrate_unit="mM")
        for i,p in enumerate(points)]
    result=analyze(converted)
    assert result["status"]==baseline["status"]
    assert result["parameters"]["Km"]["unit"]=="mM"
    for endpoint in ("point_estimate","lower","upper"):
        assert result["parameters"]["Km"][endpoint]==pytest.approx(baseline["parameters"]["Km"][endpoint]/1000,rel=1e-8)
        assert result["parameters"]["Vmax"][endpoint]==pytest.approx(baseline["parameters"]["Vmax"][endpoint],rel=1e-8)


def test_larger_confidence_level_widens_intervals_with_same_unknown_variance_model():
    a=analyze(noisy(),confidence_level=.90);b=analyze(noisy(),confidence_level=.99)
    for name in ("Km","Vmax"):
        assert b["parameters"][name]["lower"]<a["parameters"][name]["lower"]
        assert b["parameters"][name]["upper"]>a["parameters"][name]["upper"]
    assert a["statistical_model"]["variance_mle"]==b["statistical_model"]["variance_mle"]


def test_repeated_technical_measurements_do_not_supply_biological_independence():
    records=noisy()+[make_record(9,20,2.6,technical="TECH2")]
    fr,fit,review=prepare(records)
    assert fit["status"]=="FIT_WITH_LIMITATIONS"
    units=list(review.independent_units);units[-1]=(records[-1].analysis_id,units[3][1])
    review=replace(review,independent_units=tuple(units),independence_justification="Shared measurement process")
    result=analyze_mm_uncertainty(records,fr,fit,review)
    assert result["status"]=="NOT_ESTIMABLE" and not result["parameters"]


def test_empty_explicit_provenance_rejected_even_if_c2a_replays():
    records=noisy();records[0]=replace(records[0],provenance={})
    fr,fit,review=prepare(records)
    assert fit["status"]=="FIT_WITH_LIMITATIONS"
    result=analyze_mm_uncertainty(records,fr,fit,review)
    assert result["status"]=="NOT_ESTIMABLE"
    assert "source provenance" in result["reasons"][0]["message"]


def test_more_than_twenty_synthetic_rates_still_do_not_claim_exact_coverage():
    substrates=tuple(range(2,163,8))
    noise=tuple((.01,-.03,.02,-.04,.06,-.02,.03)[i%7] for i in range(len(substrates)))
    result=analyze(records_for(substrates,noise=noise))
    assert result["status"]=="INTERVAL_ESTIMATED"
    assert result["statistical_model"]["n"]==21
    assert all("exact" in p["assumptions"][3] for p in result["parameters"].values())


def test_reproducible_readonly_analysis_and_c2a_point_estimate_unchanged():
    records=noisy();fr,fit,review=prepare(records);original=deepcopy((records,fr,fit,review))
    a=analyze_mm_uncertainty(records,fr,fit,review)
    b=analyze_mm_uncertainty(records,fr,fit,review)
    assert canonical(a)==canonical(b)
    assert (records,fr,fit,review)==original
    assert canonical(fit_michaelis_menten(records,fr))==canonical(fit)
    assert a["statistical_model"]["independent_measurement_n"]==7
    assert a["statistical_model"]["biological_n"]==1


def assert_finite_strict_json(result):
    """Independent output check, not the production validation helper."""
    def check(value):
        if isinstance(value,float):
            assert math.isfinite(value)
        elif isinstance(value,dict):
            for item in value.values():check(item)
        elif isinstance(value,(list,tuple)):
            for item in value:check(item)
    check(result)
    json.dumps(result,allow_nan=False,sort_keys=True)


def test_extreme_1e297_profile_overflow_fails_safely_without_input_pollution():
    original_fit=prepare(noisy())[1]
    records=[make_record(i,p["substrate_concentration"]*1e297,p["observed_rate"])
        for i,p in enumerate(original_fit["predictions"])]
    fr,fit,review=prepare(records)
    before=canonical(fit)
    raw_before=[canonical(r.c1_result) for r in records]
    assert fit["status"]=="FIT_WITH_LIMITATIONS"
    result=analyze_mm_uncertainty(records,fr,fit,review)
    assert result["status"]=="NUMERICAL_FAILURE"
    assert result["metadata"]["failure_stage"]=="PHYSICAL_UNIT_RESTORATION"
    assert any(r["code"]=="PHYSICAL_UNIT_RESTORATION_OVERFLOW" for r in result["reasons"])
    assert result["metadata"]["input_sha256"]==input_digest(records)
    assert result["metadata"]["c2a_result_sha256"]==fit["metadata"]["result_sha256"]
    assert_finite_strict_json(result)
    for p in result["parameters"].values():
        assert p["status"]=="NUMERICAL_FAILURE" and p["lower"] is None and p["upper"] is None
        assert p["profile_representation"]=="SCALED_ONLY"
        assert p["profile"] and len(p["profile"])>=161
        assert max(q["log_ratio"] for q in p["profile"])==pytest.approx(80*math.log(2)/2,rel=1e-14)
        assert not any("target_value" in q or "nuisance_value" in q for q in p["profile"])
    assert canonical(fit)==before and [canonical(r.c1_result) for r in records]==raw_before
    assert canonical(fit_michaelis_menten(records,fr))==before
    assert canonical(result)==canonical(analyze_mm_uncertainty(records,fr,fit,review))


def test_ordinary_intervals_preserve_pre_fix_numerical_values_and_strict_json():
    result=analyze(noisy())
    expected={"Km":(20.282195311350875,19.212125268315038,21.411176312254113),
        "Vmax":(5.032750639672563,4.947044772475335,5.120523169542443)}
    assert result["status"]=="INTERVAL_ESTIMATED"
    for name,values in expected.items():
        p=result["parameters"][name]
        assert tuple(p[k] for k in ("point_estimate","lower","upper"))==pytest.approx(values,rel=1e-10)
        assert p["profile_representation"]=="SCALED_AND_PHYSICAL"
    assert_finite_strict_json(result)


def test_accepted_statistical_infinite_tail_is_not_numeric_overflow():
    result=analyze(unbounded_fixture())
    assert result["status"]=="NOT_IDENTIFIABLE"
    assert not any(r["code"]=="PHYSICAL_UNIT_RESTORATION_OVERFLOW" for r in result["reasons"])
    for p in result["parameters"].values():
        assert p["upper"] is None
        assert p["diagnostics"]["upper_endpoint"]["status"]=="OPEN_DOMAIN_LIMIT"
    assert_finite_strict_json(result)


def test_recursive_validation_normalizes_numpy_and_interval_objects():
    import numpy as np
    from dataclasses import dataclass
    from protein_engineering.mm_uncertainty import validate_finite_json
    @dataclass
    class Interval:
        lower:object
        upper:object
    value={"interval":Interval(np.float32(1.25),np.float64(2.5)),
        "diagnostics":[{"n":np.int64(7),"success":np.bool_(True),"values":(np.float64(.5),)}]}
    normalized=validate_finite_json(value)
    assert normalized=={"interval":{"lower":1.25,"upper":2.5},
        "diagnostics":[{"n":7,"success":True,"values":[.5]}]}
    assert type(normalized["diagnostics"][0]["n"]) is int
    assert_finite_strict_json(normalized)


@pytest.mark.parametrize("kind",["python_inf","python_nan","numpy_inf","numpy_nan","numpy_conversion_overflow"])
def test_recursive_validation_rejects_every_nonfinite_scalar(kind):
    import numpy as np
    from protein_engineering.mm_uncertainty import validate_finite_json,ResultIntegrityError
    with np.errstate(over="ignore",invalid="ignore"):
        values={"python_inf":float("inf"),"python_nan":float("nan"),"numpy_inf":np.float32("inf"),
            "numpy_nan":np.float64("nan"),"numpy_conversion_overflow":np.longdouble(str(np.finfo(float).max))*np.longdouble(2)}
    with pytest.raises(ResultIntegrityError) as caught:
        validate_finite_json({"outer":[{"value":values[kind]}]})
    assert caught.value.path=="$.outer[0].value"


@pytest.mark.parametrize("numpy_operands",[False,True])
def test_interval_or_nuisance_restoration_checks_python_and_numpy_products(numpy_operands):
    from protein_engineering.mm_uncertainty import _restore_physical,ResultIntegrityError
    value=scale=1e200
    if numpy_operands:
        import numpy as np
        value,scale=np.float64(value),np.float64(scale)
    with pytest.raises(ResultIntegrityError) as caught:
        _restore_physical(value,scale,"$.parameters.Km.lower")
    assert caught.value.code=="PHYSICAL_UNIT_RESTORATION_OVERFLOW"


def test_final_guard_downgrades_success_with_nonfinite_numpy_diagnostic(monkeypatch):
    import numpy as np
    from protein_engineering.mm_uncertainty import _Profile
    original=_Profile.at
    def injected(profile,log_ratio):
        point=original(profile,log_ratio)
        if log_ratio==0:point["optimizer"]["injected_invalid_diagnostic"]=np.float64("nan")
        return point
    monkeypatch.setattr(_Profile,"at",injected)
    result=analyze(noisy())
    assert result["status"]=="NUMERICAL_FAILURE"
    assert result["metadata"]["failure_stage"]=="FINAL_RESULT_VALIDATION"
    assert result["metadata"]["failure_snapshot_sanitized"] is True
    assert result["metadata"]["failure_snapshot_invalid_values"]
    assert all(p["lower"] is None and p["upper"] is None for p in result["parameters"].values())
    assert_finite_strict_json(result)


def test_ineligible_nonfinite_input_has_explicit_safe_failure_snapshot():
    records=noisy();fr,fit,review=prepare(records)
    fit["predictions"][0]["observed_rate"]=float("nan")
    result=analyze_mm_uncertainty(records,fr,fit,review)
    assert result["status"]=="NOT_ESTIMABLE"
    assert result["metadata"]["failure_snapshot_sanitized"] is True
    assert any("c2a_result.predictions" in item["path"] for item in result["metadata"]["failure_snapshot_invalid_values"])
    assert math.isnan(fit["predictions"][0]["observed_rate"])
    assert_finite_strict_json(result)


def test_positive_physical_parameter_underflow_is_not_zero_estimate():
    from protein_engineering.mm_uncertainty import _restore_physical,ResultIntegrityError
    with pytest.raises(ResultIntegrityError) as caught:
        _restore_physical(1e-200,1e-200,"$.parameters.Km.profile[0].target_value")
    assert caught.value.code=="PHYSICAL_UNIT_RESTORATION_UNDERFLOW"


@pytest.mark.parametrize("value",[None,True])
def test_required_profile_target_cannot_be_null_or_boolean(value):
    from protein_engineering.mm_uncertainty import _restore_physical,ResultIntegrityError
    with pytest.raises(ResultIntegrityError):
        _restore_physical(value,1,"$.parameters.Km.profile[0].target_value")
    assert _restore_physical(None,1,"$.parameters.Km.upper",allow_none=True) is None


def test_final_interval_contract_rejects_missing_finite_bound():
    from protein_engineering.mm_uncertainty import _finalize_result
    result=_finalize_result({"status":"INTERVAL_ESTIMATED","reasons":[],"metadata":{},
        "parameters":{"Km":{"status":"INTERVAL_ESTIMATED","point_estimate":20.,"lower":None,"upper":21.,"reasons":[]}}})
    assert result["status"]=="NUMERICAL_FAILURE"
    assert result["parameters"]["Km"]["upper"] is None
    assert result["reasons"][0]["code"]=="INTERVAL_RESULT_CONTRACT"
    assert_finite_strict_json(result)
