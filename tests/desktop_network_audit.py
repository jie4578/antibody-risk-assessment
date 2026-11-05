"""Opt-in test-process network observer. Never imported by the Desktop product.

Logs categories and sanitized call sites, never addresses, request bodies,
queries, sequences, headers or credentials. Remote and unknown targets fail
closed. Only an explicitly selected Windows asyncio socketpair is permitted.
"""
from __future__ import annotations

from contextlib import ExitStack
import ipaddress
from pathlib import Path
import socket
import sysconfig
import threading
import traceback
from unittest.mock import patch


def address_category(address):
    host = address[0] if isinstance(address, tuple) and address else address
    if not isinstance(host, str):
        return "unknown"
    try:
        value = ipaddress.ip_address(host)
    except ValueError:
        return "hostname"  # Do not resolve or log it.
    return "loopback" if value.is_loopback else "non_loopback_ip"


def safe_frames(frames):
    return [{"file": Path(frame.filename).name, "function": frame.name, "line": frame.lineno}
            for frame in frames if Path(frame.filename).name != Path(__file__).name]


def is_windows_socketpair(address, frames):
    stdlib = Path(sysconfig.get_path("stdlib")).resolve()
    calls = {(Path(frame.filename).resolve(), frame.name) for frame in frames}
    pipe = (stdlib / "asyncio" / "proactor_events.py", "_make_self_pipe") in calls
    # CPython 3.14 moved Windows' fallback to socket._fallback_socketpair.
    # Require the actual stdlib file and asyncio self-pipe caller, not just
    # a filename or an arbitrary loopback address (which might be a Provider).
    pair = ((Path(socket.__file__).resolve(), "_fallback_socketpair") in calls
            or (Path(socket.__file__).resolve(), "socketpair") in calls
            or (stdlib / "asyncio" / "windows_utils.py", "socketpair") in calls)
    return address_category(address) == "loopback" and pipe and pair


class NetworkAudit:
    def __init__(self, *, allow_asyncio_socketpair=False):
        self.allow_asyncio_socketpair = allow_asyncio_socketpair
        self.events = []
        self.phase = "imports"
        self._stack = ExitStack()
        self._lock = threading.Lock()

    def _decision(self, api, address):
        frames = traceback.extract_stack(limit=32)
        allowed = self.allow_asyncio_socketpair and is_windows_socketpair(address, frames)
        event = {"api": api, "phase": self.phase, "target_category": address_category(address),
                 "allowed": allowed, "caller": safe_frames(frames),
                 "reason": "verified_stdlib_asyncio_socketpair" if allowed else "blocked_by_test_guard"}
        with self._lock:
            if len(self.events) >= 200:
                raise RuntimeError("Network audit event bound exceeded")
            self.events.append(event)
        if not allowed:
            raise RuntimeError("Offline diagnostic blocked a connection or name lookup")

    def __enter__(self):
        connect, connect_ex = socket.socket.connect, socket.socket.connect_ex
        create, resolve = socket.create_connection, socket.getaddrinfo

        def traced_connect(sock, address):
            self._decision("socket.connect", address)
            return connect(sock, address)

        def traced_connect_ex(sock, address):
            self._decision("socket.connect_ex", address)
            return connect_ex(sock, address)

        def traced_create(address, *args, **kwargs):
            self._decision("socket.create_connection", address)
            return create(address, *args, **kwargs)

        def traced_resolve(host, port, *args, **kwargs):
            self._decision("socket.getaddrinfo", (host, port))
            return resolve(host, port, *args, **kwargs)

        for target, replacement in (("socket.socket.connect", traced_connect),
                                    ("socket.socket.connect_ex", traced_connect_ex),
                                    ("socket.create_connection", traced_create),
                                    ("socket.getaddrinfo", traced_resolve)):
            self._stack.enter_context(patch(target, replacement))
        return self

    def __exit__(self, *args):
        return self._stack.__exit__(*args)

    def report(self):
        with self._lock:
            events = list(self.events)
        return {"api_event_count": len(events), "allowed_socketpair_events": sum(e["allowed"] for e in events),
                "blocked_events": sum(not e["allowed"] for e in events), "events": events,
                "remote_connections_permitted": False, "raw_addresses_recorded": False}
