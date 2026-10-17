# Windows Qt startup / COM diagnostic audit

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
