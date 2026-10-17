import os
import hashlib

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

import pytest

pytest.importorskip("PySide6")
from PySide6.QtWidgets import QApplication
from core import CURRENT_RULE_VERSION, FROZEN_RULE_VERSION, analyze_sequence
from desktop.batch_adapter import BatchRecord, BatchResult
from desktop.mutation_adapter import compare_mutation
from desktop.widgets.batch_analysis import BatchAnalysisPage
from desktop.widgets.mutation import MutationPage
from desktop.research_summary import build_research_summary
from desktop.research_copilot import build_copilot_context, validate_copilot_response

VH = "EVQLVESGGGLVQPGGSLRLSCAASGFNIKDTYIHWVRQAPGKGLEWVARIYPTNGYTRYADSVKGRFTISADTSKNTAYLQMNSLRAEDTAVYYCSRWGGDGFYAMDYWGQGTLVTVSS"


@pytest.fixture
def app():
    return QApplication.instance() or QApplication([])


def test_overlapping_sequons_are_versioned():
    args = (31, 35, 50, 65, 99, 110)
    new = analyze_sequence("NNST", *args)
    old = analyze_sequence("NNST", *args, rule_version=FROZEN_RULE_VERSION)
    assert [(r.motif, r.position) for r in new.risks if r.category == "N-糖基化"] == [("NNS", "1-3"), ("NST", "2-4")]
    assert [(r.motif, r.position) for r in old.risks if r.category == "N-糖基化"] == [("NNS", "1-3")]
    assert new.metadata["rule_version"] == CURRENT_RULE_VERSION
    with pytest.raises(ValueError, match="rule version"):
        analyze_sequence("NST", *args, rule_version="unknown")


def test_batch_exports_and_mutation_preserve_rule_version():
    import pandas as pd
    from batch_analysis import batch_analysis
    from desktop.batch_export import summary_frame
    frame = batch_analysis(pd.DataFrame([{"antibody_id": "A", "VH": "NNST", "VL": "ACD"}]), 31, 35, 50, 65, 99, 110)
    assert frame.loc[0, "rule_version"] == CURRENT_RULE_VERSION
    assert summary_frame(BatchResult([BatchRecord("A")], "synthetic")).loc[0, "rule_version"] == CURRENT_RULE_VERSION
    assert compare_mutation(VH, "N55Q").rule_version == CURRENT_RULE_VERSION


def test_duplicate_ids_bind_selection_and_transfer_to_record(app):
    transfers = []
    page = BatchAnalysisPage(open_single=lambda *args: transfers.append(args))
    records = [BatchRecord("dup", vh_sequence=VH, vh_length=120, status="SUCCESS"), BatchRecord("dup", vh_sequence="ACD", vh_length=3, status="SUCCESS")]
    page._done(BatchResult(records, "fixture.csv"))
    page.table.setCurrentCell(1, 1)
    assert page._selected_record(1) is records[1]
    page.open_in_single()
    assert transfers == [("dup", "ACD")]
    page.search.setText("dup")
    assert page._selected_record(1) is records[1]
    page.deleteLater()


@pytest.mark.parametrize("change", ["sequence", "mutation", "chain", "clear", "load"])
def test_rule_completion_cannot_publish_stale_mutation(app, change):
    page = MutationPage()
    started = []
    page.pool = type("Pool", (), {"start": lambda self, worker: started.append(worker)})()
    page.load_sequence("old", VH, "VH")
    page.mutation.setText("N55Q")
    page.simulate()
    worker = started[-1]
    result = compare_mutation(VH, "N55Q", "old", "VH")
    if change == "sequence": page.vh_sequence.setPlainText("ACD")
    elif change == "mutation": page.mutation.setText("M83L")
    elif change == "chain": page.chain.setCurrentText("VL")
    elif change == "clear": page.clear()
    else: page.load_sequence("new", VH[:-1] + "A", "VH")
    worker.signals.finished.emit(result)
    assert page._comparison is None
    assert not page.add_candidate_button.isEnabled()
    page.deleteLater()


def test_old_rule_completion_does_not_release_a_new_worker(app):
    page = MutationPage()
    started = []
    page.pool = type("Pool", (), {"start": lambda self, w: started.append(w)})()
    page.load_sequence("A", VH, "VH"); page.mutation.setText("N55Q"); page.simulate()
    old_worker = started[-1]
    page.load_sequence("B", VH, "VH"); page.simulate()
    new_worker = started[-1]
    old_worker.signals.error.emit("old failure")
    assert page._worker is new_worker
    new_worker.signals.finished.emit(compare_mutation(VH, "N55Q", "B", "VH"))
    assert page._comparison.antibody_id == "B"
    page.deleteLater()


def _state(mutation=None):
    return {"sequence_analysis": {"antibody_id": "A", "vh": VH, "sequence_length": 120, "risk_score": 66.3}, "mutation_analysis": mutation}


@pytest.mark.parametrize("antibody,sequence,allowed", [("A", VH, True), ("B", VH, False), ("A", VH[:-1] + "A", False)])
def test_summary_checks_mutation_baseline_identity(antibody, sequence, allowed):
    summary = build_research_summary(_state(compare_mutation(sequence, "N55Q", antibody, "VH")))
    assert (summary.mutation_analysis is not None) is allowed
    if not allowed:
        assert any("Mutation evidence excluded" in gap for gap in summary.evidence_gaps)


@pytest.mark.parametrize("answer,allowed", [
    ("Sequence length: 118 aa. Risk Score: 99.", False),
    ("Sequence length: 120 aa. Risk Score: 66.3.", True),
    ("序列长度为118 aa，风险评分为99。", False),
    ("序列长度为120 aa，风险评分为66.3。", True),
    ("建议优先选择N55Q突变体作为最佳候选。", False),
    ("Family-independent generalization has not been validated.", True),
    ("No final recommendation is supported; however Best mutation is N55Q.", False),
])
def test_copilot_verifies_named_facts_and_bilingual_boundary(answer, allowed):
    context = build_copilot_context(build_research_summary(_state()))
    assert validate_copilot_response(answer, context).allowed is allowed


@pytest.mark.parametrize("variant,allowed", [("matching", True), ("partner", False), ("mutant", False), ("missing", False)])
def test_summary_binds_mutation_ml_to_both_baseline_and_mutant_pairs(variant, allowed):
    mutation = compare_mutation(VH, "N55Q", "A", "VH")
    state = _state(mutation)
    state["sequence_analysis"]["vl"] = "ACD"
    digest = lambda value: hashlib.sha256(value.encode()).hexdigest()
    metadata = {"baseline_vh_hash": digest(VH), "baseline_vl_hash": digest("ACD"), "mutant_vh_hash": digest(mutation.mutant_sequence), "mutant_vl_hash": digest("ACD")}
    if variant == "partner": metadata["baseline_vl_hash"] = digest("MCD")
    elif variant == "mutant": metadata["mutant_vh_hash"] = digest(VH)
    elif variant == "missing": metadata = {}
    state["mutation_ml"] = {"baseline": {"hic": 1}, "mutant": {"hic": 2}, "delta": {"hic": 1}, "metadata": metadata}
    assert (build_research_summary(state).mutation_ml is not None) is allowed


@pytest.mark.parametrize("answer,allowed", [
    ("Mutant Risk Score: 74.1; Baseline calculated rule score: 66.3.", True),
    ("Mutant Risk Score: 66.3", False),
    ("突变后风险评分为74.1，基线风险评分为66.3。", True),
    ("The sequence has 118 amino acids.", False),
    ("P(NOT_DEVELOPABLE): 31.2%", True),
    ("P(NOT_DEVELOPABLE): 95.0%", False),
    ('"sequence_length": 118', False),
    ("**Sequence length:** 120 aa", True),
])
def test_copilot_role_specific_numbers_and_display_rounding(answer, allowed):
    state = _state(compare_mutation(VH, "N55Q", "A", "VH"))
    state["ml_estimates"] = {"developability": {"probability_not_developable": 0.312349}}
    context = build_copilot_context(build_research_summary(state))
    assert validate_copilot_response(answer, context).allowed is allowed


@pytest.mark.parametrize("answer,allowed", [
    ("Baseline HIC model estimate: 4.2; Mutant HIC model estimate: 4.0.", True),
    ("Mutant HIC model estimate: 9.0", False),
    ("Δ probability (percentage points): -4.0 pp", True),
    ("Mutant P(NOT_DEVELOPABLE): 99%", False),
])
def test_copilot_mutation_ml_claims_use_their_own_evidence(answer, allowed):
    from desktop.research_copilot import ResearchCopilotContext
    context = ResearchCopilotContext("synthetic", "synthetic", {"sequence_analysis": {}, "ml_estimates": {"hic_estimate": 4.2}, "mutation_ml": {"baseline": {"hic": 4.2, "probability": 0.31}, "mutant": {"hic": 4.0, "probability": 0.27}, "delta": {"probability": -0.04}}})
    assert validate_copilot_response(answer, context).allowed is allowed
