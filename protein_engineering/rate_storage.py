"""SQLite-bound scientific analysis and lossless local snapshot export."""
import base64
from dataclasses import replace
from datetime import datetime, timezone
import hashlib
import json
from pathlib import Path
import uuid

from .initial_rate import Calibration, Observation, RateConfig, analyze_initial_rate, canonical, digest, series_key
from .importer import read_source
from .schema import SPECS


def _observation(record):
    f, p = record["fields"], record["provenance"]
    # Actual acquired source identity; never substitute a provider-reported source_file_id.
    return Observation(f["observation_id"], f["batch_id"], f["sample_id"], f.get("time_value"),
        f.get("raw_signal"), f.get("time_unit"), f.get("signal_unit"), p["import_id"], p["source_sha256"],
        f.get("biological_replicate"), f.get("technical_replicate"), f.get("substrate_concentration"),
        f.get("substrate_concentration_unit"), f.get("well_id"), f.get("blank_signal"))


def _records(connection, kind):
    rows = connection.execute(f"SELECT r.fields_json,r.original_json,r.source_row,i.* FROM {kind} r JOIN imports i ON r.import_id=i.import_id ORDER BY r.rowid")
    return [{"fields": json.loads(r["fields_json"]), "original": json.loads(r["original_json"]),
        "provenance": {k: r[k] for k in ("import_id", "filename", "sheet", "source_row", "source_sha256", "source_kind", "imported_at_utc")}} for r in rows]


def _groups(records):
    groups = {}
    for record in records:
        o = _observation(record)
        key = digest(series_key(o))
        group = groups.setdefault(key, {"series_id": key, "batch_id": o.batch_id, "sample_id": o.sample_id,
            "biological_replicate": o.biological_replicate, "technical_replicate": o.technical_replicate,
            "well_id": o.well_id, "substrate_concentration": o.substrate_concentration,
            "substrate_concentration_unit": o.substrate_concentration_unit, "time_unit": o.time_unit,
            "signal_unit": o.signal_unit, "records": []})
        group["records"].append(record)
    return list(groups.values())


class RateStorage:
    def time_courses(self):
        with self._connection() as connection:
            return _groups(_records(connection, "kinetic_timecourse"))

    def analyze_time_course(self, series_id, config, *, blank_series_id=None, calibration=None):
        groups = {g["series_id"]: g for g in self.time_courses()}
        if series_id not in groups or blank_series_id is not None and blank_series_id not in groups:
            raise ValueError("时间序列不存在，请刷新。")
        raw = [_observation(r) for r in groups[series_id]["records"]]
        blank = [_observation(r) for r in groups[blank_series_id]["records"]] if blank_series_id else []
        with self._connection() as db:
            batch=json.loads(db.execute("SELECT fields_json FROM experiment_batches WHERE batch_id=?",(groups[series_id]["batch_id"],)).fetchone()[0])
        if str(batch.get("assay_type","")).strip().casefold() in {"endpoint","end_point","endpoint_assay","终点","终点测定"}:
            # An explicit endpoint annotation is a veto, never silently relabel it.
            config=replace(config,measurement_kind="ENDPOINT")
        return analyze_initial_rate(raw, config, blanks=blank, calibration=calibration)

    def import_calibration(self, path):
        """Explicit local JSON calibration metadata, retained byte-for-byte. No fitting."""
        raw = read_source(path)
        fields = json.loads(raw.decode("utf-8-sig"))
        sha = hashlib.sha256(raw).hexdigest()
        import_id = "calibration:" + sha
        calibration = Calibration(source_file_id=import_id, source_sha256=sha, **fields)
        # Validate metadata, never fit a calibration model or synthesize measurements.
        from .initial_rate import calibration_parameters
        calibration_parameters(calibration, calibration.signal_unit, calibration.blank_mode)
        with self._connection() as db:
            db.execute("BEGIN IMMEDIATE")
            try:
                stored = db.execute("SELECT raw_bytes FROM source_files WHERE sha256=?", (sha,)).fetchone()
                if stored and bytes(stored[0]) != raw:
                    raise ValueError("标定原件快照损坏")
                if not stored:
                    db.execute("INSERT INTO source_files VALUES(?,?,?)", (sha, raw, len(raw)))
                if not db.execute("SELECT 1 FROM imports WHERE import_id=?", (import_id,)).fetchone():
                    db.execute("INSERT INTO imports VALUES(?,?,?,?,?,?,?,?,?,?)", (import_id, "CALIBRATION", Path(path).name, "JSON", sha,
                        "FILE", datetime.now(timezone.utc).isoformat(), 1, 0, "[]"))
                db.commit()
            except Exception:
                db.rollback(); raise
        return calibration

    def save_initial_rate(self, result):
        """Recalculate from immutable DB inputs; reject tampered/stale/partial results."""
        if result.get("status") != "ESTIMATED":
            raise ValueError("NOT_ESTIMABLE 结果不能保存为速率记录；保留界面诊断。")
        meta = result["analysis_metadata"]
        config = RateConfig(**meta["configuration"])
        calibration = Calibration(**meta["calibration"]) if meta["calibration"] else None
        with self._connection() as db:
            db.execute("BEGIN IMMEDIATE")
            try:
                groups = _groups(_records(db, "kinetic_timecourse"))
                record_map = {r["fields"]["observation_id"]: r for g in groups for r in g["records"]}
                raw_ids = [r["observation_id"] for r in result["raw_observations"]]
                blank_ids = [r["observation_id"] for r in result["blank_observations"]]
                for ids in (raw_ids, blank_ids):
                    if ids and not any(ids == [r["fields"]["observation_id"] for r in g["records"]] for g in groups):
                        raise ValueError("输入必须是完整的已导入重复序列；不能静默删观测。")
                if calibration:
                    source = db.execute("SELECT s.raw_bytes FROM imports i JOIN source_files s ON s.sha256=i.source_sha256 WHERE i.import_id=? AND i.source_sha256=? AND i.kind='CALIBRATION'", (calibration.source_file_id, calibration.source_sha256)).fetchone()
                    if not source or hashlib.sha256(source[0]).hexdigest() != calibration.source_sha256:
                        raise ValueError("标定来源尚未导入或快照损坏")
                    original = Calibration(source_file_id=calibration.source_file_id, source_sha256=calibration.source_sha256,
                                           **json.loads(bytes(source[0]).decode("utf-8-sig")))
                    if original != calibration:
                        raise ValueError("标定元数据与原件不符")
                expected = analyze_initial_rate([_observation(record_map[i]) for i in raw_ids], config,
                    blanks=[_observation(record_map[i]) for i in blank_ids], calibration=calibration,
                    calculated_at=meta["calculated_at_utc"])
                if canonical(expected) != canonical(result):
                    raise ValueError("分析记录与原始观测/配置重算不一致")
                for i in raw_ids + blank_ids:
                    p = record_map[i]["provenance"]
                    source = db.execute("SELECT raw_bytes FROM source_files WHERE sha256=?", (p["source_sha256"],)).fetchone()
                    if not source or hashlib.sha256(source[0]).hexdigest() != p["source_sha256"]:
                        raise ValueError("输入原件 SHA256 校验失败")
                derived = result["derived_initial_rate"]
                analysis_id = uuid.uuid4().hex
                db.execute("INSERT INTO initial_rate_analyses VALUES(?,?,?,?,?,?,?)", (analysis_id, meta["analysis_fingerprint"],
                    derived["batch_id"], derived["sample_id"], meta["analysis_version"], meta["calculated_at_utc"], canonical(result)))
                for role, ids in (("SAMPLE", raw_ids), ("BLANK", blank_ids)):
                    for i in ids:
                        db.execute("INSERT INTO initial_rate_inputs VALUES(?,?,?,?)", (analysis_id, i, role, record_map[i]["provenance"]["source_sha256"]))
                db.commit()
                return analysis_id
            except Exception:
                db.rollback(); raise

    def initial_rate_records(self):
        with self._connection() as db:
            return [{"analysis_id": r[0], "result": json.loads(r[1])} for r in db.execute("SELECT analysis_id,result_json FROM initial_rate_analyses ORDER BY rowid")]

    def export_snapshot(self, path):
        """Explicit private-data export, including original file bytes. Never overwrite."""
        with self._connection() as db:
            db.execute("BEGIN")
            payload = {"format": "protein-engineering-snapshot-1", "schema_version": db.execute("PRAGMA user_version").fetchone()[0],
                "records": {kind: _records(db, kind) for kind in SPECS},
                "sources": [{"sha256": r[0], "raw_base64": base64.b64encode(r[1]).decode("ascii"), "size_bytes": r[2]}
                    for r in db.execute("SELECT sha256,raw_bytes,size_bytes FROM source_files ORDER BY sha256")],
                "imports": [dict(r) for r in db.execute("SELECT * FROM imports ORDER BY import_id")],
                "analyses": [dict(r) for r in db.execute("SELECT * FROM initial_rate_analyses ORDER BY analysis_id")],
                "analysis_inputs": [dict(r) for r in db.execute("SELECT * FROM initial_rate_inputs ORDER BY analysis_id,observation_id")]}
            for source in payload["sources"]:
                if hashlib.sha256(base64.b64decode(source["raw_base64"])).hexdigest() != source["sha256"]:
                    raise ValueError("原件快照损坏；不导出")
        output = {"payload": payload, "payload_sha256": digest(payload)}
        with Path(path).open("x", encoding="utf-8", newline="\n") as stream:
            stream.write(canonical(output) + "\n")
        return {"path": str(path), "payload_sha256": output["payload_sha256"]}
