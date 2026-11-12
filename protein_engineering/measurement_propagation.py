"""Synthetic-only joint input-distribution propagation; no files or storage.

This is not a real-data API, a bootstrap, or a frequentist parameter CI.
See PHASE_C2B2A_MC_IMPLEMENTATION.md for the predeclared numerical contract.
"""
from copy import deepcopy
from dataclasses import asdict, dataclass
import hashlib
import json
import math
import platform

from .initial_rate import (
    ANALYSIS_VERSION as C1_VERSION, Calibration, Observation, RateConfig,
    analyze_initial_rate, digest,
)
from .mm_kinetics import (
    ALGORITHM_VERSION as C2A_VERSION, FitReview, RateRecord,
    DIAGNOSTIC_POLICY, NUMERICAL_CONFIG, fit_michaelis_menten, input_digest,
)
from .mm_uncertainty import ResultIntegrityError, validate_finite_json

ALGORITHM_VERSION = "synthetic-joint-mc-1.0.0"
INTEGRITY_VERSION = "synthetic-joint-integrity-1.0.0"
LABELS = ("SIMULATED", "CONDITIONAL_MEASUREMENT_PROPAGATION")
QUANTITIES = ("blank_offset", "blank_drift", "calibration_slope", "calibration_intercept", "stock_delta")
QUANTITY_UNITS = ("RFU", "RFU/min", "RFU/uM", "RFU", "dimensionless")
STAMP = "2026-11-10T00:00:00Z"
PRECISION_POLICY = dict(minimum_draws=1024, mean_mcse_over_sd=0.05,
    covariance_mcse_over_sd_product=0.10, quantile_band_width_over_sd=0.40,
    numerical_resolution_relative=1e-8, quantile_mc_band_probability=0.99,
    probabilities=(0.025, 0.975), quantile_method="linear")
_C2A_CONFIGURATION = json.dumps(NUMERICAL_CONFIG,sort_keys=True,separators=(',',':'))
_C2A_DIAGNOSTICS = json.dumps(DIAGNOSTIC_POLICY,sort_keys=True,separators=(',',':'))
_PRECISION_CONFIGURATION = json.dumps(PRECISION_POLICY,sort_keys=True,separators=(',',':'))
UNCOVERED = (
    "Real experimental initial-rate validity and kinetic-model discrepancy",
    "Unspecified time correlation, time-axis and instrument calibration errors",
    "Raw calibration standards and full preparation/dilution uncertainty",
    "Between-biological-unit and between-batch variation",
    "Frequentist parameter confidence coverage and simultaneous confidence regions",
)


@dataclass(frozen=True)
class CurveContext:
    curve_id: str
    variant_id: str
    sample_id: str
    biological_unit: str
    batch_id: str
    technical_replicate: str
    well_id: str


@dataclass(frozen=True)
class SyntheticExperiment:
    source_id: str
    scope: str
    reference_km: float
    reference_vmax: float
    substrates: tuple
    substrate_scale: float
    times: tuple
    window: tuple
    product_spike: float
    calibration_slope: float
    calibration_intercept: float
    blank_signal: float
    calibration_range: tuple
    substrate_unit: str
    product_unit: str
    time_unit: str
    signal_unit: str
    contexts: tuple


@dataclass(frozen=True)
class SharedGroup:
    group_id: str
    quantities: tuple
    curve_ids: tuple


@dataclass(frozen=True)
class JointErrorModel:
    source_id: str
    distribution: str
    latent_ids: tuple
    loadings: tuple
    covariance: tuple
    supports: tuple
    quantity_units: tuple
    reading_noise_sd: float
    dependence_statement: str
    shared_groups: tuple


@dataclass(frozen=True)
class PropagationConfig:
    draws: int = 1024
    seed: int = 20261111


class PropagationError(ValueError):
    def __init__(self, status, code, stage, message):
        self.status, self.code, self.stage = status, code, stage
        super().__init__(message)

    def record(self):
        return dict(code=self.code, stage=self.stage, message=str(self))


def standard_synthetic_experiment():
    """A declared theoretical fixture, never an acquired measurement."""
    return SyntheticExperiment("SYNTHETIC-MM-20-5", "SYNTHETIC_DEFINITION_ONLY", 20., 5.,
        (2., 5., 10., 20., 40., 80., 160.), 1., (0., .01, .02, .03, .04), (0., .04),
        1., 2., 5., 2., (0., 100.), "uM", "uM", "min", "RFU",
        tuple(CurveContext(f"C{i}", "SYN-V", "SYN-S", "SYN-BIO1", "SYN-BATCH1", "TECH1", f"W{i}")
              for i in range(7)))


def synthetic_error_model(experiment, *, reading_noise_sd, loadings):
    """Explicit synthetic constructor; no missing-value or independence inference.

    Covariance/supports follow the specified independent U(-1,1) latent model.
    Callers may supply JointErrorModel directly; its declarations are verified.
    """
    rows = tuple(tuple(v for v in row) for row in loadings)
    covariance = tuple(tuple(math.fsum(a*b for a,b in zip(left,right))/3 for right in rows) for left in rows)
    supports = tuple((-math.fsum(abs(v) for v in row), math.fsum(abs(v) for v in row)) for row in rows)
    ids = tuple(c.curve_id for c in experiment.contexts)
    return JointErrorModel("SYNTHETIC-EXPLICIT-JOINT-MODEL", "INDEPENDENT_UNIFORM_MINUS_ONE_ONE",
        tuple(f"U{i+1}" for i in range(len(rows[0]))), rows, covariance, supports, QUANTITY_UNITS,
        reading_noise_sd, "Independent bounded synthetic latents; all dependence is specified by loadings. "
        "Independent per-reading U(-sqrt(3)*SD,+sqrt(3)*SD); no residual noise added.",
        (SharedGroup("SYN-BLANK", QUANTITIES[:2], ids),
         SharedGroup("SYN-CALIBRATION", QUANTITIES[2:4], ids),
         SharedGroup("SYN-STOCK", QUANTITIES[4:], ids)))


def _error(status, code, message, stage="INPUT_VALIDATION"):
    raise PropagationError(status, code, stage, message)


def _encoded(value):
    """Strict canonical snapshot; strings held privately are not caller aliases."""
    return json.dumps(validate_finite_json(value),ensure_ascii=False,sort_keys=True,
        separators=(',',':'),allow_nan=False)


def _snapshot(value):
    # Detachment preserves declared latent/quantity insertion order; hashing is canonical separately.
    return json.dumps(validate_finite_json(value),ensure_ascii=False,separators=(',',':'),allow_nan=False)


def _sha(text):
    return hashlib.sha256(text.encode('utf-8')).hexdigest()


def _fields(value, required, stage):
    if not isinstance(value,dict):
        _error("NUMERICAL_FAILURE","INTERNAL_RESULT_FIELD_TYPE","Expected a result object",stage)
    for name,kind in required.items():
        if name not in value:
            _error("NUMERICAL_FAILURE","REQUIRED_FIELD_MISSING",name,stage)
        if not isinstance(value[name],kind):
            _error("NUMERICAL_FAILURE","INTERNAL_RESULT_FIELD_TYPE",name,stage)


def _hash_field(value, key, stage):
    _fields(value,{key:str},stage)
    text=value[key]
    if len(text)!=64 or any(c not in '0123456789abcdef' for c in text):
        _error("NUMERICAL_FAILURE","INTEGRITY_MISMATCH_HASH_FORMAT",key,stage)


def _same(actual, expected, code, stage):
    if _encoded(actual)!=_encoded(expected):
        _error("NUMERICAL_FAILURE",code,"Content does not match the trusted current input/configuration",stage)


def _c1_response(value, trusted_payload):
    stage="C1_RESULT_VALIDATION"
    out=json.loads(_snapshot(value))
    _fields(out,dict(status=str,analysis_metadata=dict,raw_observations=list,
        blank_observations=list,reasons=list,quality_control=list),stage)
    meta=out['analysis_metadata']
    _fields(meta,dict(analysis_version=str,configuration=dict,calibration=dict,
        calculated_at_utc=str,initial_rate_validity=str),stage)
    for name in ('input_sha256','analysis_fingerprint'):_hash_field(meta,name,stage)
    expected=json.loads(trusted_payload)
    payload=dict(raw_observations=out['raw_observations'],blank_observations=out['blank_observations'],
        configuration=meta['configuration'],calibration=meta['calibration'])
    _same(payload,expected,"INTEGRITY_MISMATCH_C1_INPUT",stage)
    if meta['input_sha256']!=_sha(trusted_payload):
        _error("NUMERICAL_FAILURE","INTEGRITY_MISMATCH_C1_INPUT","Incorrect C.1 input digest",stage)
    check=deepcopy(out)
    check['analysis_metadata'].pop('analysis_fingerprint')
    check['analysis_metadata'].pop('calculated_at_utc')
    if meta['analysis_fingerprint']!=_sha(_encoded(check)):
        _error("NUMERICAL_FAILURE","INTEGRITY_MISMATCH_C1_RESULT","Incorrect C.1 result fingerprint",stage)
    if meta['analysis_version']!=C1_VERSION or meta['initial_rate_validity']!='NOT_ESTABLISHED' or meta['calculated_at_utc']!=STAMP:
        _error("NUMERICAL_FAILURE","INTEGRITY_MISMATCH_C1_CONFIGURATION","Version/validity/time changed",stage)
    if out['status'] not in {'ESTIMATED','NOT_ESTIMABLE'}:
        _error("NUMERICAL_FAILURE","INTERNAL_RESULT_VALUE","Unknown C.1 status",stage)
    if out['status']=='ESTIMATED':
        _fields(out,{'derived_initial_rate':dict},stage)
        _fields(out['derived_initial_rate'],{'product_rate':(dict,type(None)),'included_observation_ids':list},stage)
    return out


def _c2a_response(value, trusted_context):
    stage="C2A_RESULT_VALIDATION"
    out=json.loads(_snapshot(value));expected=json.loads(trusted_context)
    _fields(out,dict(status=str,metadata=dict,input_records=list,review=dict,
        predictions=list,reasons=list,quality_control=list),stage)
    meta=out['metadata']
    for name in ('input_sha256','result_sha256'):_hash_field(meta,name,stage)
    _same(out['input_records'],expected['records'],"INTEGRITY_MISMATCH_C2A_INPUT",stage)
    _same(out['review'],expected['review'],"INTEGRITY_MISMATCH_C2A_REVIEW",stage)
    if meta['input_sha256']!=expected['input_sha256']:
        _error("NUMERICAL_FAILURE","INTEGRITY_MISMATCH_C2A_INPUT","Incorrect C.2A input digest",stage)
    for name,wanted in dict(algorithm_version=C2A_VERSION,configuration=json.loads(_C2A_CONFIGURATION),
            diagnostic_policy=json.loads(_C2A_DIAGNOSTICS),initial_rate_validity='NOT_ESTABLISHED',
            weighting='UNWEIGHTED_EACH_RECORD',parameter_intervals='NOT_CALCULATED',experimental_validation='NOT_ESTABLISHED').items():
        if name not in meta:_error("NUMERICAL_FAILURE","REQUIRED_FIELD_MISSING",name,stage)
        _same(meta[name],wanted,"INTEGRITY_MISMATCH_C2A_CONFIGURATION",stage)
    check=deepcopy(out);check['metadata'].pop('result_sha256')
    if meta['result_sha256']!=_sha(_encoded(check)):
        _error("NUMERICAL_FAILURE","INTEGRITY_MISMATCH_C2A_RESULT","Incorrect C.2A result fingerprint",stage)
    if out['status'] not in {'FIT_WITH_LIMITATIONS','NOT_ESTIMABLE'}:
        _error("NUMERICAL_FAILURE","INTERNAL_RESULT_VALUE","Unknown C.2A status",stage)
    if out['status']=='FIT_WITH_LIMITATIONS':
        _fields(out,{'parameters':dict},stage)
        p=out['parameters']
        _fields(p,dict(Km=(int,float),Vmax=(int,float),Km_unit=str,Vmax_unit=str),stage)
        if any(isinstance(p[k],bool) or p[k]<=0 for k in ('Km','Vmax')) or (p['Km_unit'],p['Vmax_unit'])!=('uM','uM/min'):
            _error("NUMERICAL_FAILURE","INTEGRITY_MISMATCH_C2A_UNITS_OR_PARAMETERS","Invalid point estimate/units",stage)
        ids=[r['analysis_id'] for r in expected['records']]
        if any(not isinstance(r,dict) or not isinstance(r.get('analysis_id'),str) for r in out['predictions']):
            _error("NUMERICAL_FAILURE","INTEGRITY_MISMATCH_C2A_IDENTITIES","Prediction/draw identity mismatch",stage)
        if sorted(r['analysis_id'] for r in out['predictions'])!=sorted(ids):
            _error("NUMERICAL_FAILURE","INTEGRITY_MISMATCH_C2A_IDENTITIES","Prediction/draw identity mismatch",stage)
        _fields(out,dict(statistics=dict,optimizer=dict),stage)
        _fields(out['statistics'],dict(n=int),stage)
        _same(out['statistics']['n'],len(ids),'INTEGRITY_MISMATCH_C2A_COUNT',stage)
        if out['optimizer'].get('success') is not True:
            _error('NUMERICAL_FAILURE','INTEGRITY_MISMATCH_C2A_OPTIMIZER_STATUS','Successful point estimate requires a converged optimizer',stage)
        observations={r['analysis_id']:r['c1_result']['derived_initial_rate'] for r in expected['records']}
        for prediction in out['predictions']:
            _fields(prediction,dict(observed_rate=(int,float),substrate_concentration=(int,float)),stage)
            observed=observations[prediction['analysis_id']]
            _same(prediction['observed_rate'],observed['product_rate']['slope'],'INTEGRITY_MISMATCH_C2A_OBSERVATIONS',stage)
            _same(prediction['substrate_concentration'],observed['substrate_concentration'],'INTEGRITY_MISMATCH_C2A_OBSERVATIONS',stage)
    return out


def _summary_context(values,names,units):
    return _encoded(dict(values=values,order=list(names),units=list(units),policy=json.loads(_PRECISION_CONFIGURATION)))


def _summary_response(value, trusted_context, stage):
    out=json.loads(_snapshot(value));context=json.loads(trusted_context)
    _fields(out,dict(order=list,units=list,n=int,mean=list,standard_deviation=list,
        covariance=list,covariance_mcse=list,marginal_intervals=dict,precision=dict),stage)
    for name in ('input_sha256','analysis_fingerprint'):_hash_field(out,name,stage)
    if out['input_sha256']!=_sha(trusted_context):
        _error("NUMERICAL_FAILURE","INTEGRITY_MISMATCH_SUMMARY_INPUT","Summary input changed",stage)
    check=deepcopy(out);check.pop('analysis_fingerprint')
    if out['analysis_fingerprint']!=_sha(_encoded(check)):
        _error("NUMERICAL_FAILURE","INTEGRITY_MISMATCH_SUMMARY_RESULT","Summary content changed",stage)
    _same(out['order'],context['order'],"INTEGRITY_MISMATCH_SUMMARY_IDENTITIES",stage)
    _same(out['units'],context['units'],"INTEGRITY_MISMATCH_SUMMARY_UNITS",stage)
    if out['n']!=len(context['values']):
        _error("NUMERICAL_FAILURE","INTEGRITY_MISMATCH_SUMMARY_COUNT","Incorrect summary count",stage)
    _same(out['precision'].get('policy'),context['policy'],"INTEGRITY_MISMATCH_PRECISION_CONFIGURATION",stage)
    return out


def _draw_failure(index, fixture_sha, model_sha, error):
    return dict(draw_id=f'DRAW-{index:05d}',labels=list(LABELS),status='NUMERICAL_FAILURE',
        failure=error,parameters=None,rates=[],c1_links=[],fixture_sha256=fixture_sha,model_sha256=model_sha)


def _check_draws(result, seals, phase):
    """Compare mutable responses to private pre-return snapshots, not self hashes.

    Only an explicit downgrade to a failed audit record changes a seal. Changed
    success data is never adopted as a new trusted baseline.
    """
    current=result.get('draws');rendered=[];ok=True
    for index,anchor in enumerate(seals):
        trusted=json.loads(anchor)
        try:
            actual=_snapshot(current[index]) if isinstance(current,list) and index<len(current) else None
        except (ValueError,TypeError,OverflowError):actual=None
        if actual!=anchor:
            ok=False
            old_parameters=trusted.get('parameters')
            trusted.update(status='NUMERICAL_FAILURE',parameters=None,
                failure=dict(code='INTEGRITY_MISMATCH_DRAW',stage=phase,
                    message='Draw content changed after validation',draw_id=trusted['draw_id']),
                integrity_audit=dict(trusted_snapshot_sha256=_sha(anchor),
                    observed_snapshot_sha256=_sha(actual) if actual is not None else None,
                    original_parameters=old_parameters))
            seals[index]=_snapshot(trusted)  # A failed transition, never success rebaselining.
        rendered.append(trusted)
    if not isinstance(current,list) or len(current)!=len(seals):
        ok=False
        result['analysis_failures'].append(dict(code='INTEGRITY_MISMATCH_DRAW_COLLECTION',stage=phase,
            message='Returned draw collection differs from actual executions'))
    result['draws']=rendered
    if not ok:result.update(status='NUMERICAL_FAILURE',parameter_summary=None,rate_summary=None)
    return ok


def _set_counts(result, requested, seals):
    failed=sum(json.loads(s)['failure'] is not None for s in seals)
    result.update(requested_draws=requested,executed_draws=len(seals),successful_draws=len(seals)-failed,
        failed_draws=failed,unexecuted_draws=requested-len(seals) if requested is not None else None)


def _finite_scalar(value, name, *, positive=False, nonnegative=False):
    if isinstance(value, bool) or not isinstance(value, (int, float)) or not math.isfinite(value):
        _error("NOT_ESTIMABLE", "FINITE_NUMBER_REQUIRED", name)
    if (positive and value <= 0) or (nonnegative and value < 0):
        _error("NOT_ESTIMABLE", "INVALID_PHYSICAL_INPUT", name)


def _physical_product(a, b, stage):
    value = float(a)*float(b)
    if not math.isfinite(value):
        _error("NUMERICAL_FAILURE", "PHYSICAL_UNIT_RESTORATION_OVERFLOW", "Required physical quantity overflows", stage)
    if a != 0 and b != 0 and value == 0:
        _error("NUMERICAL_FAILURE", "PHYSICAL_UNIT_RESTORATION_UNDERFLOW", "Required physical quantity underflows", stage)
    return value


def _covariance_checks(load, cov, np):
    """Validate in per-quantity units, never hide a negative variance in a floor."""
    if bool(np.any(np.diag(cov)<0)):
        _error("NOT_ESTIMABLE","NEGATIVE_VARIANCE","Diagonal variances must be nonnegative","INPUT_COVARIANCE")
    scales=np.max(np.abs(load),axis=1)
    normalized_load=np.zeros_like(load)
    normalized_cov=np.zeros_like(cov)
    for i in range(5):
        if scales[i]==0:
            if bool(np.any(cov[i,:]!=0)) or bool(np.any(cov[:,i]!=0)):
                _error("NOT_ESTIMABLE","COVARIANCE_LOADING_MISMATCH","Zero loading requires an exactly zero covariance row/column","INPUT_COVARIANCE")
        else:
            normalized_load[i]=load[i]/scales[i]
    for i in range(5):
        for j in range(5):
            if cov[i,j]==0 or scales[i]==0 or scales[j]==0:
                continue
            # frexp avoids forming scales[i]*scales[j], which can overflow/underflow.
            value,exponent=math.frexp(float(cov[i,j]))
            left,le=math.frexp(float(scales[i]));right,re=math.frexp(float(scales[j]))
            try:normalized_cov[i,j]=math.ldexp(value/(left*right),exponent-le-re)
            except OverflowError:
                _error("NOT_ESTIMABLE","COVARIANCE_LOADING_MISMATCH","Covariance has incompatible quantity scales","INPUT_COVARIANCE")
    expected=normalized_load @ normalized_load.T/3
    if not np.allclose(normalized_cov,normalized_cov.T,rtol=1e-12,atol=1e-12):
        _error("NOT_ESTIMABLE","INVALID_COVARIANCE","Covariance is not symmetric","INPUT_COVARIANCE")
    if float(np.linalg.eigvalsh(normalized_cov).min()) < -1e-12*max(1.,float(np.abs(normalized_cov).max())):
        _error("NOT_ESTIMABLE","INVALID_COVARIANCE","Covariance is not PSD; no jitter/projection applied","INPUT_COVARIANCE")
    if not np.allclose(normalized_cov,expected,rtol=1e-12,atol=1e-12):
        _error("NOT_ESTIMABLE","COVARIANCE_LOADING_MISMATCH","Declared covariance must equal L L^T/3 in the declared units","INPUT_COVARIANCE")


def _validate(experiment, model, config, np):
    if not isinstance(experiment, SyntheticExperiment) or experiment.scope != "SYNTHETIC_DEFINITION_ONLY":
        _error("NOT_ESTIMABLE", "SYNTHETIC_DEFINITION_REQUIRED", "No raw-data, rate-record or file input is supported")
    if not isinstance(model, JointErrorModel):
        _error("MISSING_UNCERTAINTY_INPUTS", "EXPLICIT_JOINT_MODEL_REQUIRED", "Unknown errors are not zero or independent")
    if not isinstance(config,PropagationConfig):
        _error("NOT_ESTIMABLE","INPUT_FIELD_TYPE","PropagationConfig required")
    if not isinstance(experiment.contexts,(tuple,list)) or any(not isinstance(c,CurveContext) for c in experiment.contexts):
        _error("NOT_ESTIMABLE","INPUT_FIELD_TYPE","CurveContext records required")
    for name in ('substrates','times','window','calibration_range'):
        if not isinstance(getattr(experiment,name),(tuple,list)):
            _error('NOT_ESTIMABLE','INPUT_FIELD_TYPE',name)
    for name,value in (('experiment.source_id',experiment.source_id),('model.source_id',model.source_id)):
        if value is None or value=='':
            _error("MISSING_UNCERTAINTY_INPUTS","SOURCE_ID_REQUIRED",name)
        if not isinstance(value,str):
            _error("NOT_ESTIMABLE","INPUT_FIELD_TYPE",name)
    required=("loadings","covariance","supports","quantity_units","reading_noise_sd",
        "latent_ids","dependence_statement","distribution")
    missing=[name for name in required if getattr(model,name) is None]
    if missing:
        _error("MISSING_UNCERTAINTY_INPUTS","JOINT_MODEL_FIELDS_REQUIRED",",".join(missing))
    if model.shared_groups is None:
        _error("UNSUPPORTED_DEPENDENCE","SHARED_MAPPING_REQUIRED","Shared relationships are unknown, not independent")
    if not isinstance(model.dependence_statement,str):
        _error("NOT_ESTIMABLE","INPUT_FIELD_TYPE","dependence_statement must be text")
    if not isinstance(model.latent_ids,(tuple,list)) or any(not isinstance(x,str) or not x for x in model.latent_ids):
        _error('NOT_ESTIMABLE','INPUT_FIELD_TYPE','latent_ids must contain text identifiers')
    for name,width in (('loadings',len(model.latent_ids)),('covariance',5),('supports',2)):
        rows=getattr(model,name)
        if not isinstance(rows,(tuple,list)):
            _error('NOT_ESTIMABLE','INPUT_FIELD_TYPE',name)
        if not rows:
            _error('MISSING_UNCERTAINTY_INPUTS','JOINT_MODEL_SHAPE',name)
        if len(rows)!=5 or any(not isinstance(row,(tuple,list)) or len(row)!=width for row in rows):
            _error('NOT_ESTIMABLE','JOINT_MODEL_SHAPE',name)
    # Validate the entire supplied tree, including fields not used in arithmetic.
    validate_finite_json((experiment, model, config))
    if not isinstance(config, PropagationConfig) or type(config.draws) is not int or not 1 <= config.draws <= 16384:
        _error("NOT_ESTIMABLE", "INVALID_DRAW_BUDGET", "draws must be an integer in 1..16384")
    if type(config.seed) is not int or not 0 <= config.seed < 2**64:
        _error("NOT_ESTIMABLE", "INVALID_SEED", "seed must be an unsigned 64-bit integer")
    if not experiment.source_id or not model.source_id:
        _error("MISSING_UNCERTAINTY_INPUTS", "SOURCE_ID_REQUIRED", "Synthetic definition and model IDs required")
    if (experiment.substrate_unit, experiment.product_unit, experiment.time_unit, experiment.signal_unit) != ("uM", "uM", "min", "RFU"):
        _error("NOT_ESTIMABLE", "UNSUPPORTED_UNITS", "First synthetic model uses explicit uM, min, RFU only; no conversion")
    if not experiment.substrates or len(experiment.substrates) != len(experiment.contexts) or len(set(experiment.substrates)) < 4:
        _error("NOT_ESTIMABLE", "INSUFFICIENT_CONCENTRATIONS", "Four distinct positive substrate levels and all curve contexts required")
    for name in ("reference_km", "reference_vmax", "substrate_scale", "calibration_slope"):
        _finite_scalar(getattr(experiment, name), name, positive=True)
    _finite_scalar(experiment.product_spike, "product_spike", nonnegative=True)
    for name in ("calibration_intercept", "blank_signal"):
        _finite_scalar(getattr(experiment, name), name)
    for s in experiment.substrates:
        _finite_scalar(s, "substrate", positive=True)
        _physical_product(s, experiment.substrate_scale, "INPUT_PHYSICAL_SCALING")
    for t in experiment.times:
        _finite_scalar(t, "time", nonnegative=True)
    if len(experiment.times) < 3 or tuple(sorted(set(experiment.times))) != experiment.times:
        _error("NOT_ESTIMABLE", "FIXED_TIMES_REQUIRED", "At least three strictly increasing fixed times required")
    if experiment.window != (experiment.times[0], experiment.times[-1]):
        _error("NOT_ESTIMABLE", "FIXED_FULL_WINDOW_REQUIRED", "No automatic member/window selection")
    if len(experiment.calibration_range) != 2 or experiment.calibration_range[0] >= experiment.calibration_range[1]:
        _error("NOT_ESTIMABLE", "INVALID_CALIBRATION_DOMAIN", "Increasing finite calibration bounds required")
    ids = tuple(c.curve_id for c in experiment.contexts)
    if len(set(ids)) != len(ids) or any(not isinstance(c, CurveContext) or
            any(not isinstance(v,str) or not v.strip() for v in asdict(c).values()) for c in experiment.contexts):
        _error("NOT_ESTIMABLE", "CURVE_IDENTITIES_REQUIRED", "Every synthetic curve needs complete unique identity")
    contexts = {(c.variant_id,c.sample_id,c.biological_unit,c.batch_id) for c in experiment.contexts}
    if len(contexts) != 1:
        _error("UNSUPPORTED_DEPENDENCE", "MULTIPLE_CONTEXTS_UNSUPPORTED", "Single variant/sample/biological unit/batch only")
    if len({c.well_id for c in experiment.contexts}) != len(ids):
        _error("UNSUPPORTED_DEPENDENCE", "DUPLICATE_WELL_CONTEXT", "Declare separate fixed reaction curves; no implicit pooling")
    if (model.distribution != "INDEPENDENT_UNIFORM_MINUS_ONE_ONE" or not model.dependence_statement.strip()
            or not model.latent_ids or len(set(model.latent_ids)) != len(model.latent_ids)
            or any(not isinstance(v,str) or not v.strip() for v in model.latent_ids)):
        _error("MISSING_UNCERTAINTY_INPUTS", "LATENT_DISTRIBUTION_REQUIRED", "Explicit independent uniform latent model and rationale required")
    if model.quantity_units != QUANTITY_UNITS:
        _error("NOT_ESTIMABLE", "MODEL_UNIT_MISMATCH", "Covariance and loadings must follow declared quantity order/units")
    _finite_scalar(model.reading_noise_sd, "reading_noise_sd", nonnegative=True)
    _physical_product(math.sqrt(3),model.reading_noise_sd,"INPUT_SUPPORT_REPRESENTATION")
    for collection in (model.loadings, model.covariance, model.supports):
        for row in collection:
            for value in row:
                _finite_scalar(value,"joint model numeric entry")
    load = np.asarray(model.loadings,dtype=float)
    cov = np.asarray(model.covariance,dtype=float)
    support = np.asarray(model.supports,dtype=float)
    if load.shape != (5,len(model.latent_ids)) or cov.shape != (5,5) or support.shape != (5,2):
        _error("MISSING_UNCERTAINTY_INPUTS", "JOINT_MODEL_SHAPE", "Full loadings, covariance and support declarations required")
    _covariance_checks(load,cov,np)
    with np.errstate(over="raise", invalid="raise"):
        limits = np.sum(np.abs(load),axis=1)
    expected_support=np.column_stack((-limits,limits))
    same_support=np.equal(support,expected_support)
    nonzero=expected_support!=0
    same_support[nonzero]=np.abs(support[nonzero]/expected_support[nonzero]-1)<=1e-12
    if not bool(np.all(same_support)):
        _error("NOT_ESTIMABLE", "SUPPORT_LOADING_MISMATCH", "Support must follow the actual bounded latent model")
    if experiment.calibration_slope <= limits[2] or limits[4] >= 1:
        _error("NOT_ESTIMABLE", "NONPOSITIVE_SUPPORT", "All supported calibration slopes and stock multipliers must be positive")
    seen, group_ids = [], set()
    for group in model.shared_groups:
        if (not isinstance(group,SharedGroup) or not group.group_id or group.group_id in group_ids
                or len(group.curve_ids) != len(ids) or set(group.curve_ids) != set(ids) or not group.quantities):
            _error("UNSUPPORTED_DEPENDENCE", "SHARED_MAPPING_REQUIRED", "First model supports explicit all-curve shared groups only")
        group_ids.add(group.group_id)
        seen.extend(group.quantities)
    if sorted(seen) != sorted(QUANTITIES):
        _error("UNSUPPORTED_DEPENDENCE", "SHARED_MAPPING_REQUIRED", "Each quantity must have exactly one shared mapping")
    return load


def _conditions():
    return dict(protocol_id="SYNTHETIC-MC", protocol_version=ALGORITHM_VERSION,
        temperature_c=25., pH=7., buffer_composition="SYNTHETIC BUFFER",
        substrate_name="SYNTHETIC SUBSTRATE", substrate_lot="SYNTHETIC STOCK",
        cofactor_name="NONE", cofactor_concentration=0., cofactor_concentration_unit="dimensionless",
        enzyme_concentration=.01, enzyme_concentration_unit="uM", reaction_volume=100.,
        reaction_volume_unit="uL", readout_method="SYNTHETIC FLUORESCENCE")


def _one_draw(experiment, model, rng, load, index, model_sha, fixture_sha, np, seals=None):
    ident = f"DRAW-{index:05d}"
    draw = dict(draw_id=ident, labels=list(LABELS),
        status="NOT_ESTIMABLE", failure=None, parameters=None, rates=[], c1_links=[],
        fixture_sha256=fixture_sha, model_sha256=model_sha)
    records = []
    stage='DRAW_SAMPLING'
    try:
        latent = rng.uniform(-1.,1.,len(model.latent_ids))
        reading_latent = rng.uniform(-1.,1.,(len(experiment.substrates),len(experiment.times)))
        with np.errstate(over="raise", invalid="raise"):
            effects = load @ latent
            noise = reading_latent * (math.sqrt(3)*model.reading_noise_sd)
        k = experiment.calibration_slope + float(effects[2])
        b = experiment.calibration_intercept + float(effects[3])
        stock = 1.+float(effects[4])
        draw.update(validate_finite_json(dict(latent_values=dict(zip(model.latent_ids,latent.tolist())),
            shared_effects=dict(zip(QUANTITIES,effects.tolist())),reading_perturbations=noise.tolist(),
            sampled_calibration=dict(slope=k,intercept=b),stock_multiplier=stock)))
        cal_payload = dict(draw_id=ident,k=k,b=b,domain=experiment.calibration_range,labels=LABELS)
        cal_sha = digest(cal_payload)
        calibration = Calibration("SIMULATED-CAL-"+ident,"SIMULATED-CAL-SOURCE-"+ident,cal_sha,
            "RFU","uM",k,b,*experiment.calibration_range,"per_observation")
        for j,(s,context) in enumerate(zip(experiment.substrates,experiment.contexts)):
            stage='RAW_SIGNAL_CONSTRUCTION'
            # Only nominal, unperturbed S/k generate the underlying theoretical raw signal.
            norm = max(s,experiment.reference_km)
            v = experiment.reference_vmax * ((s/norm)/(experiment.reference_km/norm+s/norm))
            raw = [experiment.blank_signal+experiment.calibration_intercept+
                   experiment.calibration_slope*(experiment.product_spike+v*t)+float(e)
                   for t,e in zip(experiment.times,noise[j])]
            blank = [experiment.blank_signal+float(effects[0])+float(effects[1])*t for t in experiment.times]
            substrate = _physical_product(_physical_product(s,experiment.substrate_scale,"SUBSTRATE_SCALING"),stock,"SUBSTRATE_SCALING")
            payload = validate_finite_json(dict(labels=LABELS,draw_id=ident,curve=asdict(context),
                times=experiment.times,raw=raw,blank=blank,substrate=substrate,model_sha256=model_sha))
            source_sha = digest(payload)
            observations = [Observation(f"{ident}-{context.curve_id}-T{i}",context.batch_id,context.sample_id,t,r,
                "min","RFU","SIMULATED-SOURCE-"+ident+"-"+context.curve_id,source_sha,
                context.biological_unit,context.technical_replicate,substrate,"uM",context.well_id,z)
                for i,(t,r,z) in enumerate(zip(experiment.times,raw,blank))]
            configuration=RateConfig(*experiment.window,"min",blank_mode="per_observation")
            trusted_payload=_encoded(dict(raw_observations=[asdict(o) for o in observations],
                blank_observations=[],configuration=asdict(configuration),calibration=asdict(calibration)))
            stage='INITIAL_RATE'
            response=analyze_initial_rate(deepcopy(observations),deepcopy(configuration),
                calibration=deepcopy(calibration),calculated_at=STAMP)
            stage='C1_RESULT_VALIDATION'
            c1=_c1_response(response,trusted_payload)
            derived = c1.get("derived_initial_rate")
            if c1["status"] != "ESTIMATED" or not derived or not derived["product_rate"]:
                draw["c1_failure"] = dict(curve_id=context.curve_id,
                    input_sha256=c1["analysis_metadata"]["input_sha256"],
                    fingerprint=c1["analysis_metadata"]["analysis_fingerprint"],
                    simulated_source_sha256=source_sha,simulated_calibration_sha256=cal_sha,
                    reasons=c1["reasons"],quality_control=c1["quality_control"])
                reason = [x["code"] for x in c1["reasons"]+c1["quality_control"]]
                _error("NOT_ESTIMABLE","C1_INELIGIBLE",context.curve_id+": "+",".join(reason),"INITIAL_RATE")
            draw["rates"].append(derived["product_rate"]["slope"])
            draw["c1_links"].append(dict(analysis_id=f"{ident}-{context.curve_id}",
                input_sha256=c1["analysis_metadata"]["input_sha256"],
                fingerprint=c1["analysis_metadata"]["analysis_fingerprint"],
                included_observation_ids=derived["included_observation_ids"],
                simulated_source_sha256=source_sha,simulated_calibration_sha256=cal_sha,
                quality_control=c1["quality_control"]))
            records.append(RateRecord(f"{ident}-{context.curve_id}",context.variant_id,_conditions(),c1,
                dict(labels=LABELS,fixture_sha256=fixture_sha,model_sha256=model_sha,
                     simulated_source_sha256=source_sha,simulated_calibration_sha256=cal_sha)))
        review = FitReview("SYNTHETIC CONDITIONAL ENGINE",STAMP,
            "Synthetic numerical propagation only; does not establish experimental initial rates",
            input_digest(records),acknowledge_not_established=True)
        trusted_records=[asdict(r) for r in records]
        expected_digest=_sha(_encoded(sorted(trusted_records,key=lambda r:r['analysis_id'])))
        if review.input_sha256!=expected_digest:
            _error('NUMERICAL_FAILURE','INTEGRITY_MISMATCH_C2A_REVIEW','Generated review does not bind current records','MM_FITTING')
        trusted_context=_encoded(dict(records=trusted_records,review=asdict(review),input_sha256=expected_digest))
        stage='MM_FITTING'
        response=fit_michaelis_menten(deepcopy(records),deepcopy(review))
        stage='C2A_RESULT_VALIDATION'
        fit=_c2a_response(response,trusted_context)
        draw["c2a_input_sha256"] = fit["metadata"]["input_sha256"]
        draw["c2a_result_sha256"] = fit["metadata"]["result_sha256"]
        draw["quality_control"] = fit["quality_control"]
        draw["quality_control_scope"] = "INNER_DETERMINISTIC_C2A_ONLY"
        if fit["status"] != "FIT_WITH_LIMITATIONS" or fit["parameters"] is None:
            codes = [x["code"] for x in fit["reasons"]]
            draw["c2a_failure_reasons"] = fit["reasons"]
            _error("NUMERICAL_FAILURE" if "NUMERICAL_FAILURE" in codes else "NOT_ESTIMABLE",
                "C2A_FIT_REJECTED","; ".join(x["code"]+": "+x["message"] for x in fit["reasons"]),"MM_FITTING")
        draw.update(status="FIT_WITH_LIMITATIONS",parameters=fit["parameters"])
    except PropagationError as exc:
        draw.update(status=exc.status,failure=exc.record(),parameters=None)
    except ResultIntegrityError as exc:
        issue=exc.issue();issue['stage']=stage
        draw.update(status='NUMERICAL_FAILURE',failure=issue,parameters=None)
    except (KeyError,IndexError,AttributeError,TypeError) as exc:
        draw.update(status='NUMERICAL_FAILURE',failure=dict(stage=stage,code='INTERNAL_RESULT_STRUCTURE',message=str(exc)),parameters=None)
    except (ValueError,ArithmeticError,RuntimeError) as exc:
        draw.update(status="NUMERICAL_FAILURE",failure=dict(stage=stage,code="DRAW_NUMERICAL_FAILURE",message=str(exc)),parameters=None)
    safe=validate_finite_json(draw)
    if seals is not None:seals.append(_snapshot(safe))
    return safe


def _summary(values, names, units, np):
    from scipy.stats import binom
    x = np.asarray(values,dtype=float)
    n,d = x.shape
    if n < 2:
        _error("NOT_ESTIMABLE","INSUFFICIENT_DRAWS_FOR_SUMMARY","At least two draws required","SUMMARY")
    scale = np.maximum(np.max(np.abs(x),axis=0),np.finfo(float).tiny)
    with np.errstate(over="raise",invalid="raise",divide="raise"):
        z = x/scale
        mean = z.mean(axis=0)
        centered = z-mean
        cov = centered.T @ centered/(n-1)
        sd = np.sqrt(np.diag(cov))
        products = centered[:,:,None]*centered[:,None,:]
        cov_mcse = products.std(axis=0,ddof=1)/math.sqrt(n)*(n/(n-1))
        q = np.quantile(z,PRECISION_POLICY["probabilities"],axis=0,method="linear")
    physical = lambda v,i: _physical_product(float(v),float(scale[i]),"SUMMARY_UNIT_RESTORATION")
    physical_cov = lambda v,i,j: _physical_product(physical(v,i),float(scale[j]),"COVARIANCE_UNIT_RESTORATION")
    output = dict(order=list(names),units=list(units),n=n,
        mean=[physical(mean[i],i) for i in range(d)],
        mean_mcse=[physical(sd[i]/math.sqrt(n),i) for i in range(d)],
        standard_deviation=[physical(sd[i],i) for i in range(d)],
        covariance=[[physical_cov(cov[i,j],i,j) for j in range(d)] for i in range(d)],
        covariance_mcse=[[physical_cov(cov_mcse[i,j],i,j) for j in range(d)] for i in range(d)],
        covariance_units=[[units[i]+" * "+units[j] for j in range(d)] for i in range(d)],
        covariance_ddof=1,covariance_mcse_method="EMPIRICAL_CENTERED_PRODUCT_APPROXIMATION",
        marginal_intervals={},precision=dict(status="TARGET_MET",policy=PRECISION_POLICY,components={}),
        interpretation="Marginal input-distribution propagation quantiles; NOT frequentist parameter confidence intervals or a joint region")
    constant = sd <= PRECISION_POLICY["numerical_resolution_relative"]*np.maximum(np.abs(mean),1e-300)
    ordered = np.sort(z,axis=0)
    for i,name in enumerate(names):
        bands=[]
        component_ok=True
        for p in PRECISION_POLICY["probabilities"]:
            lo=int(binom.ppf(.005,n,p))
            hi=int(binom.ppf(.995,n,p))+1
            lower=physical(ordered[lo-1,i],i) if lo>=1 else None
            upper=physical(ordered[hi-1,i],i) if hi<=n else None
            resolved=lower is not None and upper is not None
            width=(ordered[hi-1,i]-ordered[lo-1,i])/sd[i] if resolved and not constant[i] else None
            component_ok &= resolved and (bool(constant[i]) or width <= PRECISION_POLICY["quantile_band_width_over_sd"])
            bands.append(dict(probability=p,mc_probability=.99,lower=lower,upper=upper,
                lower_rank=lo,upper_rank=hi,status="RESOLVED" if resolved else "ORDER_STATISTIC_BOUND_NOT_RESOLVED",
                width_over_sd=float(width) if width is not None else None))
        output["marginal_intervals"][name] = dict(lower=physical(q[0,i],i),upper=physical(q[1,i],i),
            probabilities=[.025,.975],unit=units[i],method="LINEAR_EMPIRICAL_QUANTILES",mc_precision_bands=bands)
        output["precision"]["components"][name] = "BELOW_NUMERICAL_RESOLUTION" if constant[i] else ("TARGET_MET" if component_ok else "TARGET_NOT_MET")
        if not constant[i] and (not component_ok or 1/math.sqrt(n)>PRECISION_POLICY["mean_mcse_over_sd"]):
            output["precision"]["status"]="TARGET_NOT_MET"
    for i in range(d):
        for j in range(d):
            if not constant[i] and not constant[j] and cov_mcse[i,j]/(sd[i]*sd[j])>PRECISION_POLICY["covariance_mcse_over_sd_product"]:
                output["precision"]["status"]="TARGET_NOT_MET"
    if n < PRECISION_POLICY["minimum_draws"]:
        output["precision"]["status"]="INSUFFICIENT_DRAWS"
    output['input_sha256']=_sha(_summary_context(values,names,units))
    output['analysis_fingerprint']=_sha(_encoded(output))
    return validate_finite_json(output)


def _consume_summary(values,names,units,np,stage):
    trusted=_summary_context(values,names,units)
    supplied=json.loads(trusted)['values']
    response=_summary(supplied,names,units,np)
    _same(supplied,json.loads(trusted)['values'],'INTEGRITY_MISMATCH_SUMMARY_INPUT',stage)
    return _summary_response(response,trusted,stage)


def _finish_response(result,requested,seals,summary_seals):
    _check_draws(result,seals,'FINAL_RESULT_VALIDATION')
    _set_counts(result,requested,seals)
    _fields(result,dict(labels=list,status=str,metadata=dict,draws=list,analysis_failures=list), 'FINAL_RESULT_VALIDATION')
    _fields(result['metadata'],dict(algorithm_version=str,integrity_version=str,c1_version=str,c2a_version=str), 'FINAL_RESULT_VALIDATION')
    for name,wanted in dict(algorithm_version=ALGORITHM_VERSION,integrity_version=INTEGRITY_VERSION,
            c1_version=C1_VERSION,c2a_version=C2A_VERSION).items():
        if result['metadata'][name]!=wanted:
            _error('NUMERICAL_FAILURE','INTEGRITY_MISMATCH_RESPONSE_VERSION',name,'FINAL_RESULT_VALIDATION')
    if result['failed_draws']:
        result.update(status='NUMERICAL_FAILURE' if any(d['status']=='NUMERICAL_FAILURE' for d in result['draws']) else 'NOT_ESTIMABLE',
            parameter_summary=None,rate_summary=None)
    for key,anchor in summary_seals.items():
        if result[key] is not None and _encoded(result[key])!=anchor:
            result.update(status='NUMERICAL_FAILURE',parameter_summary=None,rate_summary=None)
            result['analysis_failures'].append(dict(code='INTEGRITY_MISMATCH_SUMMARY_RESULT',stage='FINAL_RESULT_VALIDATION',message='Summary changed after validation'))
    try:
        result=json.loads(_snapshot(result))
    except ResultIntegrityError as exc:
        safe,omitted={},[]
        for key in ('metadata','synthetic_definition','joint_error_model','source_ledger','analysis_failures'):
            if key not in result:continue
            try:safe[key]=json.loads(_encoded(result[key]))
            except ResultIntegrityError as bad:omitted.append(dict(field=key,issue=bad.issue()))
        result=dict(labels=list(LABELS),metadata=dict(algorithm_version=ALGORITHM_VERSION,integrity_version=INTEGRITY_VERSION),
            draws=[json.loads(s) for s in seals],analysis_failures=[])
        result.update(safe)
        result.update(status='NUMERICAL_FAILURE',parameter_summary=None,rate_summary=None)
        result['analysis_failures'].append(exc.issue())
        result['metadata'].update(failure_stage='FINAL_RESULT_VALIDATION',quarantined_fields=omitted)
        _set_counts(result,requested,seals)
    result['nonfinite_output_count']=0
    result['strict_json_serialization']='PASS'
    result['mc_precision_state']=result['parameter_summary']['precision']['status'] if result['parameter_summary'] else 'NOT_CALCULATED'
    return validate_finite_json(result)


def propagate_synthetic_measurements(experiment, model, config=PropagationConfig()):
    """Pure-memory propagation with trusted per-call snapshots and fail-closed IO.

    Hashes bind current content and configuration, not malicious replacement of
    an entire process or a source lacking an external authenticity anchor.
    """
    requested=config.draws if isinstance(config,PropagationConfig) and type(config.draws) is int and config.draws>=0 else None
    seals=[];summary_seals={};stage='INPUT_VALIDATION';fixture_sha=None;model_sha=None
    result=dict(labels=list(LABELS),status='NOT_ESTIMABLE',draws=[],analysis_failures=[],
        requested_draws=requested,executed_draws=0,successful_draws=0,failed_draws=0,unexecuted_draws=requested,
        parameter_summary=None,rate_summary=None,
        metadata=dict(algorithm_version=ALGORITHM_VERSION,integrity_version=INTEGRITY_VERSION,
            c1_version=C1_VERSION,c2a_version=C2A_VERSION,initial_rate_validity='NOT_ESTABLISHED',
            method='JOINT_INPUT_DISTRIBUTION_MONTE_CARLO',rng='NumPy Generator(PCG64)',seed=None,
            failure_policy='ANY_FAILED_DRAW_BLOCKS_ALL_SUMMARIES_NO_REDRAW',
            precision_policy=json.loads(_PRECISION_CONFIGURATION),uncovered_error_sources=list(UNCOVERED),
            data_readiness='SYNTHETIC_ONLY_REAL_DATA_NOT_ENABLED',
            no_double_counting='RAW_INPUT_LAYER_ONLY_NO_SE_OR_PROFILE_OR_RESIDUAL_ADDITION'))
    try:
        import numpy as np
        import scipy
        experiment,model,config=deepcopy((experiment,model,config))
        load=_validate(experiment,model,config,np)
        _same(PRECISION_POLICY,json.loads(_PRECISION_CONFIGURATION),'INTEGRITY_MISMATCH_PRECISION_CONFIGURATION',stage)
        result['metadata'].update(seed=config.seed,dependencies=dict(numpy=np.__version__,scipy=scipy.__version__,python=platform.python_version()),
            biological_units=1,experimental_batches=1,technical_curve_count=len(experiment.contexts),draws_are_not_experiments=True)
        result['synthetic_definition']=json.loads(_encoded(experiment))
        result['joint_error_model']=json.loads(_encoded(model))
        fixture_sha=_sha(_encoded(result['synthetic_definition']));model_sha=_sha(_encoded(result['joint_error_model']))
        result['metadata'].update(fixture_sha256=fixture_sha,model_sha256=model_sha,configuration_sha256=_sha(_encoded(asdict(config))))
        result['source_ledger']=[dict(quantity=name,unit=unit,source_id=model.source_id,source_sha256=model_sha,
            support=model.supports[i],layer='SHARED_INPUT_QUANTITY',loading=model.loadings[i],
            state='FIXED_BY_SYNTHETIC_DESIGN' if all(v==0 for v in model.loadings[i]) else 'PROPAGATED_ONCE',
            group_id=next(g.group_id for g in model.shared_groups if name in g.quantities))
            for i,(name,unit) in enumerate(zip(QUANTITIES,QUANTITY_UNITS))]
        result['source_ledger'].append(dict(quantity='independent_reading',unit='RFU',source_id=model.source_id,source_sha256=model_sha,
            layer='RAW_SIGNAL_ONLY',sd=model.reading_noise_sd,support=[-math.sqrt(3)*model.reading_noise_sd,math.sqrt(3)*model.reading_noise_sd],
            state='FIXED_BY_SYNTHETIC_DESIGN' if model.reading_noise_sd==0 else 'PROPAGATED_ONCE'))
        rng=np.random.Generator(np.random.PCG64(config.seed))
        for index in range(config.draws):
            stage='DRAW_EXECUTION'
            try:
                draw=_one_draw(experiment,model,rng,load,index,model_sha,fixture_sha,np,seals=seals)
                if len(seals)!=index+1:
                    _error('NUMERICAL_FAILURE','INTERNAL_DRAW_SNAPSHOT_MISSING','Draw did not create a trusted audit snapshot',stage)
            except Exception as exc:
                issue=exc.record() if isinstance(exc,PropagationError) else dict(code='INTERNAL_DRAW_FAILURE',stage=stage,message=str(exc),exception_type=type(exc).__name__)
                draw=json.loads(seals[index]) if len(seals)>index else _draw_failure(index,fixture_sha,model_sha,issue)
                draw.update(status='NUMERICAL_FAILURE',failure=issue,parameters=None)
                if len(seals)>index:seals[index]=_snapshot(draw)
                else:seals.append(_snapshot(draw))
            result['draws'].append(draw)
        _check_draws(result,seals,'PRE_SUMMARY_INTEGRITY')
        _set_counts(result,requested,seals)
        if not result['failed_draws'] and not result['analysis_failures']:
            stage='PARAMETER_SUMMARY'
            values=[[d['parameters']['Km'],d['parameters']['Vmax']] for d in result['draws']]
            parameters=_consume_summary(values,('Km','Vmax'),('uM','uM/min'),np,stage)
            stage='RATE_SUMMARY'
            rates=_consume_summary([d['rates'] for d in result['draws']],tuple(c.curve_id for c in experiment.contexts),
                ('uM/min',)*len(experiment.contexts),np,stage)
            if _check_draws(result,seals,'POST_SUMMARY_INTEGRITY'):
                result.update(status='SUFFICIENT_FOR_SELECTED_MODEL',parameter_summary=parameters,rate_summary=rates)
                summary_seals=dict(parameter_summary=_encoded(parameters),rate_summary=_encoded(rates))
    except PropagationError as exc:
        result.update(status=exc.status,parameter_summary=None,rate_summary=None)
        result['analysis_failures'].append(exc.record())
    except ResultIntegrityError as exc:
        issue=exc.issue();issue['stage']=stage
        result.update(status='NUMERICAL_FAILURE',parameter_summary=None,rate_summary=None)
        result['analysis_failures'].append(issue)
    except Exception as exc:
        result.update(status='NUMERICAL_FAILURE',parameter_summary=None,rate_summary=None)
        result['analysis_failures'].append(dict(code='INPUT_FIELD_TYPE' if stage=='INPUT_VALIDATION' and isinstance(exc,(TypeError,AttributeError,KeyError)) else 'INTERNAL_ANALYSIS_FAILURE',
            stage=stage,message=str(exc),exception_type=type(exc).__name__))
    try:
        return _finish_response(result,requested,seals,summary_seals)
    except Exception as exc:
        # Last response boundary retains the private execution ledger. Never
        # report an exception during presentation as zero executed draws.
        if isinstance(exc,PropagationError):issue=exc.record()
        elif isinstance(exc,ResultIntegrityError):issue=exc.issue();issue['stage']='FINAL_RESULT_VALIDATION'
        else:issue=dict(code='INTERNAL_RESPONSE_FAILURE',stage='FINAL_RESULT_VALIDATION',message=str(exc),exception_type=type(exc).__name__)
        emergency=dict(labels=list(LABELS),status='NUMERICAL_FAILURE',draws=[json.loads(s) for s in seals],
            parameter_summary=None,rate_summary=None,analysis_failures=[issue],
            metadata=dict(algorithm_version=ALGORITHM_VERSION,integrity_version=INTEGRITY_VERSION,
                fixture_sha256=fixture_sha,model_sha256=model_sha,initial_rate_validity='NOT_ESTABLISHED'),
            nonfinite_output_count=0,strict_json_serialization='PASS',mc_precision_state='NOT_CALCULATED')
        _set_counts(emergency,requested,seals)
        return validate_finite_json(emergency)
