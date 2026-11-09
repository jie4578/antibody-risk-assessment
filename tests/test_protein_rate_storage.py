"""Synthetic SQLite, scientific identity, provenance and migration integration."""
import base64
from copy import deepcopy
import hashlib
import json
import sqlite3

import pytest

from protein_engineering.initial_rate import RateConfig, digest
from protein_engineering.importer import preview_bytes
from protein_engineering.migrations import APPLICATION_ID, MIGRATIONS, migration_hash
from protein_engineering.models import EnzymeTarget, ProteinVariant, ProteinSample, ExperimentBatch
from protein_engineering.storage import ProteinStore, StorageError


def timecourse_csv(sample="S", prefix="O", biological="BIO1", technical="TECH1", slope=2):
    header="observation_id,batch_id,sample_id,biological_replicate,technical_replicate,well_id,substrate_concentration,substrate_concentration_unit,time_value,time_unit,raw_signal,signal_unit,blank_signal\n"
    return (header+"".join(f"{prefix}{i},B,{sample},{biological},{technical},A1,1,mM,{i},min,{5+slope*i},RFU,0\n" for i in range(5))).encode()


@pytest.fixture
def store(tmp_path):
    result=ProteinStore(tmp_path/"synthetic.sqlite3")
    for record in [EnzymeTarget("T","Synthetic enzyme"),ProteinVariant("V","T","Synthetic WT","WT","ACDEFG"),
                   ProteinSample("S","V",biological_replicate="BIO1"),ExperimentBatch("B","A","timecourse",wt_control_sample_id="S")]:
        result.add(record)
    result.commit_preview(preview_bytes("kinetic_timecourse",timecourse_csv(),"synthetic.csv"))
    return result


def test_old_migration_checksums_unchanged():
    assert migration_hash(MIGRATIONS[0][1])=="694be3e1ffbbdc66550047689601b9fe4b700e31213c14ef13fb9b57ba9afc4c"
    assert migration_hash(MIGRATIONS[1][1])=="8e875c47d5ad0630553656365df4974ececf3aa6de7a7a1e8956bc49c6439e40"


@pytest.mark.parametrize("version", [1,2])
def test_real_legacy_upgrade_retains_raw_data(tmp_path,version):
    path=tmp_path/"legacy.sqlite3"
    with sqlite3.connect(path) as db:
        for n,sql in MIGRATIONS[:version]:
            for statement in sql:
                db.execute(statement)
            db.execute("INSERT INTO schema_migrations VALUES(?,?,?)",(n,migration_hash(sql),"2026-11-09T00:00:00Z"))
        db.execute(f"PRAGMA application_id={APPLICATION_ID}")
        db.execute(f"PRAGMA user_version={version}")
        raw=b'{"synthetic":"legacy"}'
        sha=hashlib.sha256(raw).hexdigest()
        db.execute("INSERT INTO source_files VALUES(?,?,?)",(sha,raw,len(raw)))
        db.execute("INSERT INTO imports VALUES('I','enzyme_targets','legacy.json','MANUAL',?,'MANUAL','2026-11-09T00:00:00Z',1,0,'[]')",(sha,))
        db.execute("INSERT INTO enzyme_targets VALUES('T',?,?, 'I',1)",(json.dumps({"target_id":"T","target_name":"Synthetic"}),json.dumps({"target_id":"T","target_name":"Synthetic"})))
    upgraded=ProteinStore(path)
    assert upgraded.source_bytes(sha)==raw
    assert upgraded.records("enzyme_targets")[0]["fields"]["target_id"]=="T"
    with upgraded._connection() as db:
        assert db.execute("PRAGMA user_version").fetchone()[0]==3
        assert not list(db.execute("PRAGMA foreign_key_check"))
    assert ProteinStore(path).counts()["enzyme_targets"]==1


def test_derived_record_has_separate_table_and_all_original_links(store):
    before=store.records("kinetic_timecourse")
    group=store.time_courses()[0]
    result=store.analyze_time_course(group["series_id"],RateConfig(0,4,"min"))
    identifier=store.save_initial_rate(result)
    assert store.initial_rate_records()==[{"analysis_id":identifier,"result":result}]
    assert store.records("kinetic_timecourse")==before
    with store._connection() as db:
        assert db.execute("SELECT count(*) FROM initial_rate_inputs").fetchone()[0]==5
        assert not list(db.execute("PRAGMA foreign_key_check"))
    with pytest.raises(sqlite3.IntegrityError):
        store.save_initial_rate(result)
    assert len(store.initial_rate_records())==1


@pytest.mark.parametrize("table,key",[("kinetic_timecourse","observation_id"),("samples","sample_id"),
    ("protein_variants","variant_id"),("experiment_batches","batch_id"),("imports","import_id")])
def test_raw_and_identity_cannot_be_updated_or_deleted(store,table,key):
    with store._connection() as db:
        with pytest.raises(sqlite3.IntegrityError,match="immutable"):
            db.execute(f"UPDATE {table} SET {key}='changed'")
        with pytest.raises(sqlite3.IntegrityError,match="immutable"):
            db.execute(f"DELETE FROM {table}")


def test_tampered_and_silently_trimmed_analysis_rejected_atomically(store):
    result=store.analyze_time_course(store.time_courses()[0]["series_id"],RateConfig(0,4,"min"))
    tampered=deepcopy(result);tampered["derived_initial_rate"]["slope"]=999
    with pytest.raises(ValueError,match="不一致"):
        store.save_initial_rate(tampered)
    trimmed=deepcopy(result);trimmed["raw_observations"].pop()
    with pytest.raises(ValueError,match="完整"):
        store.save_initial_rate(trimmed)
    assert store.initial_rate_records()==[]
    with store._connection() as db:
        assert db.execute("SELECT count(*) FROM initial_rate_inputs").fetchone()[0]==0


def test_technical_and_biological_replicates_are_separate_courses(store):
    for i,(bio,tech) in enumerate([("BIO1","TECH2"),("BIO2","TECH1")]):
        store.commit_preview(preview_bytes("kinetic_timecourse",timecourse_csv(prefix=f"R{i}",biological=bio,technical=tech),f"repeat{i}.csv"))
    groups=store.time_courses()
    assert len(groups)==3 and all(len(g["records"])==5 for g in groups)
    for g in groups:
        assert store.analyze_time_course(g["series_id"],RateConfig(0,4,"min"))["derived_initial_rate"]["n"]==5


def test_import_and_save_explicit_calibration_source(store,tmp_path):
    path=tmp_path/"synthetic-calibration.json"
    path.write_text(json.dumps(dict(calibration_id="SYN-CAL",signal_unit="RFU",product_unit="uM",signal_per_product=2,
        intercept=5,valid_signal_min=0,valid_signal_max=100,blank_mode="none")),encoding="utf-8")
    before=path.read_bytes()
    calibration=store.import_calibration(path)
    assert store.source_bytes(calibration.source_sha256)==before
    result=store.analyze_time_course(store.time_courses()[0]["series_id"],RateConfig(0,4,"min"),calibration=calibration)
    assert result["derived_initial_rate"]["product_rate"]["slope"]==1
    store.save_initial_rate(result)
    assert path.read_bytes()==before


def test_export_is_lossless_deterministic_and_never_overwrites(store,tmp_path):
    store.save_initial_rate(store.analyze_time_course(store.time_courses()[0]["series_id"],RateConfig(0,4,"min")))
    a,b=tmp_path/"a.json",tmp_path/"b.json"
    store.export_snapshot(a);store.export_snapshot(b)
    assert a.read_bytes()==b.read_bytes()
    exported=json.loads(a.read_text(encoding="utf-8"))
    p=exported["payload"]
    assert digest(p)==exported["payload_sha256"]
    assert p["records"]["kinetic_timecourse"]==store.records("kinetic_timecourse")
    assert len(p["analyses"])==1 and len(p["analysis_inputs"])==5
    for source in p["sources"]:
        raw=base64.b64decode(source["raw_base64"])
        assert len(raw)==source["size_bytes"] and hashlib.sha256(raw).hexdigest()==source["sha256"]
    with pytest.raises(FileExistsError):
        store.export_snapshot(a)


def test_wt_role_and_cross_target_batch_link_checks(store):
    store.add(ProteinVariant("D","T","Synthetic design","DESIGNED","ACDEFA"))
    store.add(ProteinSample("D-S","D"))
    with pytest.raises(StorageError,match="WT"):
        store.add(ExperimentBatch("BAD","A","timecourse",wt_control_sample_id="D-S"))
    store.add(EnzymeTarget("OTHER-T","Synthetic other target"))
    store.add(ProteinVariant("OTHER-V","OTHER-T","WT","WT","ACDEFT"))
    store.add(ProteinSample("OTHER-S","OTHER-V"))
    before=store.counts()
    with pytest.raises(StorageError,match="不同靶标"):
        store.commit_preview(preview_bytes("kinetic_timecourse",timecourse_csv(sample="OTHER-S",prefix="X"),"wrong-target.csv"))
    assert store.counts()==before


def test_reported_blank_or_correction_requires_signal_unit():
    raw=b'observation_id,batch_id,sample_id,time_value,time_unit,blank_signal\nO,B,S,0,min,0\n'
    preview=preview_bytes("kinetic_timecourse",raw,"blank.csv")
    assert not preview.valid and any(i.code=="UNIT_REQUIRED" for i in preview.issues)


def test_numeric_excel_unit_is_not_interpreted_as_a_unit():
    from protein_engineering.schema import normalize_fields
    _,issues=normalize_fields("kinetic_timecourse",dict(observation_id="SYN-O",batch_id="B",sample_id="S",time_value=0,time_unit="min",raw_signal=0,signal_unit=123))
    assert any(i.code=="TEXT_UNIT_REQUIRED" for i in issues)


def test_declared_endpoint_batch_cannot_be_relabelled_as_timecourse(store):
    store.add(ExperimentBatch("END","A","ENDPOINT"))
    raw=timecourse_csv(prefix="E").replace(b",B,S,",b",END,S,")
    store.commit_preview(preview_bytes("kinetic_timecourse",raw,"endpoint.csv"))
    group=next(g for g in store.time_courses() if g["batch_id"]=="END")
    result=store.analyze_time_course(group["series_id"],RateConfig(0,4,"min"))
    assert result["status"]=="NOT_ESTIMABLE"
    assert any(r["code"]=="NOT_TIME_COURSE" for r in result["reasons"])


def test_analysis_does_not_borrow_provider_corrected_or_product_values(store):
    raw=b'observation_id,batch_id,sample_id,time_value,time_unit,raw_signal,signal_unit,corrected_signal,product_concentration,product_concentration_unit\nX0,B,S,0,min,0,RFU,900,100,uM\nX1,B,S,1,min,2,RFU,900,100,uM\nX2,B,S,2,min,4,RFU,900,100,uM\n'
    # Different well keeps this fixture independent from existing O0..O4.
    raw=raw.replace(b'product_concentration_unit\n',b'product_concentration_unit,well_id\n').replace(b',uM\n',b',uM,A2\n')
    store.commit_preview(preview_bytes("kinetic_timecourse",raw,"reported-values.csv"))
    group=next(g for g in store.time_courses() if g["well_id"]=="A2")
    result=store.analyze_time_course(group["series_id"],RateConfig(0,2,"min"))
    assert result["derived_initial_rate"]["slope"]==2
    assert result["derived_initial_rate"]["product_rate"] is None
