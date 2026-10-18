"""Opt-in native Qt diagnostic, not imported by the product or normal startup.

Keep original stdout/stderr and faulthandler. Only a healthy process with the
observed UIA -> COM/RPC native chain can receive the reviewed diagnostic status.
That status is deliberately not CLEAN. This is not an exception handler fix.
"""
from __future__ import annotations

import argparse
import json
import os
from pathlib import Path
import re
import subprocess
import sys


RESULT_PREFIX = "QT_NATIVE_PROBE="
COM_HEADER = "Windows fatal exception: code 0x8001010d"
C_STACK_HEADER = "Current thread's C stack trace (most recent call first):"
C_STACK_UNAVAILABLE = "  <cannot get C stack on this system>"


def classify_probe(returncode, payload, stderr):
    """Fail closed on missing health/native evidence or any other fatal output."""
    def decision(status, reason):
        return {"status": status, "reason": reason, "clean": status == "CLEAN",
                "diagnostic_present": bool(stderr.strip())}

    if not isinstance(payload, dict):
        return decision("FAIL", "Missing structured probe result")
    if returncode != 0 or payload.get("exit_code") != 0:
        return decision("FAIL", "Process did not exit successfully")
    if (payload.get("closed") is not True or payload.get("fault_handler") is not True
            or payload.get("observer_healthy") is not True
            or type(payload.get("heartbeat_count")) is not int
            or payload["heartbeat_count"] < 1):
        return decision("FAIL", "Closed-window/heartbeat/fault-handler evidence missing")
    events = payload.get("events")
    if not isinstance(events, list):
        return decision("FAIL", "Missing native observer evidence")
    if not stderr.strip() and not events:
        return decision("CLEAN", "Responsive event loop, normal exit, no diagnostic")
    headers = [line.strip() for line in stderr.splitlines()
               if "Windows fatal exception:" in line]
    if not headers or any(line.lower() != COM_HEADER.lower() for line in headers):
        return decision("FAIL", "Unknown or missing native diagnostic header")
    # Only faulthandler's header/thread/frame grammar is expected. Never remove
    # stderr or broadly whitelist everything containing the COM code.
    version = payload.get("python_version")
    python314 = (isinstance(version, list) and len(version) == 3
                 and all(type(part) is int for part in version)
                 and version[:2] == [3, 14] and version[2] >= 0)
    lines = stderr.splitlines()
    index, c_blocks = 0, 0
    python_frame, c_seen = False, False
    while index < len(lines):
        line = lines[index]
        index += 1
        if not line.strip():
            continue
        if line.strip() in headers:
            python_frame, c_seen = False, False
            continue
        if line == C_STACK_HEADER:
            # CPython 3.14 traceback.c emits this exact two-line fallback on
            # this Windows build. Do not accept arbitrary C frames/messages,
            # other versions, repeated blocks, or an orphan fallback line.
            if (not python314 or not python_frame or c_seen
                    or index >= len(lines) or lines[index] != C_STACK_UNAVAILABLE):
                return decision("FAIL", "Unreviewed Python C-stack output")
            index += 1
            c_blocks += 1
            c_seen = True
            continue
        if c_seen:
            return decision("FAIL", "Additional output after reviewed C-stack fallback")
        if re.fullmatch(r"(?:Current thread|Thread) 0x[0-9a-fA-F]+ \(most recent call first\):", line):
            continue
        if re.fullmatch(r'  File ".+", line \d+ in .+', line):
            python_frame = True
            continue
        return decision("FAIL", "Additional/unreviewed stderr output")
    if python314 and c_blocks != len(headers):
        return decision("FAIL", "Python 3.14 C-stack fallback count does not match")
    if payload.get("native_trace_version") != 1 or len(events) != len(headers):
        return decision("FAIL", "Diagnostic and native trace counts do not match")
    if type(payload.get("heartbeat_after_last_com")) is not int or payload["heartbeat_after_last_com"] < 1:
        return decision("FAIL", "No responsive heartbeat after the observed exception")
    chain = ["rpcrt4.dll", "combase.dll", "uiautomationcore.dll", "qwindows.dll", "user32.dll"]
    for event in events:
        if not isinstance(event, dict) or event.get("code") != "0x8001010d":
            return decision("FAIL", "Unreviewed native exception")
        if event.get("phase") not in {"window_show", "event_loop"}:
            return decision("FAIL", "Unreviewed exception phase")
        frames = event.get("frames")
        if not isinstance(frames, list) or not all(isinstance(f, dict) for f in frames):
            return decision("FAIL", "Missing native frames")
        modules = [str(frame.get("module", "")).lower() for frame in frames]
        cursor = 0
        for module in modules:
            if cursor < len(chain) and module == chain[cursor]:
                cursor += 1
        if cursor != len(chain):
            return decision("FAIL", "Native chain is not the reviewed UIA COM/RPC path")
        if not any(frame.get("uia_return_raw_provider") is True for frame in frames):
            return decision("FAIL", "UiaReturnRawElementProvider frame not verified")
    return decision("REVIEWED_UIA_COM_DIAGNOSTIC",
                    "Observed UIA COM/RPC first-chance diagnostic; process remained healthy. Not a clean run.")


def run_child(mode, duration):
    """Windows-only observer; always continue exception search unchanged."""
    import ctypes as C
    from ctypes import wintypes as W
    from contextlib import ExitStack
    import faulthandler
    import platform
    import tempfile
    from unittest.mock import patch

    if os.name != "nt":
        raise RuntimeError("Native probe requires Windows")
    if C.sizeof(C.c_void_p) != 8 or platform.machine().lower() not in {"amd64", "x86_64"}:
        raise RuntimeError("Native stack verification currently requires Windows x64")
    assert faulthandler.is_enabled()
    phase, events, ticks, observer_errors = "imports", [], [], []

    class Record(C.Structure):
        _fields_ = [("code", W.DWORD), ("flags", W.DWORD), ("nested", C.c_void_p),
                    ("address", C.c_void_p), ("count", W.DWORD), ("parameters", C.c_size_t * 15)]

    class Pointers(C.Structure):
        _fields_ = [("record", C.POINTER(Record)), ("context", C.c_void_p)]

    kernel = C.WinDLL("kernel32", use_last_error=True)
    capture = kernel.RtlCaptureStackBackTrace
    capture.argtypes = [W.DWORD, W.DWORD, C.POINTER(C.c_void_p), C.POINTER(W.DWORD)]
    capture.restype = W.WORD
    callback_type = C.WINFUNCTYPE(W.LONG, C.POINTER(Pointers))

    @callback_type
    def observe(info):
        try:
            if info.contents.record.contents.code == 0x8001010D and len(events) < 10:
                addresses = (C.c_void_p * 90)()
                count = capture(0, len(addresses), addresses, None)
                events.append({"code": "0x8001010d", "phase": phase,
                               "heartbeat_at_event": len(ticks),
                               "addresses": list(addresses[:count])})
        except BaseException as error:
            # Python errors cannot propagate through a native callback. Mark
            # this probe invalid, but still let Windows handle its exception.
            observer_errors.append(type(error).__name__)
        return 0  # EXCEPTION_CONTINUE_SEARCH; never CONTINUE_EXECUTION.

    kernel.AddVectoredExceptionHandler.argtypes = [W.ULONG, callback_type]
    kernel.AddVectoredExceptionHandler.restype = C.c_void_p
    kernel.RemoveVectoredExceptionHandler.argtypes = [C.c_void_p]
    handler = kernel.AddVectoredExceptionHandler(1, observe)
    assert handler
    try:
        with tempfile.TemporaryDirectory(prefix="antibody-qt-native-") as local:
            with patch.dict(os.environ, {"APPDATA": local, "HF_HOME": local,
                                         "HF_HUB_OFFLINE": "1", "QT_QPA_PLATFORM": "windows"}):
                from PySide6.QtCore import QTimer, qVersion
                from PySide6.QtWidgets import QApplication, QWidget
                app = QApplication([])
                with ExitStack() as patches:
                    phase = "window_create"
                    if mode == "project":
                        # Only the opt-in project mode reads the source checkout.
                        sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
                        from desktop.main_window import MainWindow
                        from desktop.settings import RuntimeLLMConfig
                        patches.enter_context(patch("desktop.credentials.CredentialStore.get", return_value=""))
                        patches.enter_context(patch("desktop.main_window.load_settings", RuntimeLLMConfig))
                        patches.enter_context(patch("desktop.widgets.settings_page.load_settings", RuntimeLLMConfig))
                        window = MainWindow()
                    else:
                        window = QWidget()
                        window.resize(900, 500)
                    window.setWindowTitle("Antibody Qt native diagnostic - " + mode)
                    timer = QTimer()
                    timer.setInterval(10)
                    timer.timeout.connect(lambda: ticks.append(True))
                    phase = "window_show"
                    window.show()
                    phase = "event_loop"
                    timer.start()
                    QTimer.singleShot(duration, window.close)
                    QTimer.singleShot(duration + 5000, lambda: app.exit(91))
                    result = app.exec()
                    phase = "after_exit"
                    closed = not window.isVisible()
    finally:
        assert kernel.RemoveVectoredExceptionHandler(handler), "Could not remove diagnostic observer"

    kernel.GetModuleHandleExW.argtypes = [W.DWORD, C.c_void_p, C.POINTER(W.HMODULE)]
    kernel.GetModuleFileNameW.argtypes = [W.HMODULE, W.LPWSTR, W.DWORD]
    # Verify that the captured PC and exported API are in the *same* x64
    # unwind-function entry, not merely near one another. No symbol server.
    class RuntimeFunction(C.Structure):
        _fields_ = [("begin", W.DWORD), ("end", W.DWORD), ("unwind", W.DWORD)]

    lookup = kernel.RtlLookupFunctionEntry
    lookup.argtypes = [C.c_ulonglong, C.POINTER(C.c_ulonglong), C.c_void_p]
    lookup.restype = C.POINTER(RuntimeFunction)
    provider_api = None
    provider_key = None

    def function_key(address):
        image = C.c_ulonglong()
        entry = lookup(address, C.byref(image), None)
        if not entry:
            return None
        record = entry.contents
        # Optimized Windows functions can have a small exported prologue and
        # chained body records. Follow documented UNW_FLAG_CHAININFO instead
        # of assuming one contiguous public function entry.
        for _ in range(8):
            header = C.string_at(image.value + record.unwind, 4)
            flags, count = header[0] >> 3, header[2]
            if not flags & 4:
                return (image.value, record.begin, record.end)
            offset = 4 + ((count + 1) & ~1) * 2
            record = C.cast(image.value + record.unwind + offset,
                            C.POINTER(RuntimeFunction)).contents
        return None

    if events:
        uia = C.WinDLL("UIAutomationCore")
        provider_api = C.cast(uia.UiaReturnRawElementProvider, C.c_void_p).value
        provider_key = function_key(provider_api)

    def frame_info(address):
        module = W.HMODULE()
        if not kernel.GetModuleHandleExW(6, address, C.byref(module)):
            return {"unmapped": hex(address)}
        name = C.create_unicode_buffer(32768)
        kernel.GetModuleFileNameW(module, name, len(name))
        basename = Path(name.value).name
        frame = {"module": basename, "offset": hex(address - module.value)}
        if basename.lower() == "uiautomationcore.dll" and provider_key:
            if function_key(address) == provider_key:
                frame["uia_return_raw_provider"] = True
                frame["api_displacement"] = hex(address - provider_api)
        return frame

    for event in events:
        event["frames"] = [frame_info(address) for address in event.pop("addresses")]
    payload = {"mode": mode, "qt": qVersion(), "python_version": list(sys.version_info[:3]),
               "exit_code": result, "closed": closed,
               "heartbeat_count": len(ticks), "fault_handler": faulthandler.is_enabled(),
               "observer_healthy": not observer_errors, "observer_errors": observer_errors,
               "heartbeat_after_last_com": len(ticks) - events[-1]["heartbeat_at_event"] if events else None,
               "native_trace_version": 1, "events": events,
               "product_imported": any(n == "desktop" or n.startswith("desktop.") for n in sys.modules)}
    print(RESULT_PREFIX + json.dumps(payload), flush=True)
    return result


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--mode", choices=("qt_only", "project"), default="qt_only")
    parser.add_argument("--duration-ms", type=int, default=1000)
    parser.add_argument("--child", action="store_true", help=argparse.SUPPRESS)
    args = parser.parse_args()
    if not 200 <= args.duration_ms <= 30000:
        parser.error("duration must be between 200 and 30000 ms")
    if os.name != "nt":
        parser.error("native diagnostic requires Windows")
    if args.child:
        return run_child(args.mode, args.duration_ms)
    command = [sys.executable, "-X", "faulthandler", "-B", str(Path(__file__).resolve()),
               "--child", "--mode", args.mode, "--duration-ms", str(args.duration_ms)]
    child = subprocess.run(command, capture_output=True, timeout=args.duration_ms / 1000 + 20)
    # Preserve original streams verbatim; the structured decision is additional.
    sys.stdout.buffer.write(child.stdout)
    sys.stdout.buffer.flush()
    sys.stderr.buffer.write(child.stderr)
    sys.stderr.buffer.flush()
    payload = None
    for line in child.stdout.decode("utf-8", "replace").splitlines():
        if line.startswith(RESULT_PREFIX):
            payload = json.loads(line[len(RESULT_PREFIX):])
    decision = classify_probe(child.returncode, payload, child.stderr.decode("utf-8", "replace"))
    print("QT_NATIVE_DECISION=" + json.dumps(decision), flush=True)
    return 0 if decision["status"] in {"CLEAN", "REVIEWED_UIA_COM_DIAGNOSTIC"} else 1


if __name__ == "__main__":
    raise SystemExit(main())
