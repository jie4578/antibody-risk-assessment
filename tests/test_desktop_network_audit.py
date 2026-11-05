import json
import os
import socket
import sysconfig
from pathlib import Path
from traceback import FrameSummary

import pytest

from desktop_network_audit import NetworkAudit, address_category, is_windows_socketpair, safe_frames


@pytest.mark.parametrize("address,category", [(("127.0.0.1", 123), "loopback"),
    (("::1", 123), "loopback"), (("198.51.100.9", 443), "non_loopback_ip"),
    (("private-service.invalid", 443), "hostname"), (None, "unknown")])
def test_address_categories_never_resolve(address, category):
    assert address_category(address) == category


def frames():
    root = Path(sysconfig.get_path("stdlib"))
    return [FrameSummary(str(root / "asyncio" / "proactor_events.py"), 1, "_make_self_pipe"),
            FrameSummary(str(root / "asyncio" / "windows_utils.py"), 1, "socketpair")]


def test_loopback_alone_does_not_exempt_a_connection():
    assert is_windows_socketpair(("127.0.0.1", 9999), frames())
    assert not is_windows_socketpair(("api.invalid", 443), frames())
    assert not is_windows_socketpair(("127.0.0.1", 9999), [FrameSummary("client.py", 1, "request")])
    assert not is_windows_socketpair(("127.0.0.1", 9999), [FrameSummary("windows_utils.py", 1, "socketpair")])


def test_python314_fallback_requires_the_actual_stdlib_and_self_pipe():
    caller = frames()[:1]
    actual = FrameSummary(socket.__file__, 1, "_fallback_socketpair")
    assert is_windows_socketpair(("127.0.0.1", 123), caller + [actual])
    assert not is_windows_socketpair(("127.0.0.1", 123), [actual])
    assert not is_windows_socketpair(("198.51.100.9", 443), caller + [actual])
    assert not is_windows_socketpair(("127.0.0.1", 123), caller + [FrameSummary("socket.py", 1, "_fallback_socketpair")])


@pytest.mark.parametrize("api", ["create", "resolve", "connect", "connect_ex"])
def test_unknown_network_calls_are_blocked_before_transmission(api):
    with NetworkAudit(allow_asyncio_socketpair=True) as audit:
        with pytest.raises(RuntimeError, match="blocked"):
            if api == "create":
                socket.create_connection(("secret-host.invalid", 443))
            elif api == "resolve":
                socket.getaddrinfo("secret-host.invalid", 443)
            else:
                with socket.socket() as sock:
                    getattr(sock, api)(("127.0.0.1", 1))
    report = audit.report()
    text = json.dumps(report)
    assert report["api_event_count"] == report["blocked_events"] == 1
    assert "secret-host" not in text and "127.0.0.1" not in text
    assert not report["remote_connections_permitted"]


def test_safe_trace_keeps_file_function_not_source_or_parent_paths():
    record = FrameSummary(str(Path("private-parent") / "client.py"), 8, "request", line="secret-payload")
    output = safe_frames([record])
    assert output == [{"file": "client.py", "function": "request", "line": 8}]
    assert "private-parent" not in json.dumps(output) and "secret-payload" not in json.dumps(output)


def test_context_restores_original_socket_functions():
    original = socket.socket.connect, socket.create_connection, socket.getaddrinfo
    with NetworkAudit():
        pass
    assert original == (socket.socket.connect, socket.create_connection, socket.getaddrinfo)


@pytest.mark.skipif(os.name != "nt", reason="Windows Proactor self-pipe integration only")
def test_windows_proactor_self_pipe_is_allowed_but_not_a_provider():
    import asyncio
    with NetworkAudit(allow_asyncio_socketpair=True) as audit:
        loop = asyncio.new_event_loop()
        try:
            assert not loop.is_closed()
        finally:
            loop.close()
    assert audit.report()["blocked_events"] == 0
    assert all(e["reason"] == "verified_stdlib_asyncio_socketpair" for e in audit.report()["events"])
