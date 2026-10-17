"""Explanation grounding is separate from scientific calculation and privacy."""

from dataclasses import replace

import pytest

from desktop.research_copilot import (
    COPILOT_INITIAL_PROMPT, RESEARCH_COPILOT_SYSTEM_PROMPT,
    ResearchCopilotBoundaryError, ResearchCopilotSession,
    build_copilot_context, validate_copilot_response,
)
from desktop.research_summary import build_research_summary


@pytest.fixture
def context():
    return build_copilot_context(build_research_summary({"sequence_analysis": {
        "antibody_id": "synthetic", "vh": "NNST", "sequence_length": 4,
        "risks": [{"motif": "NNS", "position": "1-3", "region": "FW"}],
    }}))


def test_prompts_explicitly_exclude_external_background_and_assumptions():
    for prompt in (RESEARCH_COPILOT_SYSTEM_PROMPT, COPILOT_INITIAL_PROMPT):
        assert "background knowledge" in prompt
        assert "mechanistic" in prompt
    assert "Do not invent tensions" in RESEARCH_COPILOT_SYSTEM_PROMPT


@pytest.mark.parametrize("text", [
    "CDR liabilities may affect antigen-binding region integrity.",
    "CDR-localized liabilities are consistent with the general concern that CDR liabilities may affect antigen-binding region integrity — but the summary does not make a causal claim.",
    "There are no ML estimates; CDR liabilities may impair binding.",
    "CDR motifs can reduce affinity.",
    "CDR liabilities not only affect binding but also reduce expression.",
    "CDR风险可能影响抗原结合区完整性。",
    "CDR位点可能导致亲和力下降。",
    "The NNS (1-3) and NST (2-4) motifs share the same starting N residue at position 1.",
    "NNS与NST基序共享相同的起始残基。",
])
def test_absent_mechanistic_background_is_blocked_even_when_hedged(context, text):
    result = validate_copilot_response(text, context)
    assert not result.allowed
    assert "background" in result.reason


@pytest.mark.parametrize("text", [
    "CDR liability sites are reported separately from framework sites.",
    "CDR liabilities have not been shown to affect binding by this summary.",
    "No evidence that CDR liabilities affect binding is provided.",
    "CDR风险未被证明会影响抗原结合。",
    "Experimental ML estimates have not been calculated.",
    "Family-independent generalization is unknown.",
])
def test_descriptive_counts_and_explicit_evidence_gaps_remain_allowed(context, text):
    assert validate_copilot_response(text, context).allowed


def test_reported_background_can_be_quoted_without_inventing_new_evidence(context):
    text = "CDR liabilities may affect binding."
    payload = dict(context.payload, literature_evidence=[{
        "title": text, "relevance": "GENERAL", "pmid": "12345678",
    }])
    supported = replace(context, payload=payload)
    assert validate_copilot_response(text + " Reported paper title; relevance: GENERAL.", supported).allowed


def test_rejected_background_is_not_returned_or_saved(context):
    class Backend:
        def complete(self, prompt, system_prompt=None):
            return "CDR liabilities may impair binding."

    session = ResearchCopilotSession(context)
    with pytest.raises(ResearchCopilotBoundaryError):
        session.explain(Backend())
    assert session.last_response is None
    assert session.history == []
