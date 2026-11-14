"""Source-side-effect and provenance regressions using only disposable v3 data."""
from contextlib import closing
import hashlib
import json
import os
from pathlib import Path
import sqlite3
import subprocess
import sys
import time

import pytest
from test_mm_kinetics import synthetic_database
from desktop import protein_mm as app
from desktop import protein_snapshot as acquisition


def state(path):
    return {p.name:[hashlib.sha256(p.read_bytes()).hexdigest(),p.stat().st_size]
        for p in [path,*[Path(str(path)+x) for x in acquisition.SUFFIXES]] if p.exists()}


@pytest.mark.parametrize('action',['catalog','verify'])
def test_original_wal_connect_race_cannot_create_source_sidecars(synthetic_database,monkeypatch,action):
    store,ids=synthetic_database;connect=sqlite3.connect;events={};targets=[]
    def race(target,*args,**kwargs):
        targets.append(str(target));assert str(store.path) not in str(target)
        if not events:
            writer=connect(store.path);writer.execute('PRAGMA journal_mode=WAL');writer.close()
            events['writer_finished']=state(store.path)
        return connect(target,*args,**kwargs)
    monkeypatch.setattr(app.sqlite3,'connect',race)
    with pytest.raises(ValueError,match='WAL'):
        app.list_saved_rates(store.path) if action=='catalog' else app.verify_selection(store.path,ids)
    assert targets and state(store.path)==events['writer_finished']
    assert len(state(store.path))==1


@pytest.mark.parametrize('kind',['-wal','-shm','-journal','wal_header'])
def test_existing_logs_and_wal_header_are_rejected_without_source_mutation(synthetic_database,kind):
    store,ids=synthetic_database
    if kind=='wal_header':
        db=sqlite3.connect(store.path);db.execute('PRAGMA journal_mode=WAL');db.close()
    else:Path(str(store.path)+kind).write_bytes(b'SYNTHETIC source evidence')
    before=state(store.path)
    with pytest.raises(ValueError):app.verify_selection(store.path,ids)
    assert state(store.path)==before


def test_source_is_only_opened_as_raw_bytes_and_copy_is_private_and_cleaned(synthetic_database,monkeypatch):
    store,ids=synthetic_database;connect=sqlite3.connect;targets=[];folders=[];original=acquisition.tempfile.TemporaryDirectory
    def directory(*a,**k):
        value=original(*a,**k);folders.append(Path(value.name));return value
    def checked(target,*a,**k):
        targets.append(str(target));assert str(store.path) not in str(target)
        assert any(str(folder.as_uri()) in str(target) for folder in folders)
        return connect(target,*a,**k)
    monkeypatch.setattr(acquisition.tempfile,'TemporaryDirectory',directory)
    monkeypatch.setattr(app.sqlite3,'connect',checked)
    before=state(store.path);selection=app.verify_selection(store.path,ids)
    assert len(selection['ids'])==7 and selection['source_strategy']==acquisition.STRATEGY
    assert targets and state(store.path)==before and all(not folder.exists() for folder in folders)
    assert selection['database_sha256']==before[store.path.name][0]


def test_external_sqlite_writer_cannot_change_source_during_capture_lock(synthetic_database):
    store,_=synthetic_database;before=state(store.path)
    program="import sqlite3,sys; db=sqlite3.connect(sys.argv[1],timeout=.01); db.execute('PRAGMA journal_mode=WAL')"
    with acquisition._locked_stream(store.path):
        child=subprocess.run([sys.executable,'-B','-c',program,str(store.path)],capture_output=True,text=True,timeout=10)
        assert child.returncode!=0
    assert state(store.path)==before


def test_committed_wal_from_external_process_is_refused_and_attributed_to_writer(synthetic_database,monkeypatch):
    store,ids=synthetic_database;connect=sqlite3.connect;children=[];writer_state={}
    program="""import sqlite3,sys,json,hashlib
from pathlib import Path
p=Path(sys.argv[1]);db=sqlite3.connect(p);db.execute('PRAGMA journal_mode=WAL')
db.execute('CREATE TABLE synthetic_wal_committed (value TEXT)');db.execute(\"INSERT INTO synthetic_wal_committed VALUES ('COMMITTED')\");db.commit()
files=[p,*[Path(str(p)+s) for s in ('-wal','-shm','-journal')]]
print(json.dumps({q.name:[hashlib.sha256(q.read_bytes()).hexdigest(),q.stat().st_size] for q in files if q.exists()}),flush=True)
sys.stdin.buffer.read(1);db.close()
"""
    def interleaved(target,*a,**k):
        if not children:
            child=subprocess.Popen([sys.executable,'-B','-c',program,str(store.path)],stdin=subprocess.PIPE,stdout=subprocess.PIPE,stderr=subprocess.PIPE,text=True)
            children.append(child);writer_state.update(json.loads(child.stdout.readline()))
            assert store.path.name+'-wal' in writer_state
        return connect(target,*a,**k)
    monkeypatch.setattr(app.sqlite3,'connect',interleaved)
    try:
        with pytest.raises(Exception):app.verify_selection(store.path,ids)
        assert state(store.path)==writer_state
    finally:
        for child in children:child.communicate(input='X',timeout=10)


@pytest.mark.parametrize('change',['truncate','bytes','replace','shm','journal'])
def test_source_change_after_capture_is_rejected_without_reader_side_effects(synthetic_database,monkeypatch,tmp_path,change):
    store,ids=synthetic_database;connect=sqlite3.connect;changed=[];after_writer={}
    def interleaved(target,*a,**k):
        if not changed:
            changed.append(True)
            if change=='truncate':store.path.write_bytes(b'SYNTHETIC_TRUNCATED')
            elif change=='bytes':
                data=bytearray(store.path.read_bytes());data[-1]^=1;store.path.write_bytes(data)
            elif change=='replace':
                replacement=tmp_path/'replacement.sqlite3';replacement.write_bytes(store.path.read_bytes());os.replace(replacement,store.path)
            else:Path(str(store.path)+'-'+change).write_bytes(b'SYNTHETIC writer sidecar')
            after_writer.update(state(store.path))
        return connect(target,*a,**k)
    monkeypatch.setattr(app.sqlite3,'connect',interleaved)
    with pytest.raises(ValueError):app.verify_selection(store.path,ids)
    assert changed and state(store.path)==after_writer


def test_copy_phase_raw_write_is_denied_or_detected_without_silent_success(synthetic_database,monkeypatch):
    store,ids=synthetic_database;native=acquisition._digest;attempts=[]
    def change_during_copy(stream,destination=None):
        if destination is not None and not attempts:
            try:
                with store.path.open('r+b') as writer:writer.seek(-1,2);writer.write(b'X')
                attempts.append('MODIFIED')
            except PermissionError:attempts.append('DENIED')
        return native(stream,destination)
    before=state(store.path);monkeypatch.setattr(acquisition,'_digest',change_during_copy)
    if os.name=='nt':
        value=app.verify_selection(store.path,ids)
        assert attempts==['DENIED'] and len(value['ids'])==7 and state(store.path)==before
    else:
        with pytest.raises(ValueError,match='SOURCE_CHANGED'):app.verify_selection(store.path,ids)
        assert attempts==['MODIFIED']


@pytest.mark.parametrize('kind',['schema','migration','source_bytes','record'])
def test_copy_validation_failure_keeps_original_and_removes_private_copy(synthetic_database,monkeypatch,kind):
    store,ids=synthetic_database
    with sqlite3.connect(store.path) as writer:
        if kind=='schema':writer.execute('PRAGMA user_version=2')
        elif kind=='migration':writer.execute("UPDATE schema_migrations SET sha256='BAD' WHERE version=3")
        elif kind=='source_bytes':writer.execute('DROP TRIGGER source_no_update');writer.execute("UPDATE source_files SET raw_bytes=x'00'")
        else:writer.execute('DROP TRIGGER analysis_no_update');writer.execute("UPDATE initial_rate_analyses SET result_json='{}'")
    writer.close();before=state(store.path);folders=[];original=acquisition.tempfile.TemporaryDirectory
    def directory(*a,**k):value=original(*a,**k);folders.append(Path(value.name));return value
    monkeypatch.setattr(acquisition.tempfile,'TemporaryDirectory',directory)
    with pytest.raises(Exception):app.verify_selection(store.path,ids)
    assert state(store.path)==before and folders and all(not path.exists() for path in folders)


def test_source_native_read_honors_python_audit_rejection_before_open(synthetic_database,monkeypatch):
    store,ids=synthetic_database;before=state(store.path);audit=sys.audit;attempts=[]
    def blocked(event,*args):
        if event=='open' and args[0]==str(store.path):
            attempts.append((args[1],args[2]));raise RuntimeError('SYNTHETIC_AUDIT_BLOCK')
        return audit(event,*args)
    monkeypatch.setattr(sys,'audit',blocked)
    with pytest.raises(RuntimeError,match='SYNTHETIC_AUDIT_BLOCK'):app.verify_selection(store.path,ids)
    assert attempts==[('rb',os.O_RDONLY)] and state(store.path)==before


@pytest.mark.parametrize('suffix',['-wal','-shm','-journal'])
def test_unverifiable_sidecar_permissions_fail_closed(synthetic_database,monkeypatch,suffix):
    store,ids=synthetic_database;original=Path.lstat;before=state(store.path)
    def denied(path,*args,**kwargs):
        if str(path)==str(store.path)+suffix:raise PermissionError('SYNTHETIC sidecar metadata denied')
        return original(path,*args,**kwargs)
    monkeypatch.setattr(Path,'lstat',denied)
    with pytest.raises(ValueError,match='SOURCE_SIDECAR_UNVERIFIABLE'):app.verify_selection(store.path,ids)
    assert state(store.path)==before
