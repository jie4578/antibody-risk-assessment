"""C.2A synthetic-only arithmetic and read-only integration; no AI or real data."""
from copy import deepcopy
from dataclasses import asdict, replace
import hashlib
import json
import math
from types import SimpleNamespace
import sqlite3

import pytest

from protein_engineering.initial_rate import Calibration, Observation, RateConfig, analyze_initial_rate, canonical, digest
from protein_engineering.mm_kinetics import (ALGORITHM_VERSION, CONDITION_FIELDS, FitReview, RateRecord,
    fit_michaelis_menten, input_digest)
from protein_engineering.mm_rate_adapter import ReadOnlyAuditError, load_rate_records

S_VALUES = (2, 5, 10, 20, 40, 80, 160)
STAMP = "2026-11-10T00:00:00Z"
CONDITIONS = dict(protocol_id="SYN-P", protocol_version="1", temperature_c=25, pH=7,
    buffer_composition="synthetic buffer", substrate_name="synthetic substrate", substrate_lot="SYN-LOT",
    cofactor_name="NONE", cofactor_concentration=0, cofactor_concentration_unit="dimensionless",
    enzyme_concentration=0.01, enzyme_concentration_unit="uM", reaction_volume=100,
    reaction_volume_unit="uL", readout_method="SYN-FLUORESCENCE")


def make_record(index, substrate, velocity, *, technical="TECH1", biological="BIO1", coefficient=2,
                calibrated=True, substrate_unit="uM", product_unit="uM", time_unit="min"):
    # Independent theoretical fixture, not the C.2A model implementation.
    observations = [Observation(f"O{index}-{t}", "B", "S", t, 1000 + coefficient * velocity * t,
        time_unit, "RFU", f"SYN-SOURCE-{index}", digest([index, substrate, velocity]), biological, technical,
        substrate, substrate_unit, f"W{index}") for t in (0, 1, 2, 3, 4)]
    calibration = Calibration("SYN-CAL", "SYN-CAL-SOURCE", digest("synthetic calibration"),
        "RFU", product_unit, coefficient, 2000 if coefficient < 0 else 0, -1e10, 1e10, "none") if calibrated else None
    c1 = analyze_initial_rate(observations, RateConfig(0, 4, time_unit), calibration=calibration, calculated_at=STAMP)
    return RateRecord(f"R{index:03}", "V", deepcopy(CONDITIONS), c1, {"source": "SYNTHETIC_FIXTURE_NOT_ACQUIRED"})


def records_for(substrates=S_VALUES, *, rates=None, noise=None, **kwargs):
    # Literal biochemical relation supplies expected rates independently.
    velocities = rates if rates is not None else [5 * s / (20 + s) for s in substrates]
    return [make_record(i, s, v + (noise[i] if noise is not None else 0), **kwargs)
            for i, (s, v) in enumerate(zip(substrates, velocities))]


def review_for(records, **kwargs):
    return replace(FitReview("SYNTHETIC reviewer", STAMP, "Synthetic-only conditional numerical check; not experimental validation",
        input_digest(records), acknowledge_not_established=True), **kwargs)


def run(records, **kwargs):
    return fit_michaelis_menten(records, review_for(records, **kwargs))


def codes(result):
    return {r["code"] for r in result["reasons"] + result["quality_control"]}


def test_noiseless_independent_parameter_recovery_and_residual_statistics():
    result = run(records_for())
    assert result["status"] == "FIT_WITH_LIMITATIONS"
    p = result["parameters"]
    assert p["Km"] == pytest.approx(20, rel=1e-9)
    assert p["Vmax"] == pytest.approx(5, rel=1e-10)
    assert (p["Km_unit"], p["Vmax_unit"]) == ("uM", "uM/min")
    assert result["statistics"]["r_squared"] == pytest.approx(1, abs=1e-14)
    assert result["statistics"]["sse"] < 1e-20
    assert result["metadata"]["algorithm_version"] == ALGORITHM_VERSION
    assert result["metadata"]["initial_rate_validity"] == "NOT_ESTABLISHED"
    for point in result["predictions"]:
        assert point["fitted_rate"] == pytest.approx(5 * point["substrate_concentration"] / (20 + point["substrate_concentration"]), abs=1e-10)


def test_fixed_noise_against_independent_profiled_scalar_solution():
    from scipy.optimize import minimize_scalar
    noise = (0.01, -0.03, 0.02, -0.04, 0.06, -0.02, 0.03)
    y = [5 * s / (20 + s) + e for s, e in zip(S_VALUES, noise)]
    # Eliminate V analytically; independent 1D bounded minimizer, not kernel/Jacobian.
    def profiled(k):
        g = [s / (k + s) for s in S_VALUES]
        v = sum(a * b for a, b in zip(g, y)) / sum(a * a for a in g)
        return sum((b - v * a) ** 2 for a, b in zip(g, y)), v
    ref = minimize_scalar(lambda k: profiled(k)[0], bounds=(10, 40), method="bounded", options={"xatol": 1e-10})
    result = run(records_for(noise=noise))
    p, stats = result["parameters"], result["statistics"]
    assert p["Km"] == pytest.approx(ref.x, rel=1e-7)
    assert p["Vmax"] == pytest.approx(profiled(ref.x)[1], rel=1e-8)
    assert abs(p["Km"] - 20) < 1 and abs(p["Vmax"] - 5) < 0.1
    assert stats["sse"] == pytest.approx(profiled(ref.x)[0], rel=1e-10)
    assert stats["rmse"] == pytest.approx(math.sqrt(stats["sse"] / 7), rel=1e-14)
    assert stats["r_squared"] == pytest.approx(1 - stats["sse"] / sum((v - sum(y)/7)**2 for v in y))


def test_irregular_spacing_and_zero_values_preserved():
    result = run(records_for((0, 1.7, 8.3, 23.2, 71.5, 205)))
    assert result["status"] == "FIT_WITH_LIMITATIONS"
    assert result["parameters"]["Km"] == pytest.approx(20, rel=1e-9)
    assert result["predictions"][0]["observed_rate"] == 0
    assert result["predictions"][0]["fitted_rate"] == 0


@pytest.mark.parametrize("substrates", [(0.001, 0.002, 0.005, 0.01, 0.02, 0.06), (2000, 4000, 8000, 16000, 32000, 80000)])
def test_high_r_squared_does_not_rescue_extreme_coverage(substrates):
    result = run(records_for(substrates))
    assert result["status"] == "NOT_ESTIMABLE" and result["parameters"] is None
    assert "EXTREME_COVERAGE" in codes(result)
    assert result["statistics"]["r_squared"] > 0.99999


def test_narrow_concentration_range_is_explicitly_limited():
    result = run(records_for((20, 20.01, 20.02, 20.03, 20.04, 20.05)))
    assert "NARROW_CONCENTRATION_RANGE" in codes(result)
    assert result["status"] != "VALIDATED"


def test_moderately_low_range_warns_no_saturation():
    result = run(records_for((1, 2, 4, 8, 12, 20)))
    assert result["status"] == "FIT_WITH_LIMITATIONS"
    assert "SATURATION_NOT_COVERED" in codes(result)


def test_technical_duplicates_preserved_but_biological_pooling_rejected():
    records = records_for()
    records.append(make_record(9, 20, 2.6, technical="TECH2"))
    result = run(records)
    assert result["statistics"]["n"] == 8 and len(result["predictions"]) == 8
    assert "TECHNICAL_REPEATS_RETAINED" in codes(result)
    records[-1] = make_record(9, 20, 2.6, biological="BIO2")
    assert "MIXED_CONTEXT" in codes(run(records))


@pytest.mark.parametrize("change", ["duplicate_id", "reused_observations", "missing_replicate", "variant", "conditions", "missing_conditions"])
def test_ambiguous_identity_or_context_rejected(change):
    records = records_for()
    if change == "duplicate_id":
        records.append(records[0])
    elif change == "reused_observations":
        records.append(replace(records[0], analysis_id="NEW"))
    elif change == "missing_replicate":
        records[0] = make_record(0, 2, 0.5, technical="")
    elif change == "variant":
        records[0] = replace(records[0], variant_id="OTHER")
    elif change == "conditions":
        records[0].conditions["pH"] = 8
    else:
        records[0].conditions["pH"] = None
    result = run(records)
    assert result["status"] == "NOT_ESTIMABLE" and result["parameters"] is None


@pytest.mark.parametrize("kwargs", [{"reviewer": ""}, {"rationale": ""}, {"reviewed_at_utc": "2026-11-10"},
    {"direction": "UNKNOWN"}, {"acknowledge_not_established": False}, {"input_sha256": "0" * 64}])
def test_explicit_review_never_upgrades_initial_rate_validity(kwargs):
    result = run(records_for(), **kwargs)
    assert "REVIEW_REQUIRED" in codes(result)
    assert result["metadata"]["initial_rate_validity"] == "NOT_ESTABLISHED"


@pytest.mark.parametrize("kwargs", [{"substrate_unit": "mM"}, {"product_unit": "mM"}, {"time_unit": "s"},
    {"substrate_unit": ""}, {"calibrated": False}])
def test_unit_mixing_and_signal_only_inputs_are_not_product_rates(kwargs):
    records = records_for()
    records[0] = make_record(0, 2, 0.5, **kwargs)
    assert run(records)["status"] == "NOT_ESTIMABLE"


@pytest.mark.parametrize("value", [None, float("nan"), float("inf"), -1, True])
def test_missing_nonfinite_negative_substrate_not_imputed(value):
    records = records_for()
    records[0] = make_record(0, value, 0.5)
    result = run(records)
    assert result["status"] == "NOT_ESTIMABLE" and result["parameters"] is None
    assert len(result["input_records"]) == 7


def test_negative_product_rate_never_absolute_but_negative_reporter_calibration_explicit():
    records = records_for()
    records[0] = make_record(0, 2, -0.5)
    assert run(records)["status"] == "NOT_ESTIMABLE"
    result = run(records_for(coefficient=-2))
    assert result["status"] == "FIT_WITH_LIMITATIONS"
    assert result["parameters"]["Vmax"] == pytest.approx(5, rel=1e-10)
    assert result["input_records"][0]["c1_result"]["derived_initial_rate"]["slope"] < 0


@pytest.mark.parametrize("kind", ["few_rates", "few_concentrations", "zero_rates", "constant_rates"])
def test_insufficient_or_boundary_data_not_reported_as_estimable(kind):
    if kind == "few_rates":
        records = records_for(S_VALUES[:3])
    elif kind == "few_concentrations":
        records = records_for((2, 2, 2, 5, 5, 5))
    else:
        records = records_for(rates=[0 if kind == "zero_rates" else 1] * 7)
    result = run(records)
    assert result["status"] == "NOT_ESTIMABLE" and result["parameters"] is None
    if kind == "constant_rates":
        assert result["statistics"]["r_squared"] is None


@pytest.mark.parametrize("mode", ["exception", "not_converged", "nonfinite", "boundary", "singular"])
def test_optimizer_failure_and_boundary_diagnostics(monkeypatch, mode):
    import scipy.optimize
    import numpy as np
    def fake(*args, **kwargs):
        if mode == "exception":
            raise RuntimeError("synthetic optimizer failure")
        x = np.array([0.0, 0.0])
        if mode == "nonfinite":
            x[0] = float("nan")
        if mode == "boundary":
            x[1] = -math.log(1e8) + 0.01
        return SimpleNamespace(success=mode != "not_converged", status=1, message="SYNTHETIC",
            nfev=1, optimality=0.0, x=x)
    monkeypatch.setattr(scipy.optimize, "least_squares", fake)
    if mode == "singular":
        monkeypatch.setattr(np.linalg, "svd", lambda *a, **k: np.array([1.0, 0.0]))
    result = run(records_for())
    assert result["status"] == "NOT_ESTIMABLE" and result["parameters"] is None
    assert {"exception": "NUMERICAL_FAILURE", "nonfinite": "NUMERICAL_FAILURE",
        "not_converged": "OPTIMIZER_NOT_CONVERGED", "boundary": "PARAMETER_BOUNDARY",
        "singular": "UNIDENTIFIABLE_PARAMETERS"}[mode] in codes(result)


def test_nonmonotonic_rates_retained_no_subset_search():
    result = run(records_for(rates=(0.4, 1.1, 1.7, 3.1, 2.2, 4.1, 4.5)))
    assert "NONMONOTONIC_RATES" in codes(result)
    assert len(result["predictions"]) == 7
    assert result["statistics"]["n"] == 7


@pytest.mark.parametrize("value", [None, float("nan"), float("inf"), True])
def test_missing_or_nonfinite_rate_snapshot_cannot_be_promoted(value):
    records = records_for()
    records[0].c1_result["derived_initial_rate"]["product_rate"]["slope"] = value
    result = run(records)
    assert result["status"] == "NOT_ESTIMABLE" and result["parameters"] is None
    assert result["input_records"][0]["c1_result"]["derived_initial_rate"]["product_rate"]["slope"] is value


@pytest.mark.parametrize("key,value", [("cofactor_concentration", None), ("temperature_c", float("inf")),
    ("enzyme_concentration_unit", "RFU"), ("cofactor_concentration", 1), ("reaction_volume", 0)])
def test_incomplete_or_nonphysical_assay_conditions_rejected(key, value):
    records = records_for()
    records[0].conditions[key] = value
    assert run(records)["status"] == "NOT_ESTIMABLE"


def test_outlier_retained_without_robust_loss_or_best_subset_selection():
    substrates = tuple(range(1, 121, 4))
    y = [5 * s / (20 + s) for s in substrates]
    y[15] += 15
    result = run(records_for(substrates, rates=y))
    assert "LARGE_RESIDUAL" in codes(result)
    assert result["statistics"]["n"] == len(y) and len(result["predictions"]) == len(y)
    assert result["metadata"]["configuration"]["loss"] == "linear"


def test_dependency_absence_is_explicit_not_desktop_import_failure(monkeypatch):
    import builtins
    original = builtins.__import__
    def restricted(name, *args, **kwargs):
        if name == "scipy":
            raise ImportError("SYNTHETIC unavailable dependency")
        return original(name, *args, **kwargs)
    monkeypatch.setattr(builtins, "__import__", restricted)
    assert "DEPENDENCY_UNAVAILABLE" in codes(run(records_for()))


def test_reproducible_hash_fit_no_mutation_and_c1_tampering_detected():
    records = records_for()
    original = deepcopy(records)
    a, b = run(records), run(records)
    assert canonical(a) == canonical(b) and records == original
    assert input_digest(records) == input_digest(reversed(records))
    assert run(list(reversed(records)))["parameters"] == a["parameters"]
    records[0].c1_result["derived_initial_rate"]["product_rate"]["slope"] += 0.01
    assert run(records)["status"] == "NOT_ESTIMABLE"


@pytest.fixture
def synthetic_database(tmp_path):
    from protein_engineering.storage import ProteinStore
    from protein_engineering.models import EnzymeTarget, ProteinVariant, ProteinSample
    from protein_engineering.importer import preview_bytes
    store = ProteinStore(tmp_path / "SYNTHETIC.sqlite3")
    for r in (EnzymeTarget("T", "Synthetic enzyme"), ProteinVariant("V", "T", "Synthetic WT", "WT", "ACDEFG"),
              ProteinSample("S", "V", biological_replicate="BIO1")):
        store.add(r)
    store.add_fields("experiment_batches", {**CONDITIONS, "batch_id": "B", "assay_id": "SYN-A", "assay_type": "timecourse"})
    cal_path = tmp_path / "SYNTHETIC-calibration.json"
    cal_path.write_text(json.dumps(dict(calibration_id="SYN-CAL", signal_unit="RFU", product_unit="uM", signal_per_product=2,
        intercept=0, valid_signal_min=0, valid_signal_max=10000, blank_mode="none")), encoding="utf-8")
    cal = store.import_calibration(cal_path)
    header = "observation_id,batch_id,sample_id,biological_replicate,technical_replicate,well_id,substrate_concentration,substrate_concentration_unit,time_value,time_unit,raw_signal,signal_unit\n"
    raw = header + "".join(f"O{i}-{t},B,S,BIO1,TECH1,W{i},{s},uM,{t},min,{1000+2*(5*s/(20+s))*t},RFU\n"
        for i, s in enumerate(S_VALUES) for t in range(5))
    store.commit_preview(preview_bytes("kinetic_timecourse", raw.encode(), "SYNTHETIC.csv"))
    ids = [store.save_initial_rate(store.analyze_time_course(g["series_id"], RateConfig(0, 4, "min"), calibration=cal))
           for g in store.time_courses()]
    return store, ids


def test_sqlite_adapter_fit_is_read_only_and_lineage_complete(synthetic_database):
    store, ids = synthetic_database
    before = store.path.read_bytes()
    records = load_rate_records(store.path, ids)
    assert store.path.read_bytes() == before
    result = run(records)
    assert result["parameters"]["Km"] == pytest.approx(20, rel=1e-9)
    assert store.path.read_bytes() == before
    assert len(store.initial_rate_records()) == 7
    assert len(records) == 7
    for record in records:
        assert record.provenance["verification"].startswith("SQLITE_V3_READ_ONLY")
        assert len(record.provenance["identity_and_observation_records"]) == 9
        assert len(record.c1_result["analysis_metadata"]["input_sha256"]) == 64
    with store._connection() as db:
        assert db.execute("PRAGMA user_version").fetchone()[0] == 3
        assert len(list(db.execute("SELECT * FROM schema_migrations"))) == 3


@pytest.mark.parametrize("selection", [[], ["missing"], ["duplicate", "duplicate"]])
def test_adapter_explicit_ids_no_silent_selection(synthetic_database, selection):
    store, _ = synthetic_database
    with pytest.raises(ReadOnlyAuditError):
        load_rate_records(store.path, selection)


def test_adapter_missing_database_not_created(tmp_path):
    path = tmp_path / "does-not-exist.sqlite3"
    with pytest.raises(ReadOnlyAuditError):
        load_rate_records(path, ["ID"])
    assert not path.exists()


@pytest.mark.parametrize("version", [1, 2])
def test_adapter_legacy_schema_is_not_migrated(tmp_path, version):
    from protein_engineering.migrations import APPLICATION_ID, MIGRATIONS, migration_hash
    path = tmp_path / "SYNTHETIC-legacy.sqlite3"
    with sqlite3.connect(path) as db:
        for n, statements in MIGRATIONS[:version]:
            for statement in statements:
                db.execute(statement)
            db.execute("INSERT INTO schema_migrations VALUES(?,?,?)", (n, migration_hash(statements), STAMP))
        db.execute(f"PRAGMA application_id={APPLICATION_ID}")
        db.execute(f"PRAGMA user_version={version}")
    before = path.read_bytes()
    with pytest.raises(ReadOnlyAuditError, match="never migrates"):
        load_rate_records(path, ["ID"])
    assert path.read_bytes() == before


@pytest.mark.parametrize("tampering", ["source", "link", "calibration", "sample_identity", "migration", "row_metadata", "raw_condition", "endpoint"])
def test_adapter_rejects_inconsistent_provenance(synthetic_database, tampering):
    store, ids = synthetic_database
    # Deliberate corruption of disposable synthetic fixtures; no real DB opened.
    with store._connection() as db:
        if tampering == "source":
            db.execute("DROP TRIGGER source_no_update")
            db.execute("UPDATE source_files SET raw_bytes=x'00'")
        elif tampering == "link":
            db.execute("DROP TRIGGER analysis_input_no_delete")
            db.execute("DELETE FROM initial_rate_inputs WHERE analysis_id=?", (ids[0],))
        elif tampering == "calibration":
            db.execute("DROP TRIGGER imports_no_update")
            db.execute("UPDATE imports SET kind='OTHER' WHERE kind='CALIBRATION'")
        elif tampering == "sample_identity":
            db.execute("DROP TRIGGER sample_no_update")
            row = db.execute("SELECT fields_json FROM samples").fetchone()
            data = json.loads(row[0]); data["biological_replicate"] = "OTHER"
            db.execute("UPDATE samples SET fields_json=?", (canonical(data),))
        elif tampering == "migration":
            db.execute("UPDATE schema_migrations SET sha256='wrong' WHERE version=3")
        elif tampering == "row_metadata":
            db.execute("DROP TRIGGER analysis_no_update")
            db.execute("UPDATE initial_rate_analyses SET fingerprint='wrong' WHERE analysis_id=?", (ids[0],))
        elif tampering == "endpoint":
            db.execute("DROP TRIGGER batch_no_update")
            row = db.execute("SELECT fields_json FROM experiment_batches").fetchone()
            data = json.loads(row[0]); data["assay_type"] = "endpoint"
            db.execute("UPDATE experiment_batches SET fields_json=?", (canonical(data),))
        else:
            db.execute("DROP TRIGGER timecourse_no_update")
            row = db.execute("SELECT fields_json FROM kinetic_timecourse WHERE observation_id='O0-0'").fetchone()
            data = json.loads(row[0]); data["pH"] = 9
            db.execute("UPDATE kinetic_timecourse SET fields_json=? WHERE observation_id='O0-0'", (canonical(data),))
    before = store.path.read_bytes()
    with pytest.raises(ReadOnlyAuditError):
        load_rate_records(store.path, ids)
    assert store.path.read_bytes() == before


def test_adapter_refuses_sidecar_recovery(synthetic_database):
    store, ids = synthetic_database
    sidecar = store.path.with_name(store.path.name + "-wal")
    sidecar.write_bytes(b"SYNTHETIC")
    with pytest.raises(ReadOnlyAuditError, match="Close/checkpoint"):
        load_rate_records(store.path, ids)
