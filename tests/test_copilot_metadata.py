"""Metadata shape claims must reflect the unmodified Summary payload."""

import copy
import json

import pytest

from desktop.research_copilot import (
    ResearchCopilotBoundaryError, ResearchCopilotContext, ResearchCopilotSession,
    build_copilot_context, validate_copilot_response,
)
from desktop.research_summary import build_research_summary


@pytest.fixture
def context():
    return build_copilot_context(build_research_summary({"sequence_analysis": {
        "antibody_id": "synthetic", "vh": "AAANNSTTT", "sequence_length": 9,
    }}))


@pytest.mark.parametrize("text", [
    '`literature_identifiers` and `rule_result_id` are empty strings.',
    '`literature_identifiers` / `rule_result_id` are empty strings.',
    'literature_identifiers is an empty string.',
    'literature_identifiers = null.',
    'literature_identifiers is an empty object.',
    'rule_result_id is an empty list.',
    'sequence_hashes is an array.',
    'sequence_hashes is an empty object.',
    'literature_identifiers 和 rule_result_id 均为空字符串。',
    'literature_identifiers 是空字符串。',
    'rule_result_id 为数组。',
])
def test_wrong_metadata_types_or_empty_states_are_blocked(context, text):
    result = validate_copilot_response(text, context)
    assert not result.allowed
    assert "metadata" in result.reason


@pytest.mark.parametrize("text", [
    'literature_identifiers is an empty list; rule_result_id is an empty string.',
    'literature_identifiers is an array. sequence_hashes is an object.',
    'literature_identifiers and rule_result_id are empty.',
    'No literature identifiers are recorded; no rule result ID is recorded.',
    'literature_identifiers 是空列表；rule_result_id 是空字符串。',
    'literature_identifiers is not a string; it is an empty list.',
    'sequence_hashes is not an empty object.',
])
def test_accurate_metadata_or_plain_missing_evidence_wording_is_allowed(context, text):
    assert validate_copilot_response(text, context).allowed


@pytest.mark.parametrize("value, text, allowed", [
    (None, 'literature_identifiers is null.', True),
    (None, 'literature_identifiers is an empty list.', False),
    (['synthetic-id'], 'literature_identifiers is an empty array.', False),
    (['synthetic-id'], 'literature_identifiers is an array.', True),
])
def test_actual_metadata_not_assumed_schema_controls_validation(value, text, allowed):
    context = ResearchCopilotContext("synthetic", "synthetic", {
        "provenance": {"literature_identifiers": value},
    })
    assert validate_copilot_response(text, context).allowed is allowed


def test_prompt_supplies_exact_shape_facts_without_coercing_summary(context):
    before = copy.deepcopy(context.payload)
    prompt = context.to_prompt()
    assert 'provenance.literature_identifiers: array (empty)' in prompt
    assert 'provenance.rule_result_id: string (empty)' in prompt
    assert 'provenance.sequence_hashes: object (non-empty)' in prompt
    assert context.payload == before
    payload = json.loads(context.to_json())["research_summary"]
    assert payload["provenance"]["literature_identifiers"] == []
    assert payload["provenance"]["rule_result_id"] == ""


def test_wrong_metadata_response_is_blocked_not_rewritten_or_saved(context):
    class Backend:
        def complete(self, prompt, system_prompt=None):
            return 'literature_identifiers and rule_result_id are empty strings.'

    session = ResearchCopilotSession(context)
    with pytest.raises(ResearchCopilotBoundaryError):
        session.explain(Backend())
    assert session.last_response is None
    assert session.history == []
