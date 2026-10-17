"""Opt-in real Provider checks. Never enabled in the normal non-live suite.

Only synthetic AAANNSTTT input is sent to the configured official DeepSeek API.
No dataset, model inference, credentials or private antibody input is logged.
"""

import os
from dataclasses import asdict

import pytest

pytestmark = pytest.mark.live


@pytest.fixture
def backend():
    if os.environ.get("ANTIBODY_RUN_LIVE_ACCEPTANCE") != "1":
        pytest.skip("Explicit live acceptance opt-in required")
    from config import get_env
    from desktop.settings import build_backend, load_settings

    config = load_settings()
    if config.provider != "deepseek" or config.base_url.rstrip("/") not in {
        "https://api.deepseek.com", "https://api.deepseek.com/v1",
    }:
        pytest.skip("Configured official DeepSeek provider required; settings not changed")
    config.api_key = get_env("DEEPSEEK_API_KEY") or ""
    if not config.api_key:
        from desktop.credentials import CredentialError, CredentialStore
        try:
            config.api_key = CredentialStore().get("deepseek")
        except CredentialError:
            pass
    if not config.api_key:
        pytest.skip("No reusable configured credential; session-only UI key is not extracted")
    return build_backend(config)


def test_real_agent_calls_scan_and_preserves_overlapping_sequons(backend):
    from agent.agent import Agent
    from agent.tools import ToolRegistry, default_tools

    tools = ToolRegistry()
    tools.register(default_tools().get("scan_antibody"))
    try:
        result = Agent(backend=backend, tools=tools, max_steps=3).run(
            "请调用 scan_antibody 扫描合成测试序列 AAANNSTTT 。仅报告工具返回的序列长度、"
            "N-糖基化候选基序及其位置、规则版本；不要推断实验修饰，不要搜索或运行ML。"
        )
    except Exception as error:
        pytest.fail("Real Agent request failed: " + type(error).__name__, pytrace=False)
    calls = [step for step in result["steps"] if step.get("type") == "tool"]
    assert calls and all(step["tool"] == "scan_antibody" for step in calls)
    assert all(step["arguments"].get("sequence") == "AAANNSTTT" for step in calls)
    assert all(not step.get("blocked") for step in calls)
    assert "NNS@4-6" in calls[0]["result"] and "NST@5-7" in calls[0]["result"]
    answer = result["answer"]
    assert "NNS" in answer and "NST" in answer and "overlap_v2" in answer
    print("\nLIVE_AGENT_REAL_TOOL_CALLS:", [step["tool"] for step in calls])
    print("LIVE_AGENT_SYNTHETIC_ANSWER:\n" + answer)


def synthetic_copilot_context():
    from core import analyze_sequence
    from desktop.research_copilot import build_copilot_context
    from desktop.research_summary import build_research_summary

    result = analyze_sequence("AAANNSTTT", 31, 35, 50, 65, 99, 110)
    summary = build_research_summary({"sequence_analysis": {
        "antibody_id": "SYNTHETIC-ACCEPTANCE", "vh": "AAANNSTTT", "sequence_length": 9,
        "rule_version": result.metadata["rule_version"],
        "chain_context": "First input only; VL partner was not provided or rule-scanned.",
        "risks": [asdict(item) for item in result.risks],
    }})
    context = build_copilot_context(summary)
    assert len(context.payload["provenance"]["sequence_hashes"]["VH"]) == 64
    return context


def test_real_copilot_explains_only_synthetic_summary(backend):
    from desktop.research_copilot import ResearchCopilotSession

    context = synthetic_copilot_context()
    class RecordingBackend:
        text = ""
        def complete(self, *args, **kwargs):
            self.text = backend.complete(*args, **kwargs)
            return self.text

    recorder = RecordingBackend()
    try:
        response = ResearchCopilotSession(context).explain(recorder)
    except Exception as error:
        # Synthetic-only diagnostic: preserve a rejected response as a failure,
        # not as a successful explanation or a silent retry.
        print("\nLIVE_COPILOT_REJECTED_SYNTHETIC_ANSWER:\n" + recorder.text)
        pytest.fail("Real Copilot request failed or was blocked: " + type(error).__name__, pytrace=False)
    assert response.validation.allowed
    assert response.text and "[SEQUENCE OMITTED]" not in response.text
    assert "SYNTHETIC-ACCEPTANCE" in response.text
    print("\nLIVE_COPILOT_SYNTHETIC_ANSWER:\n" + response.text)


def test_real_copilot_preserves_metadata_types(backend):
    from desktop.research_copilot import ResearchCopilotSession

    response = ResearchCopilotSession(synthetic_copilot_context()).explain(
        backend,
        question=("Describe only the JSON types and empty/non-empty states of provenance."
                  "literature_identifiers, provenance.rule_result_id and provenance.sequence_hashes. "
                  "Name each field separately, use array/string/object/null accurately, "
                  "and do not discuss biology or scientific results."),
    )
    text = response.text.casefold()
    assert response.validation.allowed
    for field in ("literature_identifiers", "rule_result_id", "sequence_hashes"):
        assert field in text
    assert "array" in text and "string" in text and "object" in text
    print("\nLIVE_COPILOT_METADATA_ANSWER:\n" + response.text)
