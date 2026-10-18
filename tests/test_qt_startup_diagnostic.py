"""Diagnostic classification must not hide a crash or guess from a COM code."""
import copy

import pytest

from qt_startup_diagnostic import C_STACK_HEADER, C_STACK_UNAVAILABLE, COM_HEADER, classify_probe


def healthy(events=None):
    return {"exit_code": 0, "closed": True, "heartbeat_count": 100,
            "heartbeat_after_last_com": 50, "observer_healthy": True,
            "fault_handler": True, "native_trace_version": 1,
            "events": [] if events is None else events}


def uia_event():
    # Module chain observed in both the full Desktop and empty QWidget probes.
    return {"code": "0x8001010d", "phase": "event_loop", "frames": [
        {"module": "KERNELBASE.dll", "offset": "0x25369"},
        {"module": "RPCRT4.dll", "offset": "0x5a780"},
        {"module": "combase.dll", "offset": "0x4096c"},
        {"module": "UIAutomationCore.DLL", "offset": "0x2f768",
         "uia_return_raw_provider": True, "api_displacement": "0xd8"},
        {"module": "qwindows.dll", "offset": "0x7e108"},
        {"module": "USER32.dll", "offset": "0x210e3"},
    ]}


COM_STDERR = COM_HEADER + '\n\nCurrent thread 0x1234 (most recent call first):\n  File "probe.py", line 1 in run\n'
COM_STDERR_314 = COM_STDERR + "\n" + C_STACK_HEADER + "\n" + C_STACK_UNAVAILABLE + "\n"


def test_python314_exact_fallback_requires_the_same_native_and_health_evidence():
    payload = healthy([uia_event()])
    payload["python_version"] = [3, 14, 5]
    before = copy.deepcopy(payload)
    result = classify_probe(0, payload, COM_STDERR_314)
    assert result["status"] == "REVIEWED_UIA_COM_DIAGNOSTIC"
    assert not result["clean"]
    assert payload == before
    payload["events"][0]["frames"][3].pop("uia_return_raw_provider")
    assert classify_probe(0, payload, COM_STDERR_314)["status"] == "FAIL"
    assert classify_probe(1, before, COM_STDERR_314)["status"] == "FAIL"
    before["heartbeat_after_last_com"] = 0
    assert classify_probe(0, before, COM_STDERR_314)["status"] == "FAIL"


@pytest.mark.parametrize("version", [None, [3, 13, 9], [3, 15, 0], "3.14.5", [3, 14, True]])
def test_c_stack_fallback_on_missing_or_unreviewed_python_version_fails(version):
    payload = healthy([uia_event()])
    payload["python_version"] = version
    assert classify_probe(0, payload, COM_STDERR_314)["status"] == "FAIL"


@pytest.mark.parametrize("stderr", [
    COM_STDERR,
    COM_STDERR + C_STACK_HEADER + "\n",
    COM_STDERR + C_STACK_UNAVAILABLE + "\n",
    COM_STDERR_314.replace(C_STACK_UNAVAILABLE, "  <system returned no stack trace>"),
    COM_STDERR_314.replace(C_STACK_UNAVAILABLE, '  Binary file "unknown.dll", at +0x123'),
    COM_STDERR_314 + C_STACK_HEADER + "\n" + C_STACK_UNAVAILABLE + "\n",
    COM_STDERR_314 + "Traceback (most recent call last):\n",
    COM_STDERR_314 + '  File "unexpected.py", line 2 in run\n',
    COM_STDERR_314 + "Windows fatal exception: access violation\n",
    COM_HEADER + "\n" + C_STACK_HEADER + "\n" + C_STACK_UNAVAILABLE + "\n",
])
def test_python314_malformed_missing_extra_or_other_fatal_output_fails(stderr):
    payload = healthy([uia_event()])
    payload["python_version"] = [3, 14, 5]
    assert classify_probe(0, payload, stderr)["status"] == "FAIL"


def test_multiple_python314_events_require_one_fallback_per_event():
    payload = healthy([uia_event(), uia_event()])
    payload["python_version"] = [3, 14, 5]
    result = classify_probe(0, payload, COM_STDERR_314 * 2)
    assert result["status"] == "REVIEWED_UIA_COM_DIAGNOSTIC"
    assert not result["clean"]
    assert classify_probe(0, payload, COM_STDERR_314 + COM_STDERR)["status"] == "FAIL"


def test_clean_process_is_distinct_from_reviewed_diagnostic():
    assert classify_probe(0, healthy(), "")["status"] == "CLEAN"
    result = classify_probe(0, healthy([uia_event()]), COM_STDERR)
    assert result["status"] == "REVIEWED_UIA_COM_DIAGNOSTIC"
    assert not result["clean"] and result["diagnostic_present"]


@pytest.mark.parametrize("returncode", [1, -1, 0xC0000005])
def test_nonzero_exit_is_never_downgraded(returncode):
    assert classify_probe(returncode, healthy([uia_event()]), COM_STDERR)["status"] == "FAIL"


@pytest.mark.parametrize("key,value", [
    ("exit_code", 1), ("closed", False), ("fault_handler", False),
    ("heartbeat_count", 0), ("heartbeat_count", True), ("heartbeat_count", None),
    ("native_trace_version", None), ("events", None),
    ("heartbeat_after_last_com", 0), ("observer_healthy", False),
])
def test_missing_health_or_native_evidence_fails(key, value):
    payload = healthy([uia_event()])
    payload[key] = value
    assert classify_probe(0, payload, COM_STDERR)["status"] == "FAIL"


@pytest.mark.parametrize("payload", [None, {}, [], healthy()])
def test_code_alone_or_missing_payload_does_not_exempt_failure(payload):
    assert classify_probe(0, payload, COM_STDERR)["status"] == "FAIL"


@pytest.mark.parametrize("stderr", [
    "Windows fatal exception: access violation\n",
    "Windows fatal exception: code 0xc0000005\n",
    COM_STDERR + "Windows fatal exception: code 0xc0000005\n",
    COM_STDERR + "Traceback (most recent call last):\n",
    COM_STDERR + "Fatal Python error: Aborted\n",
    COM_STDERR + "QThread: Destroyed while thread is still running\n",
    COM_STDERR + "unexpected warning or error\n",
    "unexplained stderr\n",
    "",
])
def test_other_fatal_or_unreviewed_output_still_fails(stderr):
    assert classify_probe(0, healthy([uia_event()]), stderr)["status"] == "FAIL"


@pytest.mark.parametrize("change", ["module", "order", "api", "phase", "code", "frames", "count"])
def test_unverified_or_different_native_path_fails(change):
    event = copy.deepcopy(uia_event())
    if change == "module":
        event["frames"][3]["module"] = "unrelated.dll"
    elif change == "order":
        event["frames"].reverse()
    elif change == "api":
        del event["frames"][3]["uia_return_raw_provider"]
    elif change == "phase":
        event["phase"] = "unknown"
    elif change == "code":
        event["code"] = "0xc0000005"
    elif change == "frames":
        event["frames"] = None
    events = [event, event] if change == "count" else [event]
    assert classify_probe(0, healthy(events), COM_STDERR)["status"] == "FAIL"


def test_classification_does_not_mutate_or_rewrite_evidence():
    payload = healthy([uia_event()])
    before = copy.deepcopy(payload)
    text = COM_STDERR
    classify_probe(0, payload, text)
    assert payload == before
    assert text == COM_STDERR
