# Windows Qt startup / COM diagnostic audit

Latest disposition: **UIA/COM native path reproduced and reviewed**, not a
demonstrated product crash. The historical non-reproduction below is retained;
the native-trace follow-up at the end supersedes that earlier uncertainty.

Scope: distinguish the previously logged diagnostic from an application crash.
No production startup, scientific rule, Provider or system setting is changed.

## Original observation

One Windows-platform pytest run printed `Windows fatal exception: code
0x8001010d` while showing the MainWindow fixture. It continued, passed all
eight cases and exited 0. This was a diagnostic, not an observed termination;
its triggering native caller was not captured. The original record is retained.

[Microsoft's COM error reference](https://learn.microsoft.com/en-us/windows/win32/com/com-error-codes-3)
identifies `0x8001010D` as `RPC_E_CANTCALLOUT_ININPUTSYNCCALL`: a restriction
on an outgoing call during synchronous input dispatch. The code alone does
not identify which module/client made the call.

[CPython 3.13.9's handler](https://github.com/python/cpython/blob/v3.13.9/Modules/faulthandler.c)
prints the fatal-exception heading and then returns
`EXCEPTION_CONTINUE_SEARCH`, allowing subsequent handlers to run. Therefore
the heading alone cannot establish that this process terminated. This is an
interpretation of the handler plus the observed exit 0, not proof of which
component ultimately handled the native exception.

## Controlled checks

Local runtime: Anaconda Python 3.13.9, PySide6 6.9.2, Qt 6.9.2, Windows.
All runs retained faulthandler. No exception filtering, disabled accessibility,
disabled pytest fault plugin, Windows setting change or dependency update was
used. No test result or stderr was suppressed to make a run pass.

| Probe | Result |
|---|---|
| Standalone minimal QWidget, no product imports, timed close | Event-loop exit 0, no diagnostic |
| Standalone MainWindow, mock configuration and no credential access, timed close | Event-loop exit 0, no diagnostic |
| Windows Qt integration acceptance, first recheck | 8 passed in 1.71 s, no diagnostic |
| Repeat in fresh process 1 | 8 passed in 1.64 s, no diagnostic |
| Repeat in fresh process 2 | 8 passed in 1.65 s, no diagnostic |
| Repeat in fresh process 3 | 8 passed in 1.69 s, no diagnostic |
| New child-process startup regression, Windows platform | 2 passed in 1.56 s; both event loops produced heartbeats, closed, exit 0, no fatal/traceback output |

`tests/test_desktop_startup.py` codifies the Qt-only / project comparison in
fresh child processes, independent of pytest's parent QApplication. It checks
the fault handler remains enabled, event-loop heartbeat, clean close, return
code and diagnostic stderr. Real Provider credentials are never consulted.
The existing user's Desktop process is not closed or overwritten.

From the repository root, the Windows-platform probes can be repeated with:

```powershell
$env:QT_QPA_PLATFORM = 'windows'
$env:PYTHONDONTWRITEBYTECODE = '1'
python -m pytest -s -p no:cacheprovider tests/test_desktop_startup.py tests/test_desktop_acceptance.py
```

The normal suite remains offscreen and does not depend on native mouse input.

## Decision and limitations

- **Startup, responsive event loop and controlled background close: PASS**
  in the examined configuration.
- **Original COM diagnostic: NOT REPRODUCED; native origin UNCONFIRMED.**
  No reproducible production defect has been established, so a speculative
  production workaround is not applied. Recurrence should retain the complete
  log, process exit code and native call stack before attributing a cause.
- The former Computer Use geometry/capture failures are separate observations.
  They do not establish a causal link to this COM diagnostic.
- Native OS mouse acceptance remains unverified. Qt QTest/child-process tests
  are evidence about app behavior, not a successful native mouse automation run.
- A finite set of clean runs does not guarantee this intermittent diagnostic
  can never recur or establish behavior under every Windows/Qt/runtime version.

## Native-trace follow-up — 2026-10-17

The later visible background-close acceptance reproduced the same message.
Its process still exited 0 and kept responding while awaiting its worker.
Rather than suppressing the message or changing production startup, a separate
diagnostic observer captured the first-chance native stack. The observer always
returns `EXCEPTION_CONTINUE_SEARCH`; faulthandler stays enabled. It is test-only,
not imported by the application or distributed in the wheel.

### Observed native path

Windows 10 build 19045, official CPython 3.13.9, PySide6/Qt 6.12.0:

```text
Windows synchronous window message
  -> qwindows.dll
  -> UIAutomationCore!UiaReturnRawElementProvider + 0xd8
  -> Windows combase / RPCRT4
  -> RpcRaiseException / RaiseException (0x8001010d)
```

The stack is captured from the observing callback, so its youngest frames also
contain ctypes/libffi/Python observer frames. Those are not attributed as the
origin. Local export symbol names alone can be approximate for private code;
the final tool verifies the UIA API frame against its x64 unwind-function
metadata, following chained records, not merely a nearby exported address.

The same native path occurs in an **empty QWidget with no product import,
background worker, status bar, credential lookup, rule engine or model**. Its
accessibility tree remains readable, its event timer fires and it exits 0.
Thus product-specific code and background work are not necessary conditions.
The initiating UIA client is not identified: this is not proof that Codex,
another accessibility client, or a particular Qt version is exclusively at fault.

[Qt 6.12's own handler](https://github.com/qt/qtbase/blob/v6.12.0/src/plugins/platforms/windows/uiautomation/qwindowsuiaaccessibility.cpp)
calls this API when serving `WM_GETOBJECT`.
[Microsoft's API contract](https://learn.microsoft.com/en-us/windows/win32/api/uiautomationcoreapi/nf-uiautomationcoreapi-uiareturnrawelementprovider)
describes the same provider handoff. Together with the captured trace and
normal continuation, the examined events are reviewed as handled native
UIA/COM diagnostics, not demonstrated Python/application crashes. That
conclusion does **not** apply to every occurrence of this numeric code.

### Controlled results

| Probe | Native COM events | Outcome |
|---|---:|---|
| Three short Qt-only runs | 0 each | Exit 0, heartbeat, closed, fault handler enabled |
| Three short full-project runs | 0 each | Same |
| One short event-loop-deferred show | 0 | Same; no evidence this is a necessary production fix |
| Full project, local background task + status bar, accessibility read | 1 | 1,987 heartbeats, exit 0, closed |
| Empty QWidget, independent native trace + accessibility read | 1 | 2,000 heartbeats, exit 0, no product imported |
| Final diagnostic tool, empty QWidget + accessibility read | 1 | 1,999 heartbeats after the exception, observer healthy, exit 0; REVIEWED_UIA_COM_DIAGNOSTIC, clean=false |
| Final diagnostic tool, full project | 1 | 1,999 heartbeats after the exception, observer healthy, exit 0; same reviewed status, clean=false |

The first tool revision rejected the UIA frame because it assumed one
contiguous unwind entry. This failure is retained, not counted as success.
The Windows DLL separates this API's prologue and body with chained unwind
records. Parsing was corrected according to
[Microsoft's x64 unwind documentation](https://learn.microsoft.com/en-us/cpp/build/exception-handling-x64),
then both final native probes verified the API frame. No code-only whitelist
or arbitrary address-range fallback was substituted.

### Reproducible diagnostic, not a production workaround

From a Windows x64 environment that can import the project's PySide6:

```powershell
python tests/qt_startup_diagnostic.py --mode qt_only --duration-ms 20000
python tests/qt_startup_diagnostic.py --mode project --duration-ms 20000
```

The window auto-closes. An accessibility client can inspect it while open;
the diagnostic is intermittent, so absence of an event in one run does not
prove elimination. Use an official standalone Python environment if the
separate Anaconda/ICU collision prevents importing the selected Qt version.
The project mode uses temporary Mock settings and patches credential access;
no Provider, Literature request, scientific analysis or model call is made.

Original child stdout and stderr are written verbatim. A separate structured
decision has three possible statuses:

| Status | Required evidence |
|---|---|
| CLEAN | Exit 0, responsive heartbeat, window closed, fault handler enabled, no stderr or captured native event |
| REVIEWED_UIA_COM_DIAGNOSTIC | Same health evidence, healthy observer, heartbeat after the exception, only the exact COM diagnostic grammar, matching event count, verified ordered RPC/COM/UIA/qwindows/USER32 chain and API frame |
| FAIL | Missing or different evidence, another exception, extra/unreviewed stderr, traceback, no heartbeat, unclosed window or nonzero exit |

The reviewed status is explicitly **not CLEAN**. The tool does not catch and
resume the exception, replace stderr, disable accessibility, change COM/thread
settings, patch Qt, downgrade dependencies or change production startup.
The existing strict `test_desktop_startup.py` assertions are unchanged. An
unrecognized future path still fails for review. Raw Python stack output can
contain local paths; do not publish it without a separate privacy review.

### Regression and disposition

- New classification regressions: 35 passed; genuine crashes and unknown
  diagnostics remain failures, and classification does not mutate evidence.
- Windows startup plus classification checks: 37 passed (1.42 s).
- Full application suite: 700 passed, 7 deselected, 5 warnings (11.18 s).
- The first full-suite attempt had 625 passed and 73 fixture-setup errors from
  access denied on a pre-existing pytest temporary directory. A new unique
  `--basetemp` resolved the environment issue; test assertions were not relaxed.
- ML runtime regressions: 10 passed (2.17 s).
- Full validation suites: 185 passed (208.06 s), including external-family
  and external-developability regression tests. No new experimental analysis
  or frozen-model training is performed by this diagnostic investigation.
- `git diff --check`: pass; existing CLI/manual/batch file hashes unchanged.

This closes the **unexplained-product-crash attribution** for the observed
trace, not the Windows diagnostic's existence. Its continued appearance is
preserved as a reviewed environment/runtime diagnostic. No production fix is
justified by the examined evidence; full official-installer/venv acceptance is
still a separate release task. Scientific core, models, thresholds, Provider
behavior and preserved local files remain unchanged. No commit or push is
performed as part of this investigation.

### Official Python 3.14 follow-up — 2026-10-18

The user-authorized repair restored the machine's stale independent Python
3.14.5 installation without replacing Anaconda. A new non-system-site-packages
venv installed the committed snapshot's Desktop extra from official PyPI.
Short installed-entry startup/close is clean (exit 0, 32 heartbeats, empty
stderr, System32 ICU). The longer visible run remains a functional PASS but
has one COM diagnostic; its original 427-byte stderr is preserved.

The same event was independently captured in an observed empty QWidget with
no product import: verified UIA return-provider frame, ordered RPC/COM/UIA/
qwindows/USER32 chain, 2,903 post-event heartbeats and exit 0. The original
classifier conservatively rejected Python 3.14's additional C-stack text;
that FAIL is retained. CPython's [3.14.5 traceback implementation](https://github.com/python/cpython/blob/v3.14.5/Python/traceback.c)
emits the exact two-line unavailable-C-stack fallback found in this log.

Only the opt-in test classifier was extended to recognize that exact fallback
with a Python 3.14 version payload and all existing health/native requirements.
Arbitrary C frames and other errors still fail; there is no broad stderr filter.
It does not disable `c_stack`, faulthandler, COM or accessibility. Original
streams are not rewritten, and production startup/strict startup tests are
unchanged. Seventeen additional positive/negative cases bring classification
tests to 52 passed in the new official-Python venv.

A fresh full-Desktop observer run captures the same verified API frame
(`+0xd8`) with 3,000 post-event heartbeats, healthy observer and normal close/
exit 0. Its strict decision is `REVIEWED_UIA_COM_DIAGNOSTIC`, **not CLEAN**.
This confirms the reviewed path in the new environment, not elimination or
the identity of the initiating accessibility client.

Latest application regression: 717 passed, 7 deselected, 5 warnings (13.68 s).
New-environment Desktop acceptance/startup: 10 passed (2.36 s). Frozen runtime:
10 passed (2.03 s). Full validation's 185-pass result above is historical, not
rerun here. See `RELEASE_ACCEPTANCE_2026-10-17.md` for installation provenance,
the temporary PATH preservation failure/restoration and release boundaries.

### Exact 3.14.8 candidate follow-up — 2026-10-18

The independent installation was subsequently updated to verified official
CPython 3.14.8, with Anaconda and persistent PATH unchanged. New scoped
preflight and versioned-candidate regressions each passed 677 cases, with two
absent-LangChain skips, seven live deselections and two warnings; legacy
training/fitting modules were excluded in advance. Twelve offline frozen-rule/
runtime/documentation compatibility cases passed before and after versioning.

A native observer on exact 3.14.8 captured one reviewed UIA/COM event, normal
exit, healthy observer, 2,999 heartbeats and 2,665 after the event. The actual
installed 4.1.0rc1 short entry run had empty stderr and exit 0. Its longer
visible run remained responsive for 4,500 heartbeats and exited 0 but retained
the diagnostic: functional PASS, not CLEAN; that particular uninstrumented
run has no observer stack of its own. Nothing was suppressed or fixed in
production startup. See the [candidate audit](RELEASE_CANDIDATE_4_1_0RC1_AUDIT.md)
for actual artifact/version provenance and the remaining publication gates.
