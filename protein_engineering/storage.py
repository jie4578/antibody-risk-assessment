"""Append-only local records with atomic imports and immutable source snapshots."""
from contextlib import contextmanager
from dataclasses import asdict
from datetime import datetime, timezone
from pathlib import Path
import hashlib
import json
import os
import sqlite3
import uuid

from . import SCHEMA_VERSION
from .importer import ImportPreview, SourceRow, preview_bytes, read_source
from .migrations import APPLICATION_ID, MIGRATIONS, migration_hash
from .models import record_fields
from .schema import Issue, SPECS, normalize_fields
from .rate_storage import RateStorage


class StorageError(ValueError):
    pass


def _json(value):
    return json.dumps(value, ensure_ascii=False, sort_keys=True, allow_nan=False)


def _now():
    return datetime.now(timezone.utc).isoformat()


def default_database_path():
    root = os.environ.get("PROTEIN_ENGINEERING_DATA_DIR")
    if root:
        return Path(root) / "research.sqlite3"
    local = os.environ.get("LOCALAPPDATA")
    root = Path(local) if local else Path.home() / ".local/share"
    return root / "AntibodyResearchWorkbench/protein_engineering/research.sqlite3"


class ProteinStore(RateStorage):
    def __init__(self, path):
        if str(path).startswith(("\\\\", "//")):
            raise StorageError("SQLite 数据库需要本地路径，不在网络共享上创建数据库")
        self.path = Path(path).resolve()
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self._migrate()

    @contextmanager
    def _connection(self):
        connection = sqlite3.connect(self.path, timeout=5, isolation_level=None)
        connection.row_factory = sqlite3.Row
        connection.execute("PRAGMA foreign_keys=ON")
        try:
            yield connection
        finally:
            connection.close()

    def _migrate(self):
        with self._connection() as connection:
            connection.execute("BEGIN IMMEDIATE")
            try:
                tables = {row[0] for row in connection.execute("SELECT name FROM sqlite_master WHERE type='table'")}
                objects = {row[0] for row in connection.execute("SELECT name FROM sqlite_master WHERE name NOT LIKE 'sqlite_%'")}
                app_id = connection.execute("PRAGMA application_id").fetchone()[0]
                version = connection.execute("PRAGMA user_version").fetchone()[0]
                if objects and (app_id != APPLICATION_ID or "schema_migrations" not in tables):
                    raise StorageError("不是本模块数据库；拒绝向现有其他数据库写入")
                if not 0 <= version <= SCHEMA_VERSION or app_id not in {0, APPLICATION_ID}:
                    raise StorageError("数据库版本/应用标识不受支持，不执行降级")
                history = dict(connection.execute("SELECT version, sha256 FROM schema_migrations")) if tables else {}
                if set(history) != set(range(1, version + 1)):
                    raise StorageError("数据库迁移历史不完整")
                for number, statements in MIGRATIONS:
                    expected = migration_hash(statements)
                    if number <= version:
                        if history.get(number) != expected:
                            raise StorageError("迁移定义摘要不匹配；需要人工审查，不能静默改写")
                        continue
                    for statement in statements:
                        connection.execute(statement)
                    connection.execute("INSERT INTO schema_migrations VALUES(?,?,?)", (number, expected, _now()))
                    connection.execute(f"PRAGMA user_version={number}")
                connection.execute(f"PRAGMA application_id={APPLICATION_ID}")
                connection.commit()
            except Exception:
                connection.rollback()
                raise

    def _reference_issues(self, connection, preview):
        issues = []
        spec = SPECS[preview.kind]
        local = {r.fields[spec.id_field]: r.fields for r in preview.rows}
        existing = {row[0] for row in connection.execute(f"SELECT {spec.id_field} FROM {preview.kind}")}
        for row in preview.rows:
            fields = row.fields
            if fields[spec.id_field] in existing:
                issues.append(Issue(row.source_row, spec.id_field, "EXISTING_ID", "ID 已存在；不会覆盖旧记录"))
            for key, target in spec.references:
                value = fields.get(key)
                if value is None:
                    continue
                related = local.get(value) if target == preview.kind else None
                if related is None:
                    found = connection.execute(f"SELECT fields_json FROM {target} WHERE {SPECS[target].id_field}=?", (value,)).fetchone()
                    related = json.loads(found[0]) if found else None
                if related is None:
                    issues.append(Issue(row.source_row, key, "MISSING_REFERENCE", "引用的 " + target + " ID 不存在；请先导入关联记录"))
                elif preview.kind == "protein_variants" and key in {"parent_variant_id", "reference_variant_id"}:
                    if related.get("target_id") != fields.get("target_id"):
                        issues.append(Issue(row.source_row, key, "CROSS_TARGET", "亲本/参考变体必须属于同一靶标"))
            if preview.kind == "protein_variants":
                seen, current = set(), fields
                while current is not None:
                    key = current["variant_id"]
                    if key in seen:
                        issues.append(Issue(row.source_row, "parent_variant_id", "PARENT_CYCLE", "亲本关系形成循环"))
                        break
                    seen.add(key)
                    parent = current.get("parent_variant_id")
                    if parent is None:
                        break
                    current = local.get(parent)
                    if current is None:
                        found = connection.execute("SELECT fields_json FROM protein_variants WHERE variant_id=?", (parent,)).fetchone()
                        current = json.loads(found[0]) if found else None
            if preview.kind == "experiment_batches" and fields.get("wt_control_sample_id"):
                found = connection.execute("SELECT v.fields_json FROM samples s JOIN protein_variants v ON v.variant_id=s.variant_id WHERE s.sample_id=?", (fields["wt_control_sample_id"],)).fetchone()
                if found and json.loads(found[0]).get("variant_role") != "WT":
                    issues.append(Issue(row.source_row, "wt_control_sample_id", "NOT_WT_CONTROL", "WT 对照样品必须关联显式 WT 变体；不根据名称推断"))
            if preview.kind in {"assay_results", "kinetic_timecourse"}:
                targets = connection.execute("SELECT v.target_id FROM samples s JOIN protein_variants v ON v.variant_id=s.variant_id WHERE s.sample_id IN (?, (SELECT wt_control_sample_id FROM experiment_batches WHERE batch_id=?))", (fields.get("sample_id"), fields.get("batch_id"))).fetchall()
                if len({r[0] for r in targets}) > 1:
                    issues.append(Issue(row.source_row, "sample_id", "CROSS_TARGET_BATCH", "观测样品与批次 WT 对照属于不同靶标"))
        return issues

    def _revalidate(self, preview):
        if hashlib.sha256(preview.raw_bytes).hexdigest() != preview.sha256:
            raise StorageError("预览原件摘要不匹配")
        if preview.source_path is not None and hashlib.sha256(read_source(preview.source_path)).hexdigest() != preview.sha256:
            raise StorageError("源文件在预览后发生变化；请重新预览，未写入任何记录")
        if preview.source_kind == "FILE":
            # Ignore caller-mutated dictionaries: reparse the retained raw bytes.
            return preview_bytes(preview.kind, preview.raw_bytes, preview.filename, preview.sheet)
        if preview.source_kind != "MANUAL":
            raise StorageError("未知来源类型")
        original = json.loads(preview.raw_bytes)
        fields, issues = normalize_fields(preview.kind, original)
        return ImportPreview(preview.kind, preview.filename, preview.sheet, preview.sha256, preview.raw_bytes,
                             tuple(original), (SourceRow(1, original, fields),), tuple(issues), source_kind="MANUAL")

    def commit_preview(self, preview):
        preview = self._revalidate(preview)
        if not preview.valid:
            errors = [f"row {i.row} {i.field}: {i.message}" for i in preview.issues if i.severity == "ERROR"]
            raise StorageError("导入校验失败；整批未写入：\n" + "\n".join(errors))
        with self._connection() as connection:
            connection.execute("BEGIN IMMEDIATE")
            try:
                if connection.execute("SELECT 1 FROM imports WHERE kind=? AND source_sha256=? AND sheet=?",
                                      (preview.kind, preview.sha256, preview.sheet)).fetchone():
                    raise StorageError("该类型/工作表/原件已导入；不会重复写入或静默去重")
                issues = list(preview.issues) + self._reference_issues(connection, preview)
                errors = [i for i in issues if i.severity == "ERROR"]
                if errors:
                    raise StorageError("关联校验失败；整批未写入：\n" + "\n".join(f"row {i.row} {i.field}: {i.message}" for i in errors))
                import_id = uuid.uuid4().hex
                stored = connection.execute("SELECT raw_bytes FROM source_files WHERE sha256=?", (preview.sha256,)).fetchone()
                if stored is not None and bytes(stored[0]) != preview.raw_bytes:
                    raise StorageError("已有来源快照损坏，拒绝覆盖")
                if stored is None:
                    connection.execute("INSERT INTO source_files VALUES(?,?,?)", (preview.sha256, preview.raw_bytes, len(preview.raw_bytes)))
                connection.execute("INSERT INTO imports VALUES(?,?,?,?,?,?,?,?,?,?)",
                    (import_id, preview.kind, preview.filename, preview.sheet, preview.sha256, preview.source_kind,
                     _now(), len(preview.rows), preview.blank_rows, _json([asdict(i) for i in issues])))
                spec = SPECS[preview.kind]
                keys = [spec.id_field, *(key for key, _ in spec.references)]
                if preview.kind == "protein_variants":
                    keys += ["sequence_sha256", "normalized_sequence"]
                keys += ["fields_json", "original_json", "import_id", "source_row"]
                sql = f"INSERT INTO {preview.kind} (" + ",".join(keys) + ") VALUES (" + ",".join("?" for _ in keys) + ")"
                for row in preview.rows:
                    values = [row.fields[spec.id_field], *(row.fields.get(key) for key, _ in spec.references)]
                    if preview.kind == "protein_variants":
                        values += [row.fields["sequence_sha256"], row.fields["sequence"]]
                    values += [_json(row.fields), _json(row.original), import_id, row.source_row]
                    connection.execute(sql, values)
                connection.commit()
                return {"import_id": import_id, "kind": preview.kind, "rows": len(preview.rows), "source_sha256": preview.sha256,
                        "blank_rows": preview.blank_rows, "warnings": [asdict(i) for i in issues if i.severity == "WARNING"]}
            except sqlite3.Error as exc:
                connection.rollback()
                raise StorageError("数据库写入失败，事务已回滚：" + str(exc)) from exc
            except Exception:
                connection.rollback()
                raise

    def add(self, record):
        kind, fields = record_fields(record)
        return self.add_fields(kind, fields)

    def add_fields(self, kind, original):
        if kind not in {"enzyme_targets", "protein_variants", "samples", "experiment_batches"}:
            raise StorageError("手工建档仅支持靶标、变体、样品和批次")
        raw = _json(original).encode("utf-8")
        fields, issues = normalize_fields(kind, original)
        preview = ImportPreview(kind, "manual-entry.json", "MANUAL", hashlib.sha256(raw).hexdigest(), raw,
                                tuple(original), (SourceRow(1, original, fields),), tuple(issues), source_kind="MANUAL")
        return self.commit_preview(preview)

    def counts(self):
        with self._connection() as connection:
            return {kind: connection.execute(f"SELECT count(*) FROM {kind}").fetchone()[0] for kind in SPECS}

    def records(self, kind, limit=500):
        if kind not in SPECS:
            raise StorageError("未知记录类型")
        if not 1 <= limit <= 10_000:
            raise StorageError("无效的显示条数")
        with self._connection() as connection:
            rows = connection.execute(f"SELECT r.fields_json,r.original_json,r.source_row,i.* FROM {kind} r JOIN imports i ON r.import_id=i.import_id ORDER BY r.rowid LIMIT ?", (limit,)).fetchall()
            return [{"fields": json.loads(r["fields_json"]), "original": json.loads(r["original_json"]),
                     "provenance": {key: r[key] for key in ("import_id", "filename", "sheet", "source_row", "source_sha256", "source_kind", "imported_at_utc")}}
                    for r in rows]

    def source_bytes(self, sha256):
        with self._connection() as connection:
            row = connection.execute("SELECT raw_bytes FROM source_files WHERE sha256=?", (sha256,)).fetchone()
        if row is None:
            raise StorageError("来源不存在")
        data = bytes(row[0])
        if hashlib.sha256(data).hexdigest() != sha256:
            raise StorageError("来源快照完整性检查失败")
        return data

    def sequence_audit(self):
        with self._connection() as connection:
            total, unique = connection.execute("SELECT count(*),count(DISTINCT sequence_sha256) FROM protein_variants").fetchone()
            groups = [dict(row) for row in connection.execute("SELECT sequence_sha256,count(*) AS records FROM protein_variants GROUP BY sequence_sha256 HAVING count(*)>1 ORDER BY sequence_sha256")]
            return {"records": total, "unique_sequences": unique, "duplicate_groups": groups}

    def unresolved_target_references(self):
        # Target -> reference variant is an intentionally deferred metadata link:
        # targets must be created before their first variant can be imported.
        with self._connection() as connection:
            result = []
            for record in connection.execute("SELECT fields_json FROM enzyme_targets"):
                fields = json.loads(record[0])
                reference = fields.get("reference_sequence_variant_id")
                if reference:
                    row = connection.execute("SELECT target_id FROM protein_variants WHERE variant_id=?", (reference,)).fetchone()
                    if row is None or row[0] != fields["target_id"]:
                        result.append({"target_id": fields["target_id"], "reference_variant_id": reference, "status": "UNRESOLVED_OR_CROSS_TARGET"})
            return result
