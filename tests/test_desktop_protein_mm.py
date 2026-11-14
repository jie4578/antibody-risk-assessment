"""C.2A Desktop: disposable synthetic databases only; no ML, Provider or real data."""
from copy import deepcopy
from dataclasses import replace
from html import escape
import hashlib
import json
from pathlib import Path
import sqlite3
from threading import Event
import time

import pytest
from PySide6.QtCore import QItemSelectionModel,QTimer,Qt

from desktop import protein_mm as app
from protein_engineering.initial_rate import Calibration,RateConfig
from protein_engineering.importer import preview_bytes
from test_mm_kinetics import synthetic_database,CONDITIONS,STAMP


def idle(page,qt):
    end=time.monotonic()+10
    while page._busy and time.monotonic()<end:
        qt.processEvents();time.sleep(.002)
    qt.processEvents();assert not page._busy,page.status.text()


@pytest.fixture
def page(synthetic_database,qt_application,monkeypatch):
    from desktop.widgets.protein_engineering import ProteinEngineeringPage
    store,ids=synthetic_database
    monkeypatch.setenv('PROTEIN_ENGINEERING_DATA_DIR',str(store.path.parent))
    p=ProteinEngineeringPage();p.database_path.setText(str(store.path));p.open_database();idle(p,qt_application)
    p.mm_panel.refresh_button.click();idle(p,qt_application)
    yield p,ids
    idle(p,qt_application);p.close();p.deleteLater();qt_application.processEvents()


def select(panel,ids):
    panel.table.clearSelection()
    model=panel.table.selectionModel()
    for row in range(panel.table.rowCount()):
        if panel.table.item(row,0).data(Qt.ItemDataRole.UserRole) in ids:
            model.select(panel.table.model().index(row,0),QItemSelectionModel.SelectionFlag.Select|QItemSelectionModel.SelectionFlag.Rows)


def review(panel,name='SYN reviewer',reason='Conditional synthetic data only'):
    panel.reviewer.setText(name);panel.review_time.setText(STAMP);panel.rationale.setText(reason)
    panel.acknowledge.setChecked(True);panel.direction.setChecked(True)


def fitted(page,qt,ids=None):
    p,original=page;m=p.mm_panel
    select(m,original if ids is None else ids);m.verify_button.click();idle(p,qt)
    assert m.snapshot is not None,m.status.text()
    review(m);assert m.fit_button.isEnabled(),m.status.text()
    m.fit_button.click();idle(p,qt)
    assert m.result is not None,m.status.text()
    return m


def raw_course(tag,s,*,unit='uM',batch='B',rate=None):
    value=5*s/(20+s) if rate is None else rate
    header='observation_id,batch_id,sample_id,biological_replicate,technical_replicate,well_id,substrate_concentration,substrate_concentration_unit,time_value,time_unit,raw_signal,signal_unit\n'
    return (header+''.join(f'{tag}-{t},{batch},S,BIO1,TECH2,{tag},{s},{unit},{t},min,{1000+2*value*t},RFU\n' for t in range(5))).encode()


def add_course(store,tag,s,*,unit='uM',batch='B',rate=None,calibrated=True):
    c1=store.initial_rate_records()[0]['result']
    cal=Calibration(**c1['analysis_metadata']['calibration']) if calibrated else None
    store.commit_preview(preview_bytes('kinetic_timecourse',raw_course(tag,s,unit=unit,batch=batch,rate=rate),tag+'.csv'))
    course=next(c for c in store.time_courses() if c['well_id']==tag)
    return store.save_initial_rate(store.analyze_time_course(course['series_id'],RateConfig(0,4,'min'),calibration=cal))


def test_multiselect_sorting_identity_fit_and_readonly_provenance(page,qt_application):
    p,ids=page;m=p.mm_panel
    assert m.table.rowCount()==7 and not m.selected_ids() and not m.fit_button.isEnabled()
    m.table.sortItems(5,Qt.SortOrder.DescendingOrder)
    before=p.store.path.read_bytes();old=p.store.initial_rate_records()
    m=fitted(page,qt_application)
    assert set(m.selected_ids())==set(ids)
    assert set(m.snapshot['ids'])==set(ids)
    assert m.result['status']=='FIT_WITH_LIMITATIONS'
    assert m.result['parameters']['Km']==pytest.approx(20,rel=1e-8)
    assert m.result['parameters']['Vmax']==pytest.approx(5,rel=1e-8)
    assert set(r['analysis_id'] for r in m.result['predictions'])==set(ids)
    assert m.predictions.rowCount()==7 and m.plot.result is m.result
    assert 'NOT_ESTABLISHED' in m.result_text.toPlainText() and 'NOT_CALCULATED' in m.result_text.toPlainText()
    assert all(r['variant_id']=='V' and r['batch_id']=='B' for r in m.snapshot['sources'])
    assert p.store.path.read_bytes()==before and p.store.initial_rate_records()==old
    assert not any(Path(str(p.store.path)+s).exists() for s in ('-wal','-shm','-journal'))


def test_selection_and_review_edits_invalidate_old_results(page,qt_application):
    p,ids=page;m=fitted(page,qt_application)
    m.reviewer.setText('OTHER')
    assert m.result is None and not m.fit_button.isEnabled() and not m.html_button.isEnabled()
    assert not m.acknowledge.isChecked()
    review(m);m.fit_button.click();idle(p,qt_application);assert m.result
    select(m,ids[:4])
    assert m.snapshot is None and m.result is None and not m.direction.isChecked()
    assert m.predictions.rowCount()==0 and m.plot.result is None


def test_missing_review_and_non_utc_cannot_run_fit(page,qt_application):
    p,ids=page;m=p.mm_panel;select(m,ids);m.verify_button.click();idle(p,qt_application)
    assert not m.fit_button.isEnabled()
    review(m);m.review_time.setText('2026-11-13T10:00:00+08:00')
    m.acknowledge.setChecked(True);m.direction.setChecked(True)
    m.fit_button.click();idle(p,qt_application)
    assert m.result is None and 'UTC' in m.status.text()


@pytest.mark.parametrize('mode',['units','context','reused_observations','constant_rates'])
def test_core_qualification_cannot_be_overridden_by_confirmation(page,qt_application,mode):
    p,ids=page
    if mode=='units':ids=ids+[add_course(p.store,'UNIT',.02,unit='mM')]
    elif mode=='context':
        p.store.add_fields('experiment_batches',{**CONDITIONS,'batch_id':'B2','assay_id':'OTHER','assay_type':'timecourse','pH':8})
        ids=ids+[add_course(p.store,'CONTEXT',30,batch='B2')]
    elif mode=='reused_observations':
        old=p.store.initial_rate_records()[0]['result'];cal=Calibration(**old['analysis_metadata']['calibration'])
        ids=ids+[p.store.save_initial_rate(p.store.analyze_time_course(p.store.time_courses()[0]['series_id'],RateConfig(1,4,'min'),calibration=cal))]
    else:ids=[add_course(p.store,'CONST'+str(i),s,rate=1) for i,s in enumerate((2,5,10,20,40,80,160))]
    p.mm_panel.refresh();idle(p,qt_application);before=p.store.path.read_bytes()
    m=fitted(page,qt_application,ids)
    assert m.result['status']=='NOT_ESTIMABLE' and m.result['parameters'] is None
    assert m.predictions.rowCount()==0 and app.chart_geometry(m.result)==[]
    assert m.result['reasons'] and p.store.path.read_bytes()==before


def test_signal_only_saved_rate_is_not_a_product_rate(page,qt_application):
    p,ids=page;bad=add_course(p.store,'SIGNAL',30,calibrated=False)
    p.mm_panel.refresh();idle(p,qt_application);select(p.mm_panel,ids+[bad])
    before=p.store.path.read_bytes();p.mm_panel.verify();idle(p,qt_application)
    assert p.mm_panel.snapshot is None and not p.mm_panel.fit_button.isEnabled()
    assert 'calibration' in p.mm_panel.status.text()
    assert p.store.path.read_bytes()==before


@pytest.mark.parametrize('suffix',['-wal','-shm','-journal'])
def test_sidecar_is_rejected_without_recovery_deletion_or_writes(page,qt_application,suffix):
    p,ids=page;select(p.mm_panel,ids)
    sidecar=Path(str(p.store.path)+suffix);sidecar.write_bytes(b'SYNTHETIC sidecar evidence')
    before=p.store.path.read_bytes()
    p.mm_panel.verify();idle(p,qt_application)
    assert p.mm_panel.snapshot is None and 'checkpoint' in p.mm_panel.status.text()
    assert sidecar.read_bytes()==b'SYNTHETIC sidecar evidence' and p.store.path.read_bytes()==before


def test_live_wal_writer_blocks_audit_without_changing_contract(page,qt_application):
    p,ids=page;select(p.mm_panel,ids)
    with sqlite3.connect(p.store.path) as writer:
        assert writer.execute('PRAGMA journal_mode=WAL').fetchone()[0]=='wal'
        writer.execute('CREATE TABLE synthetic_writer_marker (value TEXT)');writer.commit()
        wal=Path(str(p.store.path)+'-wal');assert wal.exists()
        before=p.store.path.read_bytes();wal_before=wal.read_bytes()
        p.mm_panel.verify();idle(p,qt_application)
        assert p.mm_panel.snapshot is None and 'checkpoint' in p.mm_panel.status.text()
        assert p.store.path.read_bytes()==before and wal.read_bytes()==wal_before


@pytest.mark.parametrize('action',['refresh','verify'])
def test_closed_wal_header_without_sidecars_is_refused_before_sqlite_open(page,qt_application,action):
    p,ids=page;select(p.mm_panel,ids)
    writer=sqlite3.connect(p.store.path);writer.execute('PRAGMA journal_mode=WAL');writer.close()
    assert p.store.path.read_bytes()[18:20]==b'\x02\x02'
    assert not any(Path(str(p.store.path)+s).exists() for s in ('-wal','-shm'))
    before=p.store.path.read_bytes()
    getattr(p.mm_panel,action)();idle(p,qt_application)
    assert p.mm_panel.snapshot is None and 'WAL' in p.mm_panel.status.text()
    assert p.store.path.read_bytes()==before
    assert not any(Path(str(p.store.path)+s).exists() for s in ('-wal','-shm','-journal'))


@pytest.mark.parametrize('suffix',['-wal','-shm','-journal'])
def test_catalog_refresh_does_not_recover_or_delete_sidecars(page,qt_application,suffix):
    p,_=page;sidecar=Path(str(p.store.path)+suffix);sidecar.write_bytes(b'SYNTHETIC evidence')
    before=p.store.path.read_bytes();p.mm_panel.refresh();idle(p,qt_application)
    assert p.mm_panel.table.rowCount()==0 and p.mm_panel.snapshot is None
    assert sidecar.read_bytes()==b'SYNTHETIC evidence' and p.store.path.read_bytes()==before


def test_source_byte_corruption_fails_closed(page,qt_application):
    p,ids=page
    with p.store._connection() as db:
        db.execute('DROP TRIGGER source_no_update');db.execute("UPDATE source_files SET raw_bytes=x'00'")
    before=p.store.path.read_bytes();select(p.mm_panel,ids);p.mm_panel.verify();idle(p,qt_application)
    assert p.mm_panel.snapshot is None and 'SHA256' in p.mm_panel.status.text()
    assert not p.mm_panel.fit_button.isEnabled() and p.store.path.read_bytes()==before


def test_missing_scipy_is_explicit_and_does_not_crash_page(page,qt_application,monkeypatch):
    import builtins
    original=builtins.__import__
    def unavailable(name,*a,**k):
        if name=='scipy' or name.startswith('scipy.'):raise ImportError('SYNTHETIC missing scipy')
        return original(name,*a,**k)
    monkeypatch.setattr(builtins,'__import__',unavailable)
    p,ids=page;m=p.mm_panel;select(m,ids);m.verify();idle(p,qt_application)
    assert m.snapshot and not m.snapshot['dependencies']['available']
    assert not m.fit_button.isEnabled() and 'SciPy' in m.status.text() and m.result is None


def test_async_duplicate_click_and_stale_review_result_are_guarded(page,qt_application,monkeypatch):
    p,ids=page;m=p.mm_panel;select(m,ids);m.verify();idle(p,qt_application);review(m)
    original=app.run_fit;entered,release=Event(),Event();calls=[]
    def slow(*args):
        calls.append(1);entered.set()
        if not release.wait(5):raise RuntimeError('Synthetic timeout')
        return original(*args)
    monkeypatch.setattr(app,'run_fit',slow)
    beats=[];timer=QTimer();timer.setInterval(1);timer.timeout.connect(lambda:beats.append(1));timer.start()
    try:
        m.fit();m.fit()
        end=time.monotonic()+.15
        while time.monotonic()<end:qt_application.processEvents();time.sleep(.002)
        assert entered.is_set() and len(calls)==1 and p._busy and beats
        assert not m.table.isEnabled() and not p.database_path.isEnabled()
        m.reviewer.setText('CHANGED DURING WORK')
    finally:release.set();idle(p,qt_application);timer.stop()
    assert m.result is None and '丢弃' in m.status.text() and not m.json_button.isEnabled()


def test_database_change_clears_snapshot_and_report_buttons(page,qt_application,tmp_path):
    p,_=page;m=fitted(page,qt_application)
    p.database_path.setText(str(tmp_path/'other.sqlite3'));p._database_changed()
    assert p.store is None and m.result is None and m.snapshot is None
    assert m.table.rowCount()==0 and not m.fit_button.isEnabled() and not m.html_button.isEnabled()
    assert not (tmp_path/'other.sqlite3').exists()


def test_incomplete_saved_record_is_refused_without_ui_crash(page,qt_application):
    p,ids=page
    with p.store._connection() as db:
        db.execute('DROP TRIGGER analysis_no_update')
        db.execute("UPDATE initial_rate_analyses SET result_json='{}' WHERE analysis_id=?",(ids[0],))
    p.mm_panel.refresh();idle(p,qt_application)
    select(p.mm_panel,ids);before=p.store.path.read_bytes();p.mm_panel.verify();idle(p,qt_application)
    assert p.mm_panel.snapshot is None and p.mm_panel.result is None
    assert not p.mm_panel.fit_button.isEnabled() and p.store.path.read_bytes()==before


def test_corrupt_background_result_cannot_be_displayed_as_success(page,qt_application,monkeypatch):
    p,ids=page;m=p.mm_panel;select(m,ids);m.verify();idle(p,qt_application);review(m)
    monkeypatch.setattr(app,'run_fit',lambda *a:dict(status='FIT_WITH_LIMITATIONS'))
    m.fit();idle(p,qt_application)
    assert m.result is None and m.snapshot is None and not m.html_button.isEnabled()
    assert '完整性' in m.status.text()


@pytest.mark.parametrize('kind',['json','html'])
def test_reports_are_local_complete_minimized_and_html_escaped(page,qt_application,tmp_path,monkeypatch,kind):
    p,_=page;m=fitted(page,qt_application)
    malicious='<img src="https://example.invalid/x" onerror="bad()"><script>bad()</script>&'
    review(m,name=malicious,reason=malicious);m.fit();idle(p,qt_application)
    destination=tmp_path/('SYN-report.'+kind)
    monkeypatch.setattr('desktop.widgets.protein_mm_fit.QFileDialog.getSaveFileName',lambda *a:(str(destination),kind))
    before=p.store.path.read_bytes();m.export(kind);idle(p,qt_application)
    text=destination.read_text(encoding='utf-8')
    assert p.store.path.read_bytes()==before and not list(tmp_path.glob('.protein-mm-*'))
    assert 'ACDEFG' not in text and 'raw_base64' not in text
    assert 'NOT_ESTABLISHED' in text and 'NOT_CALCULATED' in text
    if kind=='json':
        value=json.loads(text,parse_constant=lambda x:pytest.fail('Nonfinite JSON '+x))
        assert value['payload']['calculation']['parameters']==m.result['parameters']
        assert len(value['payload']['source_summary'])==7
        raw=json.dumps(value['payload'],ensure_ascii=False,sort_keys=True,separators=(',',':'),allow_nan=False).encode()
        assert hashlib.sha256(raw).hexdigest()==value['report_sha256']
    else:
        assert '<svg ' in text and '<script>' not in text and '<img ' not in text
        assert escape(malicious) in text and 'default-src' in text


def test_cancel_existing_file_and_io_failure_never_overwrite(page,qt_application,tmp_path,monkeypatch):
    p,_=page;m=fitted(page,qt_application);fingerprint=m.result['metadata']['result_sha256']
    dialog='desktop.widgets.protein_mm_fit.QFileDialog.getSaveFileName'
    monkeypatch.setattr(dialog,lambda *a:('',''));m.export('json')
    assert '取消' in m.status.text() and m.result['metadata']['result_sha256']==fingerprint
    destination=tmp_path/'existing.json';destination.write_text('ORIGINAL',encoding='utf-8')
    monkeypatch.setattr(dialog,lambda *a:(str(destination),'json'));m.export('json');idle(p,qt_application)
    assert destination.read_text()=='ORIGINAL' and m.result is not None
    destination=tmp_path/'failed.json'
    def blocked(*a,**k):raise OSError('SYNTHETIC no hardlink support')
    monkeypatch.setattr(app.os,'link',blocked);m.export('json');idle(p,qt_application)
    assert not destination.exists() and not list(tmp_path.glob('.protein-mm-*'))
    assert m.result is not None and '未完成' in m.status.text()


def test_export_rechecks_current_source_and_refuses_tampered_result(page,qt_application,tmp_path,monkeypatch):
    p,ids=page;m=fitted(page,qt_application)
    changed=deepcopy(m.result);changed['parameters']['Km']=999
    with pytest.raises(ValueError,match='摘要'):
        app.export_report(p.store.path,ids,m.snapshot['input_sha256'],changed,tmp_path/'bad.json','json',m.snapshot['database_sha256'])
    assert not (tmp_path/'bad.json').exists()
    with p.store._connection() as db:
        db.execute('DROP TRIGGER analysis_input_no_delete')
        db.execute('DELETE FROM initial_rate_inputs WHERE analysis_id=?',(ids[0],))
    destination=tmp_path/'changed.json'
    monkeypatch.setattr('desktop.widgets.protein_mm_fit.QFileDialog.getSaveFileName',lambda *a:(str(destination),'json'))
    before=p.store.path.read_bytes();m.export('json');idle(p,qt_application)
    assert not destination.exists() and m.result is None and m.snapshot is None
    assert p.store.path.read_bytes()==before


def test_display_curve_is_only_original_parameter_prediction(page,qt_application):
    m=fitted(page,qt_application);g=app.chart_geometry(m.result)
    assert len(g)==2 and len(g[0]['scatter'])==len(g[1]['scatter'])==7
    assert len(g[0]['line'])==121 and len(g[1]['line'])==2
    assert g[0]['x_range']==[2,160]
    assert 'confidence' not in app.chart_svg(m.result).lower()


@pytest.mark.parametrize('number',[float('inf'),float('-inf'),float('nan')])
def test_nonfinite_native_result_cannot_be_published(page,qt_application,tmp_path,number):
    p,ids=page;m=fitted(page,qt_application);bad=deepcopy(m.result)
    bad['parameters']['Km']=number
    with pytest.raises(ValueError):
        app.export_report(p.store.path,ids,m.snapshot['input_sha256'],bad,tmp_path/'nonfinite.json','json',m.snapshot['database_sha256'])
    assert not (tmp_path/'nonfinite.json').exists() and not list(tmp_path.glob('.protein-mm-*'))


@pytest.mark.parametrize('stage',['before_fit','during_fit','before_export'])
def test_any_database_change_invalidates_review_even_unselected_records(page,qt_application,tmp_path,monkeypatch,stage):
    p,ids=page;m=p.mm_panel;select(m,ids);m.verify();idle(p,qt_application);review(m)
    def change():
        with p.store._connection() as db:
            db.execute('CREATE TABLE synthetic_unselected_change (value TEXT)')
    destination=tmp_path/'stale.json'
    if stage=='during_fit':
        native=app.fit_michaelis_menten
        def change_after_native(*a,**k):
            value=native(*a,**k);change();return value
        monkeypatch.setattr(app,'fit_michaelis_menten',change_after_native)
    elif stage=='before_fit':change()
    if stage=='before_export':
        m.fit();idle(p,qt_application);assert m.result is not None
        change()
        monkeypatch.setattr('desktop.widgets.protein_mm_fit.QFileDialog.getSaveFileName',lambda *a:(str(destination),'json'))
        m.export('json')
    else:m.fit()
    idle(p,qt_application)
    assert m.result is None and m.snapshot is None and '旧审核失效' in m.status.text()
    assert not destination.exists() and not m.json_button.isEnabled()


def test_single_desktop_session_import_c1_save_then_mm_has_no_sidecars(page,qt_application,tmp_path,monkeypatch):
    p,old_ids=page;path=tmp_path/'SYN-NEW.csv';path.write_bytes(raw_course('UI-NEW',30))
    p.import_kind.setCurrentIndex(p.import_kind.findData('kinetic_timecourse'))
    p.input_path.setText(str(path));p.sheet.addItem('CSV')
    p.preview_button.click();idle(p,qt_application);p.import_button.click();idle(p,qt_application)
    rate=p.rate_panel;rate.refresh();idle(p,qt_application)
    course=next(c for c in rate.courses if c['well_id']=='UI-NEW')
    rate.course.setCurrentIndex(rate.course.findData(course['series_id']))
    cal=tmp_path/'SYNTHETIC-calibration.json'
    monkeypatch.setattr('desktop.widgets.protein_initial_rate.QFileDialog.getOpenFileName',lambda *a:(str(cal),'JSON'))
    rate.calibration_button.click();idle(p,qt_application)
    rate.start.setText('0');rate.end.setText('4');rate.confirm_timecourse.setChecked(True)
    rate.analyze_button.click();idle(p,qt_application);assert rate.result['status']=='ESTIMATED'
    rate.save_button.click();idle(p,qt_application)
    assert len(p.store.initial_rate_records())==8 and p.mm_panel.table.rowCount()==0
    p.mm_panel.refresh();idle(p,qt_application)
    ids=[r['analysis_id'] for r in p.store.initial_rate_records()]
    before=p.store.path.read_bytes();m=fitted(page,qt_application,ids)
    assert m.result['status']=='FIT_WITH_LIMITATIONS' and m.result['statistics']['n']==8
    assert p.store.path.read_bytes()==before
    assert not any(Path(str(p.store.path)+s).exists() for s in ('-wal','-shm','-journal'))


@pytest.mark.parametrize('kind',['json','html'])
@pytest.mark.parametrize('number',[float('inf'),float('-inf'),float('nan')])
def test_ui_nonfinite_export_invalidates_without_uncaught_exception(page,qt_application,tmp_path,monkeypatch,kind,number):
    p,_=page;m=fitted(page,qt_application);m.result['parameters']['Km']=number
    target=tmp_path/('nonfinite.'+kind)
    monkeypatch.setattr('desktop.widgets.protein_mm_fit.QFileDialog.getSaveFileName',lambda *a:(str(target),kind))
    m.export(kind)
    assert m.result is None and m.snapshot is None and not m.html_button.isEnabled() and not m.json_button.isEnabled()
    assert '结果已失效' in m.status.text() and not target.exists()


@pytest.mark.parametrize('failure',['source_missing','target_permission','dialog'])
def test_export_error_classification_preserves_only_valid_computation(page,qt_application,tmp_path,monkeypatch,failure):
    p,_=page;m=fitted(page,qt_application);fingerprint=m.result['metadata']['result_sha256'];target=tmp_path/'result.json'
    dialog='desktop.widgets.protein_mm_fit.QFileDialog.getSaveFileName'
    monkeypatch.setattr(dialog,lambda *a:(str(target),'JSON'))
    if failure=='source_missing':p.store.path.unlink()
    elif failure=='target_permission':
        def denied(*a):raise PermissionError('SYNTHETIC target denied')
        monkeypatch.setattr(app.os,'link',denied)
    else:
        def unavailable(*a):raise RuntimeError('SYNTHETIC dialog unavailable')
        monkeypatch.setattr(dialog,unavailable)
    m.export('json');idle(p,qt_application)
    if failure=='source_missing':assert m.result is None and m.snapshot is None and not m.json_button.isEnabled()
    else:
        assert m.result['metadata']['result_sha256']==fingerprint and m.json_button.isEnabled()
        assert '计算结果保留' in m.status.text()
    assert not target.exists() and not list(tmp_path.glob('.protein-mm-*'))


def test_same_bytes_file_replacement_invalidates_identity_bound_review(page,qt_application,tmp_path):
    p,ids=page;m=p.mm_panel;select(m,ids);m.verify();idle(p,qt_application);review(m)
    replacement=tmp_path/'same-bytes.sqlite3';replacement.write_bytes(p.store.path.read_bytes())
    replacement.replace(p.store.path);m.fit();idle(p,qt_application)
    assert m.result is None and m.snapshot is None and '旧审核失效' in m.status.text()


def test_old_fit_returning_after_new_review_cannot_replace_current_result(page,qt_application,monkeypatch):
    p,ids=page;m=p.mm_panel;select(m,ids);m.verify();idle(p,qt_application);review(m,name='OLD_REVIEW')
    entered,release=Event(),Event();native=app.run_fit;first=[]
    def delayed_first(*args):
        if not first:
            first.append(True);entered.set()
            if not release.wait(8):raise RuntimeError('Controlled old-fit barrier timeout')
        return native(*args)
    monkeypatch.setattr(app,'run_fit',delayed_first)
    def pump(predicate):
        deadline=time.monotonic()+8
        while not predicate() and time.monotonic()<deadline:qt_application.processEvents()
        qt_application.processEvents();assert predicate()
    try:
        m.fit();pump(entered.is_set);old=p._current_operation
        p._database_changed();p.open_database();idle(p,qt_application)
        m.refresh();idle(p,qt_application);select(m,ids);m.verify();idle(p,qt_application);review(m,name='NEW_REVIEW')
        m.fit();idle(p,qt_application);fingerprint=m.result['metadata']['result_sha256']
        release.set();pump(lambda:not p._operations)
    finally:release.set();pump(lambda:not p._operations)
    assert m.result['metadata']['result_sha256']==fingerprint and m.result['review']['reviewer']=='NEW_REVIEW'
    assert not m._pending and not p._busy and p.operation_history[old]['status']=='STALE_OPERATION'
