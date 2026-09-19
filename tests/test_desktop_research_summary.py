import copy
import os

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from desktop.research_summary import (
    MUTATION_ML_EXPANDED_LIMITATION,
    MUTATION_ML_WARNING,
    ResearchDecisionSummary,
    build_research_summary,
    summary_fingerprint,
)


VH = "EVQLVESGGGLVQPGGSLRLSCAASGFNIKDTYIHWVRQAPGKGLEWVARIYPTNGYTRYADSVKGRFTISADTSKNTAYLQMNSLRAEDTAVYYCSRWGGDGFYAMDYWGQGTLVTVSS"
VL = "DIQMTQSPSSLSASVGDRVTITCRASQSVSSYLAWYQQKPGKAPKLLIYAASTLQSGVPSRFSGSGSGTDFTLTISSLQPEDFATYYCQQYNSYPLTFGQGTKVEIK"


def rule_state():
    return {
        "sequence_analysis": {
            "antibody_id": "Ab-001",
            "vh": VH,
            "vl": VL,
            "sequence_length": 120,
            "risk_score": {"overall_score": 66.3, "risk_level": "Medium Risk"},
            "risks": [
                {"chain": "VH", "position": "55-56", "motif": "NG", "category": "deamidation", "region": "CDR2"},
                {"chain": "VH", "position": "83", "motif": "M", "category": "oxidation", "region": "FW"},
            ],
        }
    }


def ml_state():
    return {
        "result": {
            "hic": {"predicted_value": 4.2, "model_id": "hic_esm2_v1"},
            "developability": {"probability_not_developable": 0.31, "model_id": "developability_esm2_v1"},
        },
        "provenance": {"benchmark": "AINTIBODY_INTERNAL_ENTITY_EXACT_V1", "model_version": "phase5-frozen-v1"},
    }


def mutation_state():
    return {
        "mutation": "N55Q",
        "chain": "VH",
        "original_score": 66.3,
        "mutant_score": 74.1,
        "delta_score": 7.8,
        "removed_risks": [{"motif": "NG", "position": "55-56", "region": "CDR2"}],
        "added_risks": [],
        "unchanged_risks": [],
    }


def mutation_ml_state():
    return {
        "baseline": {"hic": 4.2, "probability": 0.31},
        "mutant": {"hic": 4.0, "probability": 0.27},
        "delta": {"hic": -0.2, "probability": -0.04},
        "metadata": {"mutation_effect_validation": "not_validated"},
    }


def paper(relevance):
    return {
        "evidence_id": "europepmc:1",
        "title": "Antibody sequence liability",
        "authors": ["A Author"],
        "journal": "Journal",
        "year": 2024,
        "pmid": "12345678",
        "pmcid": "PMC123",
        "doi": "10.1000/test",
        "source": "europepmc",
        "relevance": relevance,
    }


def test_rule_only_summary_is_structured_and_does_not_make_a_verdict():
    summary = build_research_summary(rule_state())
    assert isinstance(summary, ResearchDecisionSummary)
    assert summary.sequence_analysis["calculated_score"] == 66.3
    assert summary.sequence_analysis["total_sites"] == 2
    assert summary.ml_estimates is None
    assert "Experimental ML estimates have not been calculated." in summary.evidence_gaps
    text = summary.render_text().lower()
    assert "research decision summary" in text
    assert "success probability" not in text
    assert "best mutation" not in text


def test_rule_and_single_ml_preserve_model_context_without_categorical_label():
    state = rule_state(); state["ml_estimates"] = ml_state()
    summary = build_research_summary(state)
    assert summary.ml_estimates["hic_estimate"] == 4.2
    assert summary.ml_estimates["probability_not_developable"] == 0.31
    text = summary.render_text()
    assert "Research-support model estimate. Experimental verification is required." in text
    assert "No categorical decision threshold is defined." in text
    assert "84/95" in text
    assert "P(NOT_DEVELOPABLE)" in text
    assert "DEVELOPABLE" not in text.replace("P(NOT_DEVELOPABLE)", "")


def test_mutation_rule_and_mutation_ml_are_kept_as_separate_evidence_layers():
    state = rule_state(); state["mutation_analysis"] = mutation_state(); state["mutation_ml"] = mutation_ml_state()
    summary = build_research_summary(state)
    assert summary.mutation_analysis["mutation"] == "N55Q"
    assert summary.mutation_ml["delta"]["probability"] == -0.04
    text = summary.render_text()
    assert MUTATION_ML_WARNING in text
    assert MUTATION_ML_EXPANDED_LIMITATION in text
    assert "recommended" not in text.lower()
    assert "better" not in text.lower()


def test_literature_preserves_direct_general_irrelevant_semantics():
    state = rule_state(); state["literature_evidence"] = [paper("DIRECT"), paper("GENERAL"), paper("IRRELEVANT")]
    summary = build_research_summary(state)
    assert [item["relevance"] for item in summary.literature_evidence] == ["DIRECT", "GENERAL", "IRRELEVANT"]
    text = summary.render_text()
    assert "Relevance: DIRECT" in text and "Relevance: GENERAL" in text and "Relevance: IRRELEVANT" in text
    assert "No literature evidence has been attached" not in text


def test_missing_evidence_is_explicit_and_not_fabricated():
    summary = build_research_summary(rule_state())
    assert "No literature evidence has been attached." in summary.evidence_gaps
    assert "No mutation hypothesis is included in this summary." in summary.evidence_gaps
    text = summary.render_text()
    assert "not calculated" in text
    assert "has been attached" in text


def test_fingerprint_and_stale_detection_cover_sequence_ml_mutation_and_literature():
    state = rule_state(); state["ml_estimates"] = ml_state(); state["literature_evidence"] = [paper("GENERAL")]
    summary = build_research_summary(state)
    assert summary.fingerprint == summary_fingerprint(state)
    changed = copy.deepcopy(state); changed["sequence_analysis"]["vh"] = VH[:-1] + "A"
    assert summary.stale_for(changed)
    changed = copy.deepcopy(state); changed["ml_estimates"]["result"]["hic"]["predicted_value"] = 4.3
    assert summary.stale_for(changed)
    changed = copy.deepcopy(state); changed["literature_evidence"][0]["pmid"] = "99999999"
    assert summary.stale_for(changed)
    assert summary.mark_stale().stale


def test_summary_generation_does_not_recompute_science_or_call_external_layers(monkeypatch):
    import core
    import scoring
    import desktop.literature_adapter as literature_adapter
    import desktop.ml_adapter as ml_adapter

    monkeypatch.setattr(core, "analyze_sequence", lambda *args, **kwargs: (_ for _ in ()).throw(AssertionError("rule recomputed")), raising=False)
    monkeypatch.setattr(scoring, "compute_risk_score", lambda *args, **kwargs: (_ for _ in ()).throw(AssertionError("score recomputed")), raising=False)
    monkeypatch.setattr(literature_adapter, "search_literature", lambda *args, **kwargs: (_ for _ in ()).throw(AssertionError("literature searched")), raising=False)
    monkeypatch.setattr(ml_adapter, "FrozenMLPredictor", lambda *args, **kwargs: (_ for _ in ()).throw(AssertionError("ML recomputed")), raising=False)
    state = rule_state(); state["ml_estimates"] = ml_state(); state["literature_evidence"] = [paper("DIRECT")]
    summary = build_research_summary(state)
    assert summary.ml_estimates is not None


def test_summary_schema_has_no_overall_or_decision_score():
    summary = build_research_summary(rule_state())
    payload = summary.to_dict()
    assert not {"overall_score", "combined_score", "recommendation_score", "decision_score"}.intersection(payload)
    assert "overall_score" not in payload["sequence_analysis"]


def test_summary_render_contains_required_limitations():
    state = rule_state(); state["mutation_analysis"] = mutation_state(); state["mutation_ml"] = mutation_ml_state()
    text = build_research_summary(state).render_text()
    for expected in ("internal", "84/95", "Family-independent generalization is unknown", "experimental verification", "mutation-effect", "Literature evidence may provide mechanism/context"):
        assert expected.lower() in text.lower()


def test_single_analysis_summary_requires_explicit_action_and_marks_stale(qapp=None):
    from PySide6.QtWidgets import QApplication
    from desktop.widgets.single_analysis import SingleAnalysisPage

    app = QApplication.instance() or QApplication([])
    page = SingleAnalysisPage()
    assert page.research_summary is None
    page.sequence.setPlainText(VH)
    page.build_summary_button.click()
    assert page.research_summary is not None
    assert not page.summary_view.isHidden()
    page.sequence.setPlainText(VH[:-1] + "A")
    assert page.research_summary.is_stale
    assert "Outdated" in page.summary_status.text()
    page.deleteLater(); app.processEvents()
