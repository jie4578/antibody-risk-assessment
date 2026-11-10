"""Explicit v3 SQLite -> immutable C.2A snapshots. No migrations or writes."""
from contextlib import closing
from dataclasses import asdict
import hashlib
import json
from pathlib import Path
import sqlite3

from .initial_rate import Calibration, canonical
from .migrations import APPLICATION_ID, MIGRATIONS, migration_hash
from .mm_kinetics import CONDITION_FIELDS, RateRecord, verify_c1_result
from .rate_storage import _observation


class ReadOnlyAuditError(ValueError):
    """Selection/provenance failure; no records are silently dropped."""


def load_rate_records(path, analysis_ids):
    """Read only explicit IDs from an existing local v3 database.

    Does not construct ProteinStore (its constructor migrates). All original
    sample/blank links, calibration bytes and identity-source hashes are checked.
    Input file hashes alone are not tamper-proof experimental authentication.
    """
    identifiers = tuple(analysis_ids)
    if not identifiers or any(not isinstance(i, str) or not i.strip() for i in identifiers) or len(set(identifiers)) != len(identifiers):
        raise ReadOnlyAuditError("Explicit unique analysis IDs are required")
    database = Path(path).resolve()
    if str(path).startswith(("\\\\", "//")) or not database.is_file():
        raise ReadOnlyAuditError("An existing explicit local database is required; nothing is created")
    # Avoid hot-journal recovery or WAL shared-memory creation on this audit path.
    if any(Path(str(database) + suffix).exists() for suffix in ("-journal", "-wal", "-shm")):
        raise ReadOnlyAuditError("Close/checkpoint the database before this offline read-only audit")
    try:
        with closing(sqlite3.connect(database.as_uri() + "?mode=ro", uri=True)) as db:
            db.row_factory = sqlite3.Row
            db.execute("PRAGMA query_only=ON")
            db.execute("BEGIN")
            if db.execute("PRAGMA application_id").fetchone()[0] != APPLICATION_ID or db.execute("PRAGMA user_version").fetchone()[0] != 3:
                raise ReadOnlyAuditError("Expected Protein Engineering schema v3; adapter never migrates v1/v2")
            history = [tuple(r) for r in db.execute("SELECT version,sha256 FROM schema_migrations ORDER BY version")]
            if history != [(v, migration_hash(sql)) for v, sql in MIGRATIONS]:
                raise ReadOnlyAuditError("Migration history mismatch")

            def source(import_id):
                row = db.execute("SELECT i.*,s.raw_bytes,s.size_bytes FROM imports i JOIN source_files s ON s.sha256=i.source_sha256 WHERE i.import_id=?", (import_id,)).fetchone()
                if row is None or len(row["raw_bytes"]) != row["size_bytes"] or hashlib.sha256(row["raw_bytes"]).hexdigest() != row["source_sha256"]:
                    raise ReadOnlyAuditError("Acquired source bytes/SHA256 mismatch")
                return row

            # Only names below are interpolated; all user IDs use SQL parameters.
            def record(kind, key, value):
                row = db.execute(f"SELECT * FROM {kind} WHERE {key}=?", (value,)).fetchone()
                if row is None:
                    raise ReadOnlyAuditError("Missing referenced " + kind + ": " + value)
                s = source(row["import_id"])
                fields = json.loads(row["fields_json"])
                if fields[key] != value:
                    raise ReadOnlyAuditError("Identity column and JSON disagree")
                snapshot = {"fields": fields, "original": json.loads(row["original_json"]),
                    "provenance": {k: s[k] for k in ("import_id", "filename", "sheet", "source_sha256", "source_kind", "imported_at_utc")}}
                snapshot["provenance"]["source_row"] = row["source_row"]
                return row, snapshot

            result = []
            for identifier in identifiers:
                row = db.execute("SELECT * FROM initial_rate_analyses WHERE analysis_id=?", (identifier,)).fetchone()
                if row is None:
                    raise ReadOnlyAuditError("Missing analysis_id: " + identifier)
                c1 = json.loads(row["result_json"])
                verify_c1_result(c1)
                meta, d = c1["analysis_metadata"], c1["derived_initial_rate"]
                if (row["fingerprint"], row["analysis_version"], row["calculated_at_utc"], row["sample_id"], row["batch_id"]) != (
                    meta["analysis_fingerprint"], meta["analysis_version"], meta["calculated_at_utc"], d["sample_id"], d["batch_id"]):
                    raise ReadOnlyAuditError("C.1 row metadata mismatch")
                sample, sample_snapshot = record("samples", "sample_id", d["sample_id"])
                variant, variant_snapshot = record("protein_variants", "variant_id", sample["variant_id"])
                _, batch_snapshot = record("experiment_batches", "batch_id", d["batch_id"])
                target, target_snapshot = record("enzyme_targets", "target_id", variant["target_id"])
                del target
                if sample_snapshot["fields"].get("variant_id") != variant["variant_id"] or variant_snapshot["fields"].get("target_id") != variant["target_id"]:
                    raise ReadOnlyAuditError("Variant identity linkage mismatch")
                bio = sample_snapshot["fields"].get("biological_replicate")
                if bio != d["biological_replicate"]:
                    raise ReadOnlyAuditError("Sample and time-course biological identities disagree or are absent")
                conditions = {k: batch_snapshot["fields"].get(k) for k in CONDITION_FIELDS}
                if str(batch_snapshot["fields"].get("assay_type", "")).casefold() not in {"timecourse", "time_course", "time course", "时间序列"}:
                    raise ReadOnlyAuditError("An explicitly documented time-course batch is required")
                lineage = [sample_snapshot, variant_snapshot, target_snapshot, batch_snapshot]
                expected_links = []
                for role, observations in (("SAMPLE", c1["raw_observations"]), ("BLANK", c1["blank_observations"])):
                    for observation in observations:
                        _, snapshot = record("kinetic_timecourse", "observation_id", observation["observation_id"])
                        if canonical(asdict(_observation(snapshot))) != canonical(observation):
                            raise ReadOnlyAuditError("C.1 observation snapshot disagrees with original row")
                        if role == "SAMPLE":
                            for k in CONDITION_FIELDS:
                                supplied = snapshot["fields"].get(k)
                                if supplied is not None and canonical(supplied) != canonical(conditions[k]):
                                    raise ReadOnlyAuditError("Per-observation assay condition contradicts batch: " + k)
                        expected_links.append((observation["observation_id"], role, observation["source_sha256"]))
                        lineage.append(snapshot)
                links = [tuple(r) for r in db.execute("SELECT observation_id,input_role,source_sha256 FROM initial_rate_inputs WHERE analysis_id=? ORDER BY observation_id", (identifier,))]
                if sorted(expected_links) != links:
                    raise ReadOnlyAuditError("Missing/extra/changed C.1 input links")
                cal = Calibration(**meta["calibration"])
                s = source(cal.source_file_id)
                if s["kind"] != "CALIBRATION" or s["source_sha256"] != cal.source_sha256 or Calibration(
                    source_file_id=cal.source_file_id, source_sha256=cal.source_sha256,
                    **json.loads(bytes(s["raw_bytes"]).decode("utf-8-sig"))) != cal:
                    raise ReadOnlyAuditError("Calibration differs from acquired source")
                provenance = {"verification": "SQLITE_V3_READ_ONLY_BYTE_HASH_AND_C1_REPLAY",
                    "identity_and_observation_records": lineage,
                    "calibration_source": {k: s[k] for k in ("import_id", "filename", "source_sha256", "imported_at_utc")}}
                result.append(RateRecord(identifier, variant["variant_id"], conditions, c1, provenance))
            return tuple(result)
    except (sqlite3.Error, KeyError, TypeError, ValueError) as exc:
        if isinstance(exc, ReadOnlyAuditError):
            raise
        raise ReadOnlyAuditError(str(exc)) from exc
