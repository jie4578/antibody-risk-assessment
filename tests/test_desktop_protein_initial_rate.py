"""Synthetic Desktop C.1 integration, queued worker slots and stale-state checks."""
import json
from threading import Event
import time

import pytest

from protein_engineering.importer import preview_bytes
from protein_engineering.models import EnzymeTarget,ProteinVariant,ProteinSample,ExperimentBatch
from protein_engineering.storage import ProteinStore


def idle(page,app):
    until=time.monotonic()+5
    while page._busy and time.monotonic()<until:
        app.processEvents();time.sleep(.002)
    app.processEvents()
    assert not page._busy,page.status.text()


@pytest.fixture
def page(qt_application,tmp_path,monkeypatch):
    from desktop.widgets.protein_engineering import ProteinEngineeringPage
    monkeypatch.setenv("PROTEIN_ENGINEERING_DATA_DIR",str(tmp_path))
    p=ProteinEngineeringPage()
    p.open_database();idle(p,qt_application)
    for r in [EnzymeTarget("T","Synthetic only"),ProteinVariant("V","T","Synthetic WT","WT","ACDEFG"),
              ProteinSample("S","V"),ExperimentBatch("B","A","timecourse")]:
        p.store.add(r)
    raw=b'observation_id,batch_id,sample_id,time_value,time_unit,raw_signal,signal_unit,blank_signal\nO0,B,S,0,min,5,RFU,0\nO1,B,S,1,min,7,RFU,0\nO2,B,S,2,min,9,RFU,0\nO3,B,S,3,min,11,RFU,0\n'
    p.store.commit_preview(preview_bytes("kinetic_timecourse",raw,"synthetic.csv"))
    p.rate_panel.refresh_button.click();idle(p,qt_application)
    yield p
    idle(p,qt_application)
    p.deleteLater()


def calculate(page,app):
    rate=page.rate_panel
    rate.confirm_timecourse.setChecked(True)
    rate.start.setText("0");rate.end.setText("3")
    rate.analyze_button.click();idle(page,app)
    return rate


def test_select_inspect_calculate_and_save_without_raw_overwrite(page,qt_application):
    rate=page.rate_panel
    assert rate.course.count()==1 and 'O0' in rate.raw_text.toPlainText()
    assert rate.result is None and not rate.save_button.isEnabled()
    original=page.store.records("kinetic_timecourse")
    rate=calculate(page,qt_application)
    assert rate.result["derived_initial_rate"]["slope"]==2
    assert "N=4" in rate.result_text.toPlainText()
    assert "INITIAL_RATE_NOT_VERIFIED" in rate.result_text.toPlainText()
    assert rate.save_button.isEnabled()
    rate.save_button.click();idle(page,qt_application)
    assert len(page.store.initial_rate_records())==1 and not rate.save_button.isEnabled()
    assert page.store.records("kinetic_timecourse")==original
    rate.read_saved_button.click();idle(page,qt_application)
    assert "已保存 1" in rate.result_text.toPlainText()
    assert rate.result is None and not rate.save_button.isEnabled()


def test_every_configuration_edit_invalidates_unsaved_result(page,qt_application):
    for change in [lambda r:r.end.setText("2"),lambda r:r.blank_mode.setCurrentIndex(1),
                   lambda r:r.missing.setCurrentIndex(1),lambda r:r.exclusions.setText('{"O0":"synthetic exclusion"}')]:
        r=calculate(page,qt_application)
        assert r.result is not None
        change(r)
        assert r.result is None and not r.save_button.isEnabled() and not r.result_text.toPlainText()
        r.blank_mode.setCurrentIndex(0);r.missing.setCurrentIndex(0);r.exclusions.clear()


def test_not_estimable_does_not_enable_save(page,qt_application):
    r=page.rate_panel
    r.confirm_timecourse.setChecked(True)
    r.start.setText("0");r.end.setText("1")
    r.analyze_button.click();idle(page,qt_application)
    assert r.result["status"]=="NOT_ESTIMABLE" and not r.save_button.isEnabled()
    assert "INSUFFICIENT_TIME_POINTS" in r.result_text.toPlainText()
    assert not page.store.initial_rate_records()


def test_timecourse_confirmation_required_and_not_auto_checked(page,qt_application):
    r=page.rate_panel
    assert not r.confirm_timecourse.isChecked()
    r.start.setText("0");r.end.setText("3")
    r.analyze_button.click();idle(page,qt_application)
    assert r.result["status"]=="NOT_ESTIMABLE" and not r.save_button.isEnabled()
    assert any(i["code"]=="NOT_TIME_COURSE" for i in r.result["reasons"])


def test_calibration_file_is_explicit_and_clearing_invalidates(page,qt_application,tmp_path,monkeypatch):
    from desktop.widgets import protein_initial_rate as module
    path=tmp_path/"synthetic-calibration.json"
    path.write_text(json.dumps(dict(calibration_id="SYN-C",signal_unit="RFU",product_unit="uM",signal_per_product=2,
        intercept=5,valid_signal_min=0,valid_signal_max=100,blank_mode="none")),encoding="utf-8")
    monkeypatch.setattr(module.QFileDialog,"getOpenFileName",lambda *a:(str(path),"JSON"))
    rate=page.rate_panel
    rate.calibration_button.click();idle(page,qt_application)
    assert rate.calibration and rate.result is None
    calculate(page,qt_application)
    assert rate.result["derived_initial_rate"]["product_rate"]["slope"]==1
    rate.clear_calibration_button.click()
    assert rate.calibration is None and rate.result is None and not rate.save_button.isEnabled()


def test_analysis_is_async_and_locks_configuration(page,qt_application,monkeypatch):
    from PySide6.QtCore import QTimer
    original=page.store.analyze_time_course
    entered,release=Event(),Event()
    def delayed(*args,**kwargs):
        entered.set()
        if not release.wait(3):
            raise RuntimeError("Synthetic test worker timeout")
        return original(*args,**kwargs)
    monkeypatch.setattr(page.store,"analyze_time_course",delayed)
    rate=page.rate_panel;rate.confirm_timecourse.setChecked(True);rate.start.setText("0");rate.end.setText("3")
    beats=[]
    timer=QTimer();timer.setInterval(1);timer.timeout.connect(lambda:beats.append(True));timer.start()
    try:
        rate.analyze_button.click()
        until=time.monotonic()+.2
        while time.monotonic()<until:
            qt_application.processEvents();time.sleep(.002)
        assert entered.is_set() and page._busy and beats
        assert not rate.start.isEnabled() and not page.database_path.isEnabled()
    finally:
        release.set();timer.stop()
        idle(page,qt_application)
    assert rate.result["status"]=="ESTIMATED"


def test_database_switch_clears_series_calculation_and_calibration(page,qt_application,tmp_path):
    rate=calculate(page,qt_application)
    page.database_path.setText(str(tmp_path/"other.sqlite3"));page._database_changed()
    assert page.store is None and rate.course.count()==0 and rate.result is None
    assert not rate.save_button.isEnabled() and not rate.analyze_button.isEnabled()


def test_private_export_explicit_path_and_no_overwrite(page,qt_application,tmp_path,monkeypatch):
    from desktop.widgets import protein_engineering as module
    target=tmp_path/"protein-private-snapshot.json"
    monkeypatch.setattr(module.QFileDialog,"getSaveFileName",lambda *a:(str(target),"JSON"))
    page.export_button.click();idle(page,qt_application)
    original=target.read_bytes()
    assert json.loads(original)["payload"]["records"]["kinetic_timecourse"]
    page.export_button.click();idle(page,qt_application)
    assert target.read_bytes()==original
    assert "操作未完成" in page.status.text()
