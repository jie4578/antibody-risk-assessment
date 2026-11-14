"""Deterministic task/session regressions; original audit assertions are retained."""
from pathlib import Path
import shutil
import sys
from threading import Event,get_ident
import time

import pytest
from PySide6.QtCore import QThreadPool
from test_mm_kinetics import synthetic_database
from test_desktop_protein_mm import page,select,review,idle


def pump(qt,predicate):
    deadline=time.monotonic()+8
    while not predicate() and time.monotonic()<deadline:qt.processEvents()
    qt.processEvents();assert predicate()


@pytest.mark.parametrize('order',['A_FIRST','B_FIRST'])
@pytest.mark.parametrize('a_fails,b_fails',[(False,False),(True,False),(False,True),(True,True)])
def test_task_identity_generation_and_gui_thread_delivery(page,qt_application,monkeypatch,order,a_fails,b_fails):
    p,_=page;entered={x:Event() for x in 'AB'};release={x:Event() for x in 'AB'};calls=[];errors=[]
    monkeypatch.setattr(sys,'excepthook',lambda *args:errors.append(str(args[1])))
    gui=get_ident();old_store=p.store
    def work(name,failed):
        entered[name].set()
        if not release[name].wait(8):raise RuntimeError('Controlled task barrier timeout')
        if failed:raise ValueError('SYNTHETIC_'+name+'_FAILURE')
        return name
    def done(name):calls.append((name,get_ident()))
    a=p._run(lambda:work('A',a_fails),done,task_type='AUDIT_A',input_snapshot={'selected':['old']})
    pump(qt_application,entered['A'].is_set);generation=p._generation
    p._database_changed()
    b=p._run(lambda:work('B',b_fails),done,task_type='AUDIT_B',input_snapshot={'selected':['new']})
    pump(qt_application,entered['B'].is_set)
    try:
        first,second=('A','B') if order=='A_FIRST' else ('B','A')
        ids={'A':a,'B':b};release[first].set()
        pump(qt_application,lambda:p.operation_history[ids[first]]['physically_finished'])
        if first=='A':assert p._busy and p._current_operation==b
        release[second].set();pump(qt_application,lambda:not p._operations)
    finally:
        for event in release.values():event.set()
        pump(qt_application,lambda:not p._operations)
    assert not errors and calls==([] if b_fails else [('B',gui)])
    assert p.store is None and not isinstance(p.store,dict) and not p._busy
    assert p._generation==generation+1
    assert p.operation_history[a]['status']=='STALE_OPERATION'
    assert p.operation_history[b]['status']==('FAILED' if b_fails else 'SUCCEEDED')
    assert p.operation_history[a]['session_id']!=p.operation_history[b]['session_id']
    assert all(row['executed'] and row['physically_finished'] for key,row in p.operation_history.items() if key in (a,b))
    p.store=old_store


@pytest.mark.parametrize('same_database',[True,False])
@pytest.mark.parametrize('old_first',[True,False])
def test_real_open_and_old_fit_have_separate_callbacks(page,qt_application,monkeypatch,tmp_path,same_database,old_first):
    from desktop import protein_mm as app
    import desktop.widgets.protein_engineering as host
    p,ids=page;m=p.mm_panel;select(m,ids);m.verify();idle(p,qt_application);review(m)
    entered,release,returned,new_entered,new_release=Event(),Event(),Event(),Event(),Event();errors=[]
    monkeypatch.setattr(sys,'excepthook',lambda *a:errors.append(str(a[1])))
    native=app.run_fit
    def delayed(*a):
        entered.set()
        if not release.wait(8):raise RuntimeError('Synthetic old timeout')
        try:return native(*a)
        finally:returned.set()
    monkeypatch.setattr(app,'run_fit',delayed)
    path=p.store.path
    if not same_database:
        second=tmp_path/'second.sqlite3';shutil.copyfile(path,second);path=second
    constructor=host.ProteinStore
    def new_store(value):
        new_entered.set()
        if not new_release.wait(8):raise RuntimeError('Synthetic open timeout')
        return constructor(value)
    monkeypatch.setattr(host,'ProteinStore',new_store)
    try:
        m.fit();pump(qt_application,entered.is_set);old=p._current_operation
        p.database_path.setText(str(path));p._database_changed();p.open_database();pump(qt_application,new_entered.is_set)
        if old_first:
            release.set();pump(qt_application,lambda:p.operation_history[old]['physically_finished'])
            assert p._busy and p.store is None
            new_release.set()
        else:
            new_release.set();pump(qt_application,lambda:not p._busy)
            release.set()
        pump(qt_application,lambda:not p._operations)
    finally:
        release.set();new_release.set();pump(qt_application,lambda:not p._operations)
    assert not errors and isinstance(p.store,host._ProteinStoreType) and Path(p.store.path)==path
    assert m.result is None and not m._pending and not p._busy
    assert p.operation_history[old]['status']=='STALE_OPERATION'


def test_running_cancel_has_logical_and_physical_terminal_states(page,qt_application):
    p,_=page;entered,release=Event(),Event();calls=[]
    def work():
        entered.set()
        if not release.wait(8):raise RuntimeError('Controlled cancellation timeout')
        return 'OLD'
    try:
        old=p._run(work,calls.append);pump(qt_application,entered.is_set)
        p._worker.cancel();pump(qt_application,lambda:not p._busy)
        assert p.operation_history[old]['status']=='CANCELLED' and not p.operation_history[old]['physically_finished']
        new=p._run(lambda:'NEW',calls.append)
        pump(qt_application,lambda:p.operation_history[new]['physically_finished'])
        release.set();pump(qt_application,lambda:not p._operations)
    finally:release.set();pump(qt_application,lambda:not p._operations)
    assert calls==['NEW'] and p.operation_history[old]['executed'] is True
    assert p.operation_history[old]['status']=='CANCELLED' and not p._busy


def test_queued_cancel_and_pool_clear_never_leave_busy(page,qt_application):
    from desktop.workers import Worker
    p,_=page;pool=QThreadPool.globalInstance();previous=pool.maxThreadCount();pool.setMaxThreadCount(1)
    entered,release=Event(),Event();calls=[]
    def block():entered.set();release.wait(8)
    blocker=Worker(block);pool.start(blocker);pump(qt_application,entered.is_set)
    try:
        operation=p._run(lambda:calls.append('EXECUTED'),calls.append)
        p._worker.cancel();pool.clear();pump(qt_application,lambda:not p._busy)
        assert not calls and p.operation_history[operation]['executed'] is False
        assert p.operation_history[operation]['physically_finished'] and p.operation_history[operation]['status']=='CANCELLED'
    finally:
        release.set();pump(qt_application,lambda:pool.activeThreadCount()==0);pool.setMaxThreadCount(previous)


def test_callback_exception_is_caught_and_next_operation_can_run(page,qt_application,monkeypatch):
    p,_=page;errors=[];monkeypatch.setattr(sys,'excepthook',lambda *a:errors.append(str(a[1])))
    def failed(value):raise RuntimeError('SYNTHETIC_CALLBACK_FAILURE')
    operation=p._run(lambda:1,failed);pump(qt_application,lambda:not p._operations)
    assert not errors and p.operation_history[operation]['status']=='CALLBACK_FAILED' and not p._busy
    accepted=[];p._run(lambda:2,accepted.append);pump(qt_application,lambda:not p._operations)
    assert accepted==[2]


def test_closed_page_suppresses_callbacks_and_reaches_terminal(page,qt_application):
    p,_=page;entered,release=Event(),Event();calls=[]
    def work():entered.set();release.wait(8);return 'SHOULD_NOT_DISPLAY'
    operation=p._run(work,calls.append);pump(qt_application,entered.is_set);p.close()
    release.set();pump(qt_application,lambda:not p._operations)
    assert not calls and not p._busy and p.operation_history[operation]['physically_finished']
    assert p.operation_history[operation]['status'] in ('STALE_OPERATION','CLOSED_OPERATION','CANCELLED')


def test_repeated_generation_switches_keep_only_current_completion(page,qt_application):
    p,_=page;events=[];calls=[];identifiers=[]
    try:
        for index in range(4):
            entered,release=Event(),Event();events.append((entered,release))
            def work(i=index,e=entered,r=release):e.set();r.wait(8);return i
            identifiers.append(p._run(work,calls.append));pump(qt_application,entered.is_set)
            if index!=3:p._database_changed()
        # Explicit reverse completion order; no sleep-based scheduling assumptions.
        for identifier,(_,release) in reversed(list(zip(identifiers,events))):
            release.set();pump(qt_application,lambda:p.operation_history[identifier]['physically_finished'])
    finally:
        for _,release in events:release.set()
        pump(qt_application,lambda:not p._operations)
    assert calls==[3] and not p._busy
    assert all(p.operation_history[i]['status']=='STALE_OPERATION' for i in identifiers[:-1])


def test_failed_same_database_reopen_invalidates_old_review_immediately(page,qt_application,monkeypatch):
    from test_desktop_protein_mm import fitted
    import desktop.widgets.protein_engineering as host
    p,_=page;m=fitted(page,qt_application)
    def failed(path):raise PermissionError('SYNTHETIC reopen unavailable')
    monkeypatch.setattr(host,'ProteinStore',failed)
    previous=p._session_id;p.open_database()
    assert p._session_id!=previous and p.store is None and m.result is None and m.snapshot is None
    pump(qt_application,lambda:not p._operations)
    assert not p._busy and not m.fit_button.isEnabled() and not m.json_button.isEnabled()


def test_session_change_cancels_queued_old_callable_before_execution(page,qt_application):
    from desktop.workers import Worker
    p,_=page;pool=QThreadPool.globalInstance();previous=pool.maxThreadCount();pool.setMaxThreadCount(1)
    entered,release=Event(),Event();calls=[]
    def block():entered.set();release.wait(8)
    blocker=Worker(block);pool.start(blocker);pump(qt_application,entered.is_set)
    try:
        operation=p._run(lambda:calls.append('STALE_WRITE'),calls.append)
        p._database_changed();pump(qt_application,lambda:not p._operations)
        release.set();pump(qt_application,lambda:pool.activeThreadCount()==0)
        assert not calls and not p._busy
        assert p.operation_history[operation]['executed'] is False
        assert p.operation_history[operation]['status']=='STALE_OPERATION'
    finally:
        release.set();pump(qt_application,lambda:pool.activeThreadCount()==0);pool.setMaxThreadCount(previous)
