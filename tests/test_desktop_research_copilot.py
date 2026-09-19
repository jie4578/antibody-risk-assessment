import os

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

import pytest

from desktop.research_copilot import (
    RESEARCH_COPILOT_SYSTEM_PROMPT,
    ResearchCopilotBoundaryError,
    ResearchCopilotSession,
    build_copilot_context,
    privacy_disclosure,
    validate_copilot_response,
)
from desktop.research_summary import build_research_summary


VH = "EVQLVESGGGLVQPGGSLRLSCAASGFNIKDTYIHWVRQAPGKGLEWVARIYPTNGYTRYADSVKGRFTISADTSKNTAYLQMNSLRAEDTAVYYCSRWGGDGFYAMDYWGQGTLVTVSS"
VL = "DIQMTQSPSSLSASVGDRVTITCRASQSISSYLAWYQQKPGKAPKLLIYAASSLQSGVPSRFSGSGSGTDFTLTISSLQPEDFATYYCQQSYSTPYTFGQGTKVEIK"


def summary_state():
    return {
        "sequence_analysis": {
            "antibody_id": "Ab-001",
            "vh": VH,
            "vl": VL,
            "sequence_length": 120,
            "risk_score": {"overall_score": 66.3, "risk_level": "Medium Risk"},
            "risks": [{"chain": "VH", "position": "55-56", "motif": "NG", "category": "deamidation", "region": "CDR2"}],
        },
        "literature_evidence": [{
            "evidence_id": "europepmc:1", "title": "Antibody sequence liability", "authors": ["A Author"],
            "journal": "Journal", "year": 2024, "pmid": "12345678", "pmcid": "PMC123",
            "doi": "10.1000/test", "source": "europepmc", "relevance": "DIRECT",
        }],
    }


class RecordingBackend:
    def __init__(self, response="Evidence Summary\nThe reported evidence is limited."):
        self.calls = []
        self.response = response

    def complete(self, prompt, system_prompt=None):
        self.calls.append((prompt, system_prompt))
        return self.response


def test_context_is_summary_only_and_excludes_raw_sequences_and_secrets():
    summary = build_research_summary(summary_state())
    context = build_copilot_context(summary)
    serialized = context.to_json()
    assert VH not in serialized
    assert VL not in serialized
    assert "sequence_hashes" in serialized
    assert "api_key" not in serialized.casefold()
    assert "password" not in serialized.casefold()
    assert "Evidence Summary" in context.to_prompt()


def test_system_prompt_freezes_explanation_boundary():
    prompt = RESEARCH_COPILOT_SYSTEM_PROMPT.casefold()
    for phrase in ("do not call tools", "do not", "final research verdict", "family-independent", "full vh/vl sequences"):
        assert phrase in prompt
    assert "final recommendation" in prompt


def test_provider_is_not_called_until_explicit_session_action():
    context = build_copilot_context(build_research_summary(summary_state()))
    backend = RecordingBackend()
    session = ResearchCopilotSession(context)
    assert backend.calls == []
    result = session.explain(backend)
    assert len(backend.calls) == 1
    assert result.validation.allowed


def test_stale_summary_cannot_create_copilot_context():
    summary = build_research_summary(summary_state()).mark_stale()
    with pytest.raises(ValueError, match="stale"):
        build_copilot_context(summary)


def test_session_rejects_changed_summary_before_provider_call():
    state = summary_state()
    summary = build_research_summary(state)
    changed = dict(state)
    changed["sequence_analysis"] = dict(state["sequence_analysis"], sequence_length=119)
    backend = RecordingBackend()
    session = ResearchCopilotSession(build_copilot_context(summary))
    with pytest.raises(ValueError, match="changed"):
        session.explain(backend, current_summary=build_research_summary(changed))
    assert backend.calls == []


@pytest.mark.parametrize("response", [
    "Final Recommendation: proceed with N55Q.",
    "Best mutation is N55Q.",
    "This is a family-independent model validated across unrelated antibody families.",
    "Clinical success probability is 80%.",
    "Overall evidence score: 9/10.",
])
def test_unsafe_decision_language_is_blocked(response):
    context = build_copilot_context(build_research_summary(summary_state()))
    validation = validate_copilot_response(response, context)
    assert not validation.allowed


def test_unknown_citation_is_blocked_but_summary_citation_is_allowed():
    context = build_copilot_context(build_research_summary(summary_state()))
    assert not validate_copilot_response("PMID: 99999999", context).allowed
    allowed = validate_copilot_response("The relevant record is PMID: 12345678 and DOI 10.1000/test.", context)
    assert allowed.allowed
    assert set(allowed.citations) == {"12345678", "10.1000/test"}


def test_irrelevant_literature_is_preserved_as_context_not_promoted():
    state = summary_state()
    state["literature_evidence"] = [dict(state["literature_evidence"][0], relevance="IRRELEVANT")]
    context = build_copilot_context(build_research_summary(state))
    paper = context.payload["literature_evidence"][0]
    assert paper["relevance"] == "IRRELEVANT"
    assert "promote" in RESEARCH_COPILOT_SYSTEM_PROMPT


def test_privacy_disclosure_is_provider_specific_without_exposing_credentials():
    assert "not included by default" in privacy_disclosure("deepseek")
    assert "local" in privacy_disclosure("ollama").casefold()
    assert "offline mock" in privacy_disclosure("mock").casefold()


def test_boundary_error_preserves_block_reason_without_returning_unsafe_text():
    context = build_copilot_context(build_research_summary(summary_state()))
    session = ResearchCopilotSession(context)
    with pytest.raises(ResearchCopilotBoundaryError) as error:
        session.explain(RecordingBackend("Best mutation is N55Q."))
    assert "recommendation" in str(error.value).casefold() or "mutation" in str(error.value).casefold()
    assert session.last_response is None


def test_single_analysis_summary_has_explicit_copilot_action_and_no_auto_call(qapp=None):
    from PySide6.QtWidgets import QApplication
    from desktop.widgets.single_analysis import SingleAnalysisPage

    app = QApplication.instance() or QApplication([])
    page = SingleAnalysisPage()
    page.set_input("Ab-001", VH, analyze=True)
    page.build_research_summary()
    assert page._copilot_worker is None
    assert page.copilot_explain_button.isEnabled()
    assert page.copilot_answer.toPlainText() == ""
    page.deleteLater()
    app.processEvents()
