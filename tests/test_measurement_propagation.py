"""Synthetic-only joint-measurement propagation; independent analytic checks."""
from copy import deepcopy
from dataclasses import asdict,replace
import hashlib
import json
import math

import numpy as np
import pytest

from protein_engineering import measurement_propagation as mc
from protein_engineering.mm_uncertainty import validate_finite_json


def model_for(experiment, *, sd=0., blank=0., drift=0., slope=0., intercept=0., stock=0., correlation=0.):
    # Explicit fixture construction, never missing experimental error => zero.
    load=np.zeros((5,5))
    load[0,0]=blank
    load[1,1]=drift
    load[2,2]=slope
    load[3,2]=intercept*correlation
    load[3,3]=intercept*math.sqrt(1-correlation**2)
    load[4,4]=stock
    return mc.synthetic_error_model(experiment,reading_noise_sd=sd,loadings=load.tolist())


def run(experiment=None, model=None, *, draws=8):
    experiment=experiment or mc.standard_synthetic_experiment()
    return mc.propagate_synthetic_measurements(experiment,model or model_for(experiment),mc.PropagationConfig(draws=draws))


def estimated(result):
    assert result['status']=='SUFFICIENT_FOR_SELECTED_MODEL', result['analysis_failures'] or result['draws'][:1]
    assert result['failed_draws']==0
    assert result['nonfinite_output_count']==0
    json.dumps(result,allow_nan=False)
    return result


@pytest.fixture(scope='module')
def reading_ensemble():
    exp=mc.standard_synthetic_experiment()
    return estimated(run(exp,model_for(exp,sd=.001),draws=1024))


@pytest.fixture(scope='module')
def drift_ensemble():
    exp=mc.standard_synthetic_experiment()
    return estimated(run(exp,model_for(exp,drift=.01),draws=1024))


@pytest.fixture(scope='module')
def mixed_ensemble():
    exp=mc.standard_synthetic_experiment()
    return estimated(run(exp,model_for(exp,sd=.001,blank=.01,drift=.01,slope=.04,intercept=.05,stock=.02,correlation=.8),draws=1024))


def test_no_error_parameter_recovery_units_and_not_established():
    result=estimated(run())
    for draw in result['draws']:
        assert draw['parameters']['Km']==pytest.approx(20,rel=1e-7,abs=1e-8)
        assert draw['parameters']['Vmax']==pytest.approx(5,rel=1e-7,abs=1e-8)
        assert (draw['parameters']['Km_unit'],draw['parameters']['Vmax_unit'])==('uM','uM/min')
        assert len(draw['c1_links'])==7
        assert all(len(link['included_observation_ids'])==5 for link in draw['c1_links'])
        assert all(len(link['simulated_source_sha256'])==64 for link in draw['c1_links'])
    assert result['metadata']['initial_rate_validity']=='NOT_ESTABLISHED'
    assert result['parameter_summary']['covariance'][0][0]==0
    assert result['parameter_summary']['precision']['status']=='INSUFFICIENT_DRAWS'
    assert all(x['state']=='FIXED_BY_SYNTHETIC_DESIGN' for x in result['source_ledger'])


def test_independent_signal_noise_variance_from_ols_weights(reading_ensemble):
    rates=np.asarray([d['rates'] for d in reading_ensemble['draws']])
    theoretical=np.array([5*s/(20+s) for s in [2,5,10,20,40,80,160]])
    # w=(-20,-10,0,10,20), sum(w^2)=1000; k0=2.
    variance=.001**2*1000/4
    mean=rates.mean(axis=0)
    cov=np.cov(rates,rowvar=False,ddof=1)
    products=(rates-mean)[:,:,None]*(rates-mean)[:,None,:]
    se=products.std(axis=0,ddof=1)/math.sqrt(len(rates))*len(rates)/(len(rates)-1)
    assert np.all(abs(mean-theoretical)<=5*rates.std(axis=0,ddof=1)/math.sqrt(len(rates))+1e-10)
    assert np.all(abs(cov-np.eye(7)*variance)<=5*se+1e-10)
    assert np.allclose(reading_ensemble['rate_summary']['covariance'],cov,rtol=1e-12,atol=1e-15)


def test_constant_shared_blank_cancels_without_extra_se_noise():
    exp=mc.standard_synthetic_experiment()
    result=estimated(run(exp,model_for(exp,blank=.1),draws=32))
    expected=[5*s/(20+s) for s in exp.substrates]
    for draw in result['draws']:
        assert draw['rates']==pytest.approx(expected,rel=1e-7,abs=1e-8)
        assert draw['parameters']['Km']==pytest.approx(20,rel=1e-7,abs=1e-8)
        assert draw['parameters']['Vmax']==pytest.approx(5,rel=1e-7,abs=1e-8)


def test_shared_blank_drift_keeps_cross_curve_covariance(drift_ensemble):
    rates=np.asarray([d['rates'] for d in drift_ensemble['draws']])
    expected=np.array([5*s/(20+s) for s in [2,5,10,20,40,80,160]])
    for row,draw in zip(rates,drift_ensemble['draws']):
        assert row==pytest.approx(expected-draw['shared_effects']['blank_drift']/2,rel=1e-7,abs=1e-8)
    centered=rates-rates.mean(axis=0)
    products=centered[:,:,None]*centered[:,None,:]
    se=products.std(axis=0,ddof=1)/math.sqrt(len(rates))*len(rates)/(len(rates)-1)
    theoretical=.01**2/3/4
    assert np.all(abs(np.cov(rates,rowvar=False,ddof=1)-theoretical)<=5*se+1e-10)
    assert np.allclose(np.corrcoef(rates,rowvar=False),1,atol=1e-12)


def test_shared_calibration_slope_scales_vmax_only():
    exp=mc.standard_synthetic_experiment()
    result=estimated(run(exp,model_for(exp,slope=.04),draws=64))
    for draw in result['draws']:
        k=draw['sampled_calibration']['slope']
        assert draw['parameters']['Km']==pytest.approx(20,rel=1e-7,abs=1e-8)
        assert draw['parameters']['Vmax']==pytest.approx(10/k,rel=1e-7,abs=1e-8)
    # Independent exact uniform reciprocal moment, not the kernel's summaries.
    lo,hi=1.96,2.04
    expected_mean=10*math.log(hi/lo)/(hi-lo)
    samples=np.array([d['parameters']['Vmax'] for d in result['draws']])
    assert abs(samples.mean()-expected_mean)<=5*samples.std(ddof=1)/math.sqrt(64)+1e-10


def test_shared_stock_scales_km_only():
    exp=mc.standard_synthetic_experiment()
    result=estimated(run(exp,model_for(exp,stock=.02),draws=32))
    for draw in result['draws']:
        assert draw['parameters']['Km']==pytest.approx(20*draw['stock_multiplier'],rel=1e-7,abs=1e-8)
        assert draw['parameters']['Vmax']==pytest.approx(5,rel=1e-7,abs=1e-8)


def test_correlated_k_b_and_complete_shared_ledger(mixed_ensemble):
    pairs=[]
    for draw in mixed_ensemble['draws']:
        u=draw['latent_values']
        assert draw['shared_effects']['calibration_slope']==pytest.approx(.04*u['U3'],abs=1e-15)
        assert draw['shared_effects']['calibration_intercept']==pytest.approx(.05*(.8*u['U3']+.6*u['U4']),abs=1e-15)
        pairs.append([draw['shared_effects']['calibration_slope'],draw['shared_effects']['calibration_intercept']])
    x=np.asarray(pairs)
    cross=(x[:,0]-x[:,0].mean())*(x[:,1]-x[:,1].mean())
    mcse=cross.std(ddof=1)/math.sqrt(len(x))*len(x)/(len(x)-1)
    assert abs(np.cov(x,rowvar=False,ddof=1)[0,1]-.04*.05*.8/3)<=5*mcse+1e-10
    assert len(mixed_ensemble['source_ledger'])==6
    assert 'NO_SE_OR_PROFILE_OR_RESIDUAL' in mixed_ensemble['metadata']['no_double_counting']
    assert mixed_ensemble['joint_error_model']['shared_groups'][1]['curve_ids']==[f'C{i}' for i in range(7)]


@pytest.mark.parametrize('rho',[-1.,1.])
def test_legal_rank_deficient_latent_model(rho):
    exp=mc.standard_synthetic_experiment()
    model=model_for(exp,slope=.04,intercept=.05,correlation=rho)
    assert np.linalg.matrix_rank(np.asarray(model.covariance))==1
    result=estimated(run(exp,model,draws=16))
    for draw in result['draws']:
        effects=draw['shared_effects']
        assert effects['calibration_intercept']==pytest.approx(rho*.05/.04*effects['calibration_slope'],abs=1e-15)


@pytest.mark.parametrize('mode',['negative','not_psd','mismatch','tiny_mismatch','support','units','mapping','duplicate_mapping'])
def test_invalid_covariance_or_dependence_is_rejected_without_draws(mode):
    exp=mc.standard_synthetic_experiment()
    model=model_for(exp,slope=.04,intercept=.05,correlation=.8)
    if mode in {'negative','not_psd','mismatch','tiny_mismatch'}:
        cov=np.array(model.covariance)
        if mode=='negative':cov[0,0]=-1
        if mode=='not_psd':cov[0,1]=cov[1,0]=1
        if mode=='mismatch':cov[2,2]*=2
        if mode=='tiny_mismatch':cov[0,0]=1e-20
        model=replace(model,covariance=tuple(map(tuple,cov)))
    elif mode=='support':model=replace(model,supports=((0.,0.),)*5)
    elif mode=='units':model=replace(model,quantity_units=('unknown',)*5)
    elif mode=='mapping':model=replace(model,shared_groups=(replace(model.shared_groups[0],curve_ids=('C0',)),*model.shared_groups[1:]))
    else:model=replace(model,shared_groups=(*model.shared_groups,model.shared_groups[0]))
    result=mc.propagate_synthetic_measurements(exp,model,mc.PropagationConfig(draws=4))
    assert result['status'] in {'NOT_ESTIMABLE','UNSUPPORTED_DEPENDENCE'}
    assert result['executed_draws']==0 and result['parameter_summary'] is None
    json.dumps(result,allow_nan=False)


@pytest.mark.parametrize('mode',['none','covariance','independence','latent_distribution'])
def test_missing_error_model_information_never_implies_zero(mode):
    exp=mc.standard_synthetic_experiment()
    model=model_for(exp)
    if mode=='none':model=None
    if mode=='covariance':model=replace(model,covariance=())
    if mode=='independence':model=replace(model,dependence_statement='')
    if mode=='latent_distribution':model=replace(model,distribution='UNKNOWN')
    result=mc.propagate_synthetic_measurements(exp,model)
    assert result['status']=='MISSING_UNCERTAINTY_INPUTS'
    assert result['executed_draws']==0


@pytest.mark.parametrize('field',['biological_unit','batch_id','variant_id','sample_id'])
def test_multiple_context_scope_rejected(field):
    exp=mc.standard_synthetic_experiment()
    exp=replace(exp,contexts=(replace(exp.contexts[0],**{field:'OTHER'}),*exp.contexts[1:]))
    result=run(exp)
    assert result['status']=='UNSUPPORTED_DEPENDENCE'
    assert result['analysis_failures'][0]['code']=='MULTIPLE_CONTEXTS_UNSUPPORTED'


def test_mixed_failed_draws_suppress_all_normal_intervals_and_no_redraw():
    exp=replace(mc.standard_synthetic_experiment(),calibration_range=(0.,7.4))
    result=run(exp,model_for(exp,sd=.05),draws=32)
    assert result['status']=='NOT_ESTIMABLE'
    assert 0<result['failed_draws']<32
    assert result['executed_draws']==result['requested_draws']==32
    assert len({d['draw_id'] for d in result['draws']})==32
    assert result['parameter_summary'] is None and result['rate_summary'] is None
    stages=set()
    for draw in result['draws']:
        if draw['failure']:
            stages.add(draw['failure']['stage'])
            if draw['failure']['stage']=='INITIAL_RATE':
                assert 'OUTSIDE_CALIBRATION_RANGE' in draw['failure']['message']
                assert len(draw['c1_failure']['input_sha256'])==64
                assert len(draw['c1_failure']['simulated_source_sha256'])==64
            else:
                # Same original high-noise fixture can produce negative rates.
                assert draw['failure']['stage']=='MM_FITTING'
                assert draw['failure']['code']=='C2A_FIT_REJECTED'
                assert any('Negative substrate or product rate' in x['message'] for x in draw['c2a_failure_reasons'])
            assert draw['parameters'] is None
    assert stages=={'INITIAL_RATE','MM_FITTING'}


def test_negative_converted_concentration_is_not_clipped_or_redrawn():
    exp=replace(mc.standard_synthetic_experiment(),product_spike=0.)
    result=run(exp,model_for(exp,sd=.01),draws=8)
    assert result['failed_draws']>0 and result['parameter_summary'] is None
    assert any('INVALID_CONVERTED_CONCENTRATION' in d['failure']['message'] for d in result['draws'] if d['failure'])


def test_extreme_scale_safe_failure_and_finite_json():
    exp=replace(mc.standard_synthetic_experiment(),substrate_scale=1e297)
    result=run(exp,model_for(exp,stock=.02),draws=8)
    assert result['status']=='NUMERICAL_FAILURE'
    assert result['failed_draws']==0  # Failure restoring ensemble covariance, not fitting draws.
    assert result['analysis_failures'][0]['code']=='PHYSICAL_UNIT_RESTORATION_OVERFLOW'
    assert result['parameter_summary'] is None
    assert all(math.isfinite(d['parameters']['Km']) for d in result['draws'])
    assert result['nonfinite_output_count']==0
    validate_finite_json(result)
    json.dumps(result,allow_nan=False)


@pytest.mark.parametrize('value',[float('nan'),float('inf'),-float('inf')])
def test_nonfinite_input_returns_safe_explicit_failure(value):
    exp=mc.standard_synthetic_experiment()
    result=mc.propagate_synthetic_measurements(exp,replace(model_for(exp),reading_noise_sd=value))
    assert result['status']=='NUMERICAL_FAILURE'
    assert result['executed_draws']==0 and result['parameter_summary'] is None
    assert result['strict_json_serialization']=='PASS'
    json.dumps(result,allow_nan=False)


@pytest.mark.parametrize('mode',['optimizer_failure','nonfinite_result'])
def test_fit_failure_cannot_leave_successful_parameters(monkeypatch,mode):
    original=mc.fit_michaelis_menten
    def rejected(*args):
        out=original(*args)
        if mode=='optimizer_failure':
            out.update(status='NOT_ESTIMABLE',parameters=None,reasons=[dict(code='NUMERICAL_FAILURE',message='synthetic injected optimizer failure')])
        else:out['parameters']['Km']=float('inf')
        return out
    monkeypatch.setattr(mc,'fit_michaelis_menten',rejected)
    result=run(draws=3)
    assert result['status']=='NUMERICAL_FAILURE'
    assert result['failed_draws']==result['executed_draws']==3
    assert result['parameter_summary'] is None
    assert all(d['parameters'] is None for d in result['draws'])
    json.dumps(result,allow_nan=False)


def test_seed_prefix_joint_pairing_and_input_immutability(mixed_ensemble):
    exp=mc.standard_synthetic_experiment()
    model=model_for(exp,sd=.001,blank=.01,drift=.01,slope=.04,intercept=.05,stock=.02,correlation=.8)
    before=deepcopy((exp,model))
    a=estimated(run(exp,model,draws=4))
    b=estimated(run(exp,model,draws=4))
    assert a==b and (exp,model)==before
    assert a['draws']==mixed_ensemble['draws'][:4]
    pairs=np.asarray([[d['parameters']['Km'],d['parameters']['Vmax']] for d in mixed_ensemble['draws']])
    assert np.allclose(mixed_ensemble['parameter_summary']['covariance'],np.cov(pairs,rowvar=False,ddof=1),rtol=1e-10,atol=1e-14)
    assert mixed_ensemble['parameter_summary']['covariance_units'][0][1]=='uM * uM/min'


def test_precision_order_statistics_match_independent_binomial_ranks(mixed_ensemble):
    from scipy.stats import binom
    summary=mixed_ensemble['parameter_summary']
    assert summary['n']==1024
    assert summary['precision']['status'] in {'TARGET_MET','TARGET_NOT_MET'}
    for i,name in enumerate(['Km','Vmax']):
        samples=np.sort([d['parameters'][name] for d in mixed_ensemble['draws']])
        interval=summary['marginal_intervals'][name]
        assert [interval['lower'],interval['upper']]==pytest.approx(np.quantile(samples,[.025,.975]),rel=1e-12)
        for band in interval['mc_precision_bands']:
            p=band['probability']
            lo=int(binom.ppf(.005,1024,p));hi=int(binom.ppf(.995,1024,p))+1
            assert (band['lower_rank'],band['upper_rank'])==(lo,hi)
            assert (band['lower'],band['upper'])==pytest.approx((samples[lo-1],samples[hi-1]),rel=1e-12)


def test_mixed_parameters_against_independent_profiled_scalar_reference(mixed_ensemble):
    from scipy.optimize import minimize_scalar
    for draw in mixed_ensemble['draws'][:4]:
        s=np.array([2,5,10,20,40,80,160])*draw['stock_multiplier']
        y=np.array(draw['rates'])
        def profiled(log_k):
            g=s/(math.exp(log_k)+s)
            v=float(g@y/(g@g))
            return float(np.sum((y-v*g)**2)),v
        ref=minimize_scalar(lambda p:profiled(p)[0],bounds=(math.log(5),math.log(80)),
            method='bounded',options={'xatol':1e-12})
        assert ref.success
        assert draw['parameters']['Km']==pytest.approx(math.exp(ref.x),rel=2e-6,abs=1e-7)
        assert draw['parameters']['Vmax']==pytest.approx(profiled(ref.x)[1],rel=2e-6,abs=1e-7)


def test_explicit_technical_replicate_not_merged_or_promoted_to_biological_n():
    exp=mc.standard_synthetic_experiment()
    extra=replace(exp.contexts[0],curve_id='C7',well_id='W7',technical_replicate='TECH2')
    exp=replace(exp,substrates=(*exp.substrates,2.),contexts=(*exp.contexts,extra))
    result=estimated(run(exp,model_for(exp,sd=.001),draws=4))
    assert len(result['draws'][0]['rates'])==8
    assert len(result['draws'][0]['c1_links'])==8
    assert result['metadata']['initial_rate_validity']=='NOT_ESTABLISHED'


@pytest.mark.parametrize('change',[dict(time_unit='s'),dict(substrate_unit='mM'),dict(window=(0.,.03))])
def test_units_and_fixed_window_cannot_be_silently_changed(change):
    exp=replace(mc.standard_synthetic_experiment(),**change)
    result=run(exp)
    assert result['status']=='NOT_ESTIMABLE' and result['executed_draws']==0


def test_no_file_database_network_or_training_interfaces_in_new_kernel():
    import ast
    from pathlib import Path
    tree=ast.parse(Path(mc.__file__).read_text(encoding='utf-8'))
    forbidden={'open','connect','fit_transform','partial_fit','save_initial_rate','load_rate_records','predict','train'}
    for node in ast.walk(tree):
        if isinstance(node,ast.Call):
            name=getattr(node.func,'id',None) or getattr(node.func,'attr',None)
            assert name not in forbidden


@pytest.mark.parametrize('value',[True,'0.01'])
def test_joint_coefficients_require_actual_finite_numbers(value):
    exp=mc.standard_synthetic_experiment()
    model=model_for(exp)
    rows=[list(row) for row in model.loadings];rows[0][0]=value
    result=mc.propagate_synthetic_measurements(exp,replace(model,loadings=tuple(map(tuple,rows))))
    assert result['status']=='NOT_ESTIMABLE'
    assert result['executed_draws']==0


def test_unrepresentable_reading_support_fails_before_sampling():
    exp=mc.standard_synthetic_experiment()
    result=mc.propagate_synthetic_measurements(exp,model_for(exp,sd=1.7e308))
    assert result['status']=='NUMERICAL_FAILURE'
    assert result['executed_draws']==0
    assert result['analysis_failures'][0]['code']=='PHYSICAL_UNIT_RESTORATION_OVERFLOW'
    assert result['mc_precision_state']=='NOT_CALCULATED'
    json.dumps(result,allow_nan=False)


@pytest.mark.parametrize('field',['loadings','covariance','supports','quantity_units','reading_noise_sd','latent_ids','dependence_statement'])
def test_missing_joint_fields_are_metadata_failures_not_numerical_failures(field):
    exp=mc.standard_synthetic_experiment()
    result=mc.propagate_synthetic_measurements(exp,replace(model_for(exp),**{field:None}))
    assert result['status']=='MISSING_UNCERTAINTY_INPUTS'
    assert result['executed_draws']==0 and result['parameter_summary'] is None
    json.dumps(result,allow_nan=False)


def test_final_guard_preserves_actual_execution_audit_when_summary_corrupted(monkeypatch):
    original=mc._summary
    def corrupted(*args):
        output=original(*args)
        output['mean'][0]=float('nan')
        return output
    monkeypatch.setattr(mc,'_summary',corrupted)
    result=run(draws=4)
    assert result['status']=='NUMERICAL_FAILURE'
    assert result['executed_draws']==result['requested_draws']==4
    assert result['failed_draws']==0  # Final result validation failed, not the draws.
    assert len(result['draws'])==4
    assert result['metadata']['fixture_sha256']
    assert result['parameter_summary'] is None and result['rate_summary'] is None
    assert result['analysis_failures'][-1]['code']=='NONFINITE_RESULT_NUMBER'
    assert result['nonfinite_output_count']==0
    json.dumps(result,allow_nan=False)


def reference_hash(value):
    return hashlib.sha256(json.dumps(value,sort_keys=True,ensure_ascii=False,
        separators=(',',':'),allow_nan=False).encode('utf-8')).hexdigest()


def assert_counts(out,requested,executed,failed):
    assert out['requested_draws']==requested
    assert out['executed_draws']==executed==len(out['draws'])
    assert out['failed_draws']==failed
    assert out['successful_draws']==executed-failed
    assert out['unexecuted_draws']==requested-executed
    assert failed==sum(d['failure'] is not None for d in out['draws'])
    assert out['nonfinite_output_count']==0
    json.dumps(out,allow_nan=False)


@pytest.mark.parametrize('stage',['c1','c2a'])
@pytest.mark.parametrize('kind',['missing','wrong_type'])
def test_p1_a_missing_or_typed_fingerprint_returns_complete_failure(monkeypatch,stage,kind):
    attr='analyze_initial_rate' if stage=='c1' else 'fit_michaelis_menten'
    original=getattr(mc,attr)
    def injected(*args,**kwargs):
        out=original(*args,**kwargs)
        meta=out['analysis_metadata'] if stage=='c1' else out['metadata']
        field='analysis_fingerprint' if stage=='c1' else 'result_sha256'
        if kind=='missing':meta.pop(field)
        else:meta[field]=123
        return out
    monkeypatch.setattr(mc,attr,injected)
    out=run(draws=4)
    assert_counts(out,4,4,4)
    assert out['status']=='NUMERICAL_FAILURE' and out['parameter_summary'] is None
    expected='REQUIRED_FIELD_MISSING' if kind=='missing' else 'INTERNAL_RESULT_FIELD_TYPE'
    assert all(d['failure']['code']==expected for d in out['draws'])
    assert all(d['failure']['stage']==('C1_RESULT_VALIDATION' if stage=='c1' else 'C2A_RESULT_VALIDATION') for d in out['draws'])


def test_p1_a_single_failed_draw_keeps_partial_successes_without_intervals(monkeypatch):
    original=mc.fit_michaelis_menten;calls=0
    def injected(*args,**kwargs):
        nonlocal calls
        calls+=1
        out=original(*args,**kwargs)
        if calls==2:out['metadata'].pop('result_sha256')
        return out
    monkeypatch.setattr(mc,'fit_michaelis_menten',injected)
    out=run(draws=4)
    assert_counts(out,4,4,1)
    assert out['draws'][1]['draw_id']=='DRAW-00001' and out['draws'][1]['failure']
    assert out['parameter_summary'] is None and out['rate_summary'] is None


@pytest.mark.parametrize('field',['source_id','covariance','reading_noise_sd'])
def test_p1_a_missing_entry_source_or_metadata_keeps_unexecuted_budget(field):
    exp=mc.standard_synthetic_experiment()
    model=replace(model_for(exp),**{field:None})
    out=mc.propagate_synthetic_measurements(exp,model,mc.PropagationConfig(4))
    assert_counts(out,4,0,0)
    assert out['status']=='MISSING_UNCERTAINTY_INPUTS'
    assert out['analysis_failures'][0]['stage']=='INPUT_VALIDATION'


@pytest.mark.parametrize('mode',['input_digest','result_digest','records_rehashed','configuration_rehashed','version_rehashed','units_rehashed',
    'duplicate_prediction_rehashed','observed_rate_rehashed','count_rehashed'])
def test_p1_b_c2a_return_must_bind_trusted_inputs_and_configuration(monkeypatch,mode):
    original=mc.fit_michaelis_menten
    def injected(*args,**kwargs):
        out=original(*args,**kwargs)
        if mode=='input_digest':out['metadata']['input_sha256']='0'*64
        if mode=='result_digest':out['metadata']['result_sha256']='0'*64
        if mode=='records_rehashed':
            out['input_records'][0]['variant_id']='OTHER'
            out['metadata']['input_sha256']=reference_hash(sorted(out['input_records'],key=lambda r:r['analysis_id']))
            out['review']['input_sha256']=out['metadata']['input_sha256']
        if mode=='configuration_rehashed':out['metadata']['configuration']['ftol']=.5
        if mode=='version_rehashed':out['metadata']['algorithm_version']='UNREVIEWED'
        if mode=='units_rehashed':out['parameters']['Km_unit']='mM'
        if mode=='duplicate_prediction_rehashed':out['predictions'][-1]['analysis_id']=out['predictions'][0]['analysis_id']
        if mode=='observed_rate_rehashed':out['predictions'][0]['observed_rate']+=.1
        if mode=='count_rehashed':out['statistics']['n']+=1
        if mode.endswith('rehashed'):
            body=deepcopy(out);body['metadata'].pop('result_sha256')
            out['metadata']['result_sha256']=reference_hash(body)
        return out
    monkeypatch.setattr(mc,'fit_michaelis_menten',injected)
    out=run(draws=4)
    assert_counts(out,4,4,4)
    assert out['status']=='NUMERICAL_FAILURE' and out['parameter_summary'] is None
    assert all(d['failure']['code'].startswith('INTEGRITY_MISMATCH') for d in out['draws'])


def test_p1_b_callee_cannot_replace_whole_input_snapshot_with_a_self_consistent_one(monkeypatch):
    original=mc.fit_michaelis_menten
    def injected(records,review):
        for r in records:r.conditions['pH']=8.
        review=replace(review,input_sha256=reference_hash(sorted([asdict(r) for r in records],key=lambda r:r['analysis_id'])))
        return original(records,review)
    exp=mc.standard_synthetic_experiment();model=model_for(exp);before=deepcopy((exp,model))
    monkeypatch.setattr(mc,'fit_michaelis_menten',injected)
    out=run(exp,model,draws=4)
    assert_counts(out,4,4,4)
    assert (exp,model)==before
    assert all(d['failure']['code']=='INTEGRITY_MISMATCH_C2A_INPUT' for d in out['draws'])


def test_p1_b_c1_self_consistent_source_replacement_is_rejected(monkeypatch):
    original=mc.analyze_initial_rate
    def injected(observations,*args,**kwargs):
        changed=[replace(o,source_file_id='UNDECLARED-SOURCE') for o in observations]
        return original(changed,*args,**kwargs)
    monkeypatch.setattr(mc,'analyze_initial_rate',injected)
    out=run(draws=4)
    assert_counts(out,4,4,4)
    assert all(d['failure']['code']=='INTEGRITY_MISMATCH_C1_INPUT' for d in out['draws'])


def test_p1_b_late_mutation_of_callee_owned_object_cannot_change_consumed_snapshot(monkeypatch):
    original_fit=mc.fit_michaelis_menten;original_summary=mc._summary;retained=[]
    def retain(*args,**kwargs):
        out=original_fit(*args,**kwargs);retained.append(out);return out
    def late(*args,**kwargs):
        retained[0]['metadata']['input_sha256']='0'*64
        retained[0]['parameters']['Km']=999.
        return original_summary(*args,**kwargs)
    monkeypatch.setattr(mc,'fit_michaelis_menten',retain)
    monkeypatch.setattr(mc,'_summary',late)
    out=estimated(run(draws=4))
    assert_counts(out,4,4,0)
    assert out['draws'][0]['parameters']['Km']==pytest.approx(20,rel=1e-7,abs=1e-8)
    assert out['draws'][0]['c2a_input_sha256']!='0'*64


@pytest.mark.parametrize('phase',['PRE_SUMMARY_INTEGRITY','POST_SUMMARY_INTEGRITY'])
def test_p1_b_post_sampling_tampering_is_rechecked_before_final_response(monkeypatch,phase):
    original=mc._check_draws;injected=False
    def corrupt_after_check(result,seals,current_phase):
        nonlocal injected
        ok=original(result,seals,current_phase)
        if current_phase==phase and not injected:
            injected=True;result['draws'][1]['c2a_input_sha256']='0'*64
        return ok
    monkeypatch.setattr(mc,'_check_draws',corrupt_after_check)
    out=run(draws=4)
    assert_counts(out,4,4,1)
    assert out['status']=='NUMERICAL_FAILURE' and out['parameter_summary'] is None
    assert out['draws'][1]['failure']['code']=='INTEGRITY_MISMATCH_DRAW'


@pytest.mark.parametrize('mode',['input_mutated','fingerprint_missing','finite_output_mutated'])
def test_p1_b_summary_must_bind_unchanged_inputs_and_its_result(monkeypatch,mode):
    original=mc._summary
    def injected(values,*args,**kwargs):
        if mode=='input_mutated':values[0][0]+=2
        out=original(values,*args,**kwargs)
        if mode=='fingerprint_missing':out.pop('analysis_fingerprint')
        if mode=='finite_output_mutated':out['mean'][0]+=2
        return out
    monkeypatch.setattr(mc,'_summary',injected)
    out=run(draws=4)
    assert_counts(out,4,4,0)
    assert out['status']=='NUMERICAL_FAILURE' and out['parameter_summary'] is None
    assert out['analysis_failures'][0]['code']=='REQUIRED_FIELD_MISSING' or out['analysis_failures'][0]['code'].startswith('INTEGRITY_MISMATCH')


def test_p1_a_final_response_exception_keeps_private_execution_ledger(monkeypatch):
    def broken(*args,**kwargs):raise KeyError('synthetic final response failure')
    monkeypatch.setattr(mc,'_finish_response',broken)
    out=run(draws=4)
    assert_counts(out,4,4,0)
    assert out['status']=='NUMERICAL_FAILURE' and out['parameter_summary'] is None
    assert out['analysis_failures'][0]['code']=='INTERNAL_RESPONSE_FAILURE'


@pytest.mark.parametrize('negative',[-1e-320,-math.ulp(0.)])
def test_p1_c_negative_variance_rejected_before_any_psd_tolerance(monkeypatch,negative):
    exp=mc.standard_synthetic_experiment();model=model_for(exp)
    cov=[list(row) for row in model.covariance];cov[0][0]=negative
    def forbidden(*args):raise AssertionError('Negative diagonal reached eigensolver')
    monkeypatch.setattr(np.linalg,'eigvalsh',forbidden)
    out=mc.propagate_synthetic_measurements(exp,replace(model,covariance=tuple(map(tuple,cov))),mc.PropagationConfig(4))
    assert_counts(out,4,0,0)
    assert out['status']=='NOT_ESTIMABLE'
    assert out['analysis_failures'][0]['code']=='NEGATIVE_VARIANCE'


def test_p1_c_zero_negative_offdiagonal_and_mixed_magnitude_psd_remain_legal():
    exp=mc.standard_synthetic_experiment()
    zero=estimated(run(exp,model_for(exp),draws=4));assert_counts(zero,4,4,0)
    load=np.zeros((5,5));load[0,0]=1e-100;load[1,1]=.001;load[2,2]=.04;load[3,2]=-.05;load[4,4]=.02
    model=mc.synthetic_error_model(exp,reading_noise_sd=0.,loadings=load.tolist())
    assert model.covariance[2][3]<0 and min(np.diag(model.covariance))>=0
    assert np.linalg.matrix_rank(np.asarray(model.covariance))<5
    out=estimated(run(exp,model,draws=4));assert_counts(out,4,4,0)


def test_p1_c_clear_negative_eigenvalue_does_not_get_jitter_or_projection():
    exp=mc.standard_synthetic_experiment();load=np.eye(5)*.01
    model=mc.synthetic_error_model(exp,reading_noise_sd=0.,loadings=load.tolist())
    cov=np.asarray(model.covariance).copy();cov[0,1]=cov[1,0]=2*cov[0,0]
    assert np.linalg.eigvalsh(cov).min()<0
    before=cov.copy()
    out=mc.propagate_synthetic_measurements(exp,replace(model,covariance=tuple(map(tuple,cov))),mc.PropagationConfig(4))
    assert_counts(out,4,0,0)
    assert out['status']=='NOT_ESTIMABLE' and out['analysis_failures'][0]['code']=='INVALID_COVARIANCE'
    assert np.array_equal(cov,before)


@pytest.mark.parametrize('value',[float('nan'),float('inf')])
def test_p1_c_nonfinite_covariance_cannot_start_draws(value):
    exp=mc.standard_synthetic_experiment();model=model_for(exp)
    cov=[list(row) for row in model.covariance];cov[0][0]=value
    out=mc.propagate_synthetic_measurements(exp,replace(model,covariance=tuple(map(tuple,cov))),mc.PropagationConfig(4))
    assert_counts(out,4,0,0)
    assert out['parameter_summary'] is None


def test_p1_a_exception_before_draw_snapshot_keeps_all_attempted_slots(monkeypatch):
    original=mc._one_draw
    def injected(*args,**kwargs):
        if args[4]==1:raise KeyError('synthetic missing internal field before snapshot')
        return original(*args,**kwargs)
    monkeypatch.setattr(mc,'_one_draw',injected)
    out=run(draws=4)
    assert_counts(out,4,4,1)
    assert out['draws'][1]['draw_id']=='DRAW-00001'
    assert out['draws'][1]['failure']['stage']=='DRAW_EXECUTION'
    assert len(out['draws'][1]['fixture_sha256'])==64
    assert out['parameter_summary'] is None


@pytest.mark.parametrize('mode',['metadata_missing','version_wrong'])
def test_p1_a_final_response_structure_and_version_are_verified(monkeypatch,mode):
    original=mc._check_draws
    def injected(out,seals,phase):
        ok=original(out,seals,phase)
        if phase=='FINAL_RESULT_VALIDATION':
            if mode=='metadata_missing':out.pop('metadata')
            else:out['metadata']['algorithm_version']='UNREVIEWED'
        return ok
    monkeypatch.setattr(mc,'_check_draws',injected)
    out=run(draws=4)
    assert_counts(out,4,4,0)
    assert out['status']=='NUMERICAL_FAILURE' and out['parameter_summary'] is None
    assert out['metadata']['algorithm_version']==mc.ALGORITHM_VERSION
