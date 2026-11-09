"""Immutable versioned SQLite migration snapshots.

Do not derive historical DDL from the current record schema: adding a future
record type must not change the checksum of an already applied migration.
"""
import hashlib

APPLICATION_ID = 1347568974

MIGRATIONS = ((1,
  ('CREATE TABLE schema_migrations (version INTEGER PRIMARY KEY, sha256 TEXT NOT NULL, applied_at_utc TEXT NOT NULL)',
   'CREATE TABLE source_files (sha256 TEXT PRIMARY KEY, raw_bytes BLOB NOT NULL, size_bytes INTEGER NOT NULL)',
   'CREATE TABLE imports (import_id TEXT PRIMARY KEY, kind TEXT NOT NULL, filename TEXT NOT NULL, sheet TEXT NOT NULL, '
   'source_sha256 TEXT NOT NULL REFERENCES source_files(sha256), source_kind TEXT NOT NULL, imported_at_utc TEXT NOT '
   'NULL, row_count INTEGER NOT NULL, blank_rows INTEGER NOT NULL, issues_json TEXT NOT NULL, UNIQUE(kind, '
   'source_sha256, sheet))',
   "CREATE TRIGGER source_no_update BEFORE UPDATE ON source_files BEGIN SELECT RAISE(ABORT, 'source snapshots are "
   "immutable'); END",
   "CREATE TRIGGER source_no_delete BEFORE DELETE ON source_files BEGIN SELECT RAISE(ABORT, 'source snapshots are "
   "immutable'); END",
   'CREATE TABLE enzyme_targets (target_id TEXT PRIMARY KEY NOT NULL, fields_json TEXT NOT NULL, original_json TEXT '
   'NOT NULL, import_id TEXT NOT NULL REFERENCES imports(import_id), source_row INTEGER NOT NULL)',
   'CREATE TABLE protein_variants (variant_id TEXT PRIMARY KEY NOT NULL, target_id TEXT, parent_variant_id TEXT, '
   'reference_variant_id TEXT, sequence_sha256 TEXT NOT NULL, normalized_sequence TEXT NOT NULL, fields_json TEXT NOT '
   'NULL, original_json TEXT NOT NULL, import_id TEXT NOT NULL REFERENCES imports(import_id), source_row INTEGER NOT '
   'NULL, FOREIGN KEY(target_id) REFERENCES enzyme_targets(target_id) DEFERRABLE INITIALLY DEFERRED, FOREIGN '
   'KEY(parent_variant_id) REFERENCES protein_variants(variant_id) DEFERRABLE INITIALLY DEFERRED, FOREIGN '
   'KEY(reference_variant_id) REFERENCES protein_variants(variant_id) DEFERRABLE INITIALLY DEFERRED)',
   'CREATE TABLE samples (sample_id TEXT PRIMARY KEY NOT NULL, variant_id TEXT, fields_json TEXT NOT NULL, '
   'original_json TEXT NOT NULL, import_id TEXT NOT NULL REFERENCES imports(import_id), source_row INTEGER NOT NULL, '
   'FOREIGN KEY(variant_id) REFERENCES protein_variants(variant_id) DEFERRABLE INITIALLY DEFERRED)',
   'CREATE TABLE experiment_batches (batch_id TEXT PRIMARY KEY NOT NULL, wt_control_sample_id TEXT, fields_json TEXT '
   'NOT NULL, original_json TEXT NOT NULL, import_id TEXT NOT NULL REFERENCES imports(import_id), source_row INTEGER '
   'NOT NULL, FOREIGN KEY(wt_control_sample_id) REFERENCES samples(sample_id) DEFERRABLE INITIALLY DEFERRED)',
   'CREATE TABLE assay_results (result_id TEXT PRIMARY KEY NOT NULL, batch_id TEXT, sample_id TEXT, fields_json TEXT '
   'NOT NULL, original_json TEXT NOT NULL, import_id TEXT NOT NULL REFERENCES imports(import_id), source_row INTEGER '
   'NOT NULL, FOREIGN KEY(batch_id) REFERENCES experiment_batches(batch_id) DEFERRABLE INITIALLY DEFERRED, FOREIGN '
   'KEY(sample_id) REFERENCES samples(sample_id) DEFERRABLE INITIALLY DEFERRED)',
   'CREATE TABLE kinetic_timecourse (observation_id TEXT PRIMARY KEY NOT NULL, batch_id TEXT, sample_id TEXT, '
   'fields_json TEXT NOT NULL, original_json TEXT NOT NULL, import_id TEXT NOT NULL REFERENCES imports(import_id), '
   'source_row INTEGER NOT NULL, FOREIGN KEY(batch_id) REFERENCES experiment_batches(batch_id) DEFERRABLE INITIALLY '
   'DEFERRED, FOREIGN KEY(sample_id) REFERENCES samples(sample_id) DEFERRABLE INITIALLY DEFERRED)',
   'CREATE TABLE ai_predictions (prediction_id TEXT PRIMARY KEY NOT NULL, variant_id TEXT, fields_json TEXT NOT NULL, '
   'original_json TEXT NOT NULL, import_id TEXT NOT NULL REFERENCES imports(import_id), source_row INTEGER NOT NULL, '
   'FOREIGN KEY(variant_id) REFERENCES protein_variants(variant_id) DEFERRABLE INITIALLY DEFERRED)',
   'CREATE TABLE structure_assets (structure_id TEXT PRIMARY KEY NOT NULL, variant_id TEXT, fields_json TEXT NOT NULL, '
   'original_json TEXT NOT NULL, import_id TEXT NOT NULL REFERENCES imports(import_id), source_row INTEGER NOT NULL, '
   'FOREIGN KEY(variant_id) REFERENCES protein_variants(variant_id) DEFERRABLE INITIALLY DEFERRED)',
   'CREATE TABLE source_manifest (source_file_id TEXT PRIMARY KEY NOT NULL, fields_json TEXT NOT NULL, original_json '
   'TEXT NOT NULL, import_id TEXT NOT NULL REFERENCES imports(import_id), source_row INTEGER NOT NULL)')),
 (2,
  ('CREATE INDEX variant_sequence_hash ON protein_variants(sequence_sha256)',
   'CREATE INDEX sample_variant ON samples(variant_id)',
   'CREATE INDEX measured_sample ON assay_results(sample_id)',
   'CREATE INDEX predicted_variant ON ai_predictions(variant_id)')),
 (3,
  ('CREATE TABLE initial_rate_analyses (analysis_id TEXT PRIMARY KEY NOT NULL, fingerprint TEXT NOT NULL UNIQUE, batch_id TEXT NOT NULL REFERENCES experiment_batches(batch_id), sample_id TEXT NOT NULL REFERENCES samples(sample_id), analysis_version TEXT NOT NULL, calculated_at_utc TEXT NOT NULL, result_json TEXT NOT NULL)',
   'CREATE TABLE initial_rate_inputs (analysis_id TEXT NOT NULL REFERENCES initial_rate_analyses(analysis_id), observation_id TEXT NOT NULL REFERENCES kinetic_timecourse(observation_id), input_role TEXT NOT NULL CHECK(input_role IN (\'SAMPLE\',\'BLANK\')), source_sha256 TEXT NOT NULL REFERENCES source_files(sha256), PRIMARY KEY(analysis_id, observation_id))',
   "CREATE TRIGGER imports_no_update BEFORE UPDATE ON imports BEGIN SELECT RAISE(ABORT, 'raw provenance is immutable'); END",
   "CREATE TRIGGER imports_no_delete BEFORE DELETE ON imports BEGIN SELECT RAISE(ABORT, 'raw provenance is immutable'); END",
   "CREATE TRIGGER target_no_update BEFORE UPDATE ON enzyme_targets BEGIN SELECT RAISE(ABORT, 'source records are immutable'); END",
   "CREATE TRIGGER target_no_delete BEFORE DELETE ON enzyme_targets BEGIN SELECT RAISE(ABORT, 'source records are immutable'); END",
   "CREATE TRIGGER variant_no_update BEFORE UPDATE ON protein_variants BEGIN SELECT RAISE(ABORT, 'source records are immutable'); END",
   "CREATE TRIGGER variant_no_delete BEFORE DELETE ON protein_variants BEGIN SELECT RAISE(ABORT, 'source records are immutable'); END",
   "CREATE TRIGGER sample_no_update BEFORE UPDATE ON samples BEGIN SELECT RAISE(ABORT, 'source records are immutable'); END",
   "CREATE TRIGGER sample_no_delete BEFORE DELETE ON samples BEGIN SELECT RAISE(ABORT, 'source records are immutable'); END",
   "CREATE TRIGGER batch_no_update BEFORE UPDATE ON experiment_batches BEGIN SELECT RAISE(ABORT, 'source records are immutable'); END",
   "CREATE TRIGGER batch_no_delete BEFORE DELETE ON experiment_batches BEGIN SELECT RAISE(ABORT, 'source records are immutable'); END",
   "CREATE TRIGGER assay_no_update BEFORE UPDATE ON assay_results BEGIN SELECT RAISE(ABORT, 'raw observations are immutable'); END",
   "CREATE TRIGGER assay_no_delete BEFORE DELETE ON assay_results BEGIN SELECT RAISE(ABORT, 'raw observations are immutable'); END",
   "CREATE TRIGGER timecourse_no_update BEFORE UPDATE ON kinetic_timecourse BEGIN SELECT RAISE(ABORT, 'raw observations are immutable'); END",
   "CREATE TRIGGER timecourse_no_delete BEFORE DELETE ON kinetic_timecourse BEGIN SELECT RAISE(ABORT, 'raw observations are immutable'); END",
   "CREATE TRIGGER prediction_no_update BEFORE UPDATE ON ai_predictions BEGIN SELECT RAISE(ABORT, 'reported predictions are immutable'); END",
   "CREATE TRIGGER prediction_no_delete BEFORE DELETE ON ai_predictions BEGIN SELECT RAISE(ABORT, 'reported predictions are immutable'); END",
   "CREATE TRIGGER structure_no_update BEFORE UPDATE ON structure_assets BEGIN SELECT RAISE(ABORT, 'source records are immutable'); END",
   "CREATE TRIGGER structure_no_delete BEFORE DELETE ON structure_assets BEGIN SELECT RAISE(ABORT, 'source records are immutable'); END",
   "CREATE TRIGGER manifest_no_update BEFORE UPDATE ON source_manifest BEGIN SELECT RAISE(ABORT, 'source records are immutable'); END",
   "CREATE TRIGGER manifest_no_delete BEFORE DELETE ON source_manifest BEGIN SELECT RAISE(ABORT, 'source records are immutable'); END",
   "CREATE TRIGGER analysis_no_update BEFORE UPDATE ON initial_rate_analyses BEGIN SELECT RAISE(ABORT, 'derived analyses are immutable'); END",
   "CREATE TRIGGER analysis_no_delete BEFORE DELETE ON initial_rate_analyses BEGIN SELECT RAISE(ABORT, 'derived analyses are immutable'); END",
   "CREATE TRIGGER analysis_input_no_update BEFORE UPDATE ON initial_rate_inputs BEGIN SELECT RAISE(ABORT, 'analysis links are immutable'); END",
   "CREATE TRIGGER analysis_input_no_delete BEFORE DELETE ON initial_rate_inputs BEGIN SELECT RAISE(ABORT, 'analysis links are immutable'); END")))


def migration_hash(statements):
    return hashlib.sha256("\n".join(statements).encode("utf-8")).hexdigest()
