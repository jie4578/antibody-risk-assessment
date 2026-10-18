# Post-checkpoint release acceptance — 2026-10-17

Latest follow-up, 2026-10-18: exact CPython 3.14.8 base-Desktop acceptance and
local 4.1.0rc1 wheel/sdist preparation are complete. See the
[candidate audit](RELEASE_CANDIDATE_4_1_0RC1_AUDIT.md). Earlier attempts and
environment-specific results below remain chronological evidence.

Audited source checkpoint: `fbc47eae0b898a6afba2f06b2af949616beac568`.
The initial acceptance work kept metadata at 4.0.0 and created no release,
tag, model or performance result. A later explicit authorization permitted
the exact-3.14.8 checks and 4.1.0rc1 metadata/build follow-up linked above;
it still creates no public release or tag. Production behavior is unchanged.

## Assisted real Windows acceptance

The user operates the real Windows Desktop. Codex reads the live accessibility
tree and the user's copied Summary text. These checks are distinct from the
earlier Qt QTest cases and are not called successful native mouse automation.
Screenshot capture previously timed out; keyboard injection was stopped after
the helper repeatedly detected user input. No alternate injection API bypass
is used.

| Check | Observed evidence | Status |
|---|---|---|
| Overlapping NNST candidates | Real Summary: `overlap_v2`, score 73, four total sites; NNS@1–3 and NST@2–4, plus NS@2–3 and NN@1–2 | PASS |
| Duplicate-ID transfer to Single | Two synthetic CSV rows: DUP/NNST/ACD and DUP/AAANVSTT/MMM. Display sorted by score; user selected VH length 8. Live Single input is AAANVSTT, not the other same-ID sequence | PASS |
| Duplicate-ID VL transfer | User selected displayed VH-length-4 row and VL. Live Mutation input is ACD, chain VL, not MMM | PASS |
| Mutation edit invalidation | User reported simulating A1M on ACD, then editing to A1V without simulating again. Live UI shows A1V, cleared original/mutant/comparison values, disabled Add Candidate and ML Comparison | PASS |
| Matching mutation attachment | Copied real Summary contains N4Q, VH, baseline 91, mutant 100, delta 9, one removed site, `overlap_v2`; current VH is AAANVSTT | PASS |
| Cross-sample Summary isolation | User changed only Single antibody ID to OTHER-DUP, sequence unchanged. Rebuilt Summary excludes N4Q and records an identity/sequence/chain mismatch evidence gap | PASS |
| Stale Summary blocking after a new input/transfer | Live Single view after transfer retains the old text but marks it Outdated; Explain with AI and View AI Context are disabled | PASS |
| Literature non-title-column selection | User selects first result through Year/DOI cell. Live detail title and PMID 36018377 match that result; Send Evidence and Open Source enabled | PASS |
| Literature query edit invalidation | Query changed to antibody aggregation without Search: old rows/details cleared, both actions disabled, Found 10 replaced by Search inputs changed prompt | PASS |
| Empty literature query | Empty Query: Enter a query, then click Search; actions remain disabled | PASS |
| Normal original Desktop close | User reports no error; original Desktop process exits 0 | PASS |
| Close during real literature search | User did not see Searching; results arrived too quickly to perform the requested active-work close | INCONCLUSIVE, not a failure or PASS |
| Manual close with controlled local background work | User closes the confirmed visible test window. Close observed; 80 timer heartbeats while closing; controls disabled; queued calls and published results empty; no timeout; exit 0 | FUNCTIONAL PASS; startup diagnostic remains |

The short synthetic sequences test UI state and rule-candidate enumeration.
They are not biological antibody validation or evidence of experimental effects.
The two duplicate-ID transfer checks above sample two real workflows; the
six-path exhaustive row/Single/VH/VL coverage remains Qt integration evidence.

## Fresh package installation

A source ZIP was generated with `git archive HEAD`, not from the dirty working
tree. An offline wheel build used that snapshot. The wheel therefore includes
the committed CLI source, not the preserved local CLI modifications.

- Wheel: `antibody_risk-4.0.0-py3-none-any.whl`, 180,546 bytes, 81 members.
- Wheel SHA256: `afff4278939a49d5c33f272194a3d87a8b1994b55189959e508d6f78231f6049`.
- Fresh venv has no system site packages. Wheel `[desktop]` dependencies were
  installed from the official PyPI index; `pip check` found no broken requirements.
- Resolved versions include Python 3.13.9, PySide6 6.12.0, Gradio 6.30.0,
  NumPy 2.5.4, pandas 3.0.6, SciPy 1.18.1, scikit-learn 1.9.1 and OpenAI 3.33.0.
  This records the observed resolver result, not a new dependency pin.
- Wheel inspection found no validation package, raw XLSX, NPZ, joblib, database,
  private-key files, `.env` or model-artifact directory. Wheel core/scoring and
  both CLI files match the committed checkpoint (line-ending-normalized).
- CLI console-entry `--help` exits successfully. No training/prediction command
  was invoked.

### Default Anaconda-derived venv failure, preserved

The initial venv uses Anaconda Python 3.13.9 as its base interpreter. Importing
PySide6 QtCore/QtWidgets fails with Windows error 127 (specified procedure not
found), including with a minimal process-local PATH. `pip check` alone did not
detect this native dependency failure.

Read-only PE-import/export inspection found that Qt6Core requires unversioned
`ucnv_*` procedures. The loaded Anaconda ICU 73.1 `icuuc.dll` lacks those names;
Windows System32 ICU 64.2 exports them. In a disposable diagnostic process only,
preloading the system DLL allowed full MainWindow startup, heartbeat and clean
exit (exit 0; fault handler enabled). This does not turn the original default
launch into a PASS.

No system DLL, PATH, registry setting, existing Python installation or production
startup code was changed. No speculative production DLL-loader workaround or
dependency downgrade was added.

### Visible background-close follow-up

The first controlled background-close process was not targetable on the user's
visible desktop. The original Desktop, not that diagnostic process, was closed.
The diagnostic's own safety timeout then fired: no manual close was observed,
its local worker completed, and its assertions failed. This is retained as an
invalid acceptance attempt, not a passing shutdown test and not evidence that
result suppression failed after an actual user close. An attempt to stop only
the owned temporary process reported an error; its later timeout output is the
actual disposition.

A separately launched visible controlled window is confirmed in the native
window inventory. This visible run emitted `Windows fatal exception: code
0x8001010d` while executing `window.show()`, with the fault handler enabled.
The process continued and the window remained targetable. Unlike the clean
short startup probes below, this visible run is **not clean**. This reproduces
the previously recorded diagnostic under a new isolated runtime, without
establishing its native caller or proving that the application crashed.
The user then closed that confirmed visible window and reported a pale/white
appearance followed by exit after a few seconds. Independent process output:

```json
{"close_seen": true, "heartbeat_while_closing": 80,
 "disabled_while_closing": true, "timed_out": false, "exit_code": 0,
 "closed": true, "worker_entered": true, "queued_calls": [],
 "published_results": [], "fault_handler": true}
```

The local worker is deliberately released about five seconds after the close
request so the real MainWindow close handler must wait. Its event-loop timer
continues firing; queued work and result delivery are suppressed. This is a
functional shutdown PASS, not a claim that the startup diagnostic disappeared,
nor a test of real Provider cancellation or network timeout behavior. No
fault-handler suppression, COM configuration change or production workaround
is applied.

### Official CPython control

To isolate the base interpreter, the official Python 3.13.9 x64 embeddable ZIP
was downloaded from the [Python release page](https://www.python.org/downloads/release/python-3139/)
into the temporary acceptance directory. The same minor/patch version is used
as a controlled comparison, not as a recommendation to deploy an old Python.

- ZIP SHA256: `91d828c2da3a029b41699e918674a0cb379c02cf20dab9c501306885f837402a`.
- SHA256 matches the digest in the official Sigstore bundle; the complete
  Sigstore certificate/transparency proof was not independently verified.
- ZIP MD5 matches the official release-page value; extracted `python.exe`
  Authenticode status is Valid, signer Python Software Foundation.
- Only the temporary portable interpreter's `_pth` file was configured to read
  the newly installed audit venv site-packages. It does not read the repository
  or original Anaconda site-packages. This reuses the same fresh dependency
  installation; it is not a second full installer/venv installation test.

With that official interpreter, without system-DLL preloading:

| Probe | Result |
|---|---|
| QtCore/QtWidgets import | PASS, Qt 6.12.0 |
| Installed core/scoring/config/Summary/runtime/Agent imports, isolated mode, no source-checkout fallback | PASS |
| NNST overlapping candidates and Summary preservation | PASS |
| Copilot metadata-type contradiction guard | PASS |
| Missing local ML artifacts | MODEL_ARTIFACTS_MISSING; UI reports unavailable, no worker or prediction call |
| Full Windows MainWindow startup, event-loop heartbeat, timed close | PASS, exit 0, fault handler enabled, no fatal diagnostic |
| Gradio page construction | PASS, model/RAG caches uninitialized, no training |
| Runtime dependency on `validation` | NONE loaded |
| External socket connection attempts during runtime probes | 0; test guard permits only local loopback for Windows asyncio |

A separate loaded-module check confirms the official interpreter resolves
`icuuc.dll` to Windows System32 and has no Anaconda entry in `sys.path`.
`pip check` also passes when invoked with this official interpreter against
the same fresh dependency installation.

Qt's [Windows support table](https://doc.qt.io/qt-6.12/windows.html) includes
Windows 10 1809 or later. The observed host is Windows 10 build 19045; the
identified ICU collision should not be described as Windows 10 being unsupported.

## Full installer / fresh venv follow-up — blocked before venv creation

This follow-up selected the official Python 3.13.16 Windows x64 full installer,
not the earlier embeddable ZIP. The [official release page](https://www.python.org/downloads/release/python-31316/)
lists its SHA256. The downloaded installer is 29,935,584 bytes; its SHA256 is
`fb4f9f5d438b2396da0086dc70b935c530cb578e37adc6d354f7ad2037fee83b`,
and Windows Authenticode reports Valid, signer Python Software Foundation.
These checks validate the acquired installer, not a successful installation.

A fresh `git archive HEAD` source snapshot was prepared from the same
`fbc47eae0b898a6afba2f06b2af949616beac568` checkpoint. Its ZIP SHA256 is
`3390312271e769578791aa04eebeac3fa555b35898b409b18f2f8d80a9b26169`.
No dirty CLI source, private data or model binaries
were copied into the snapshot. README's exact `py -3.10` command has not been
tested by this follow-up; selecting 3.13 is explicitly a version substitution.

Pre-install checks revealed two different Windows account contexts:

- The restricted test account has no registered Python interpreter. Its initial
  `py -0p` output must not be generalized to the real desktop account.
- The desktop account's Python 3.13 install registration points to Anaconda.
  A precondition check stopped the privileged command **before** it executed
  the installer, to avoid overwriting that existing registration.
- The desktop account also lists Python 3.14, but the registered executable
  does not exist. This is a stale registration, not an available standalone
  interpreter. No registration was repaired or removed.
- Running the verified installer only in the isolated test account, with a
  separate target directory and no PATH/association/launcher/shortcut changes,
  returned exit code 5. Its preserved log reports `0x80070005`: access denied
  creating the bundle's per-user Package Cache directory, followed by failure
  to begin registration/cache the bundle. The target `python.exe` was not
  created. No permission or security setting was relaxed to bypass this.

The installer, source snapshot and raw failure log remain in a local temporary
acceptance directory, outside Git. No fresh venv, dependency installation,
CLI smoke or Desktop launch occurred in this attempt. There is no new
installation PASS and no newly rerun application/validation/runtime test
result. The earlier results below remain historical results, not results from
this uncreated environment.

Post-checks confirm that the desktop account's Python 3.13/3.14 registered
paths and both persistent PATH values are unchanged. Protected CLI, manual
workbook, core/scoring and batch-artifact hashes match their pre-check values;
the Git index remains empty. The failed installer log is retained, not
silently discarded.

Disposition: **BLOCKED_ENVIRONMENT / NOT_READY** for the full installation
gate. Continue on a clean Windows account/machine, or obtain explicit user
direction before repairing the stale standalone-Python installation. Do not
overwrite the Anaconda registration, install system-wide, or change PATH as
an implicit workaround. No release or version decision is made here.

## Release gate and boundaries

### Authorized standalone-Python repair follow-up — completed 2026-10-18

The user explicitly authorized repair of the stale standalone Python install,
without touching Anaconda. This supersedes the environment blocker above;
the failed initial attempt is preserved rather than rewritten as successful.

Read-only desktop-account inspection identified the stale install as Python
3.14.5 x64. Its complete target directory was absent, while its normal
per-user installer registration remained. The original cached bootstrapper
was PSF-signed but smaller than the full published installer; it was not
misrepresented as matching the published full-installer hash.

The same-version full installer was acquired from the [official release page](https://www.python.org/downloads/release/python-3145/):

- File: `python-3.14.5-amd64.exe`, 30,361,968 bytes.
- SHA256: `f9c09f5ed6f796fd1a8bc5ddfa41715a494b453c4781f0e35d5077cf9fa58f6d`.
- Official checksum matches; Authenticode Valid, signer Python Software Foundation.
- Command: `/repair /quiet /norestart /log <local-repair-log>`.
- Repair exit code: 0; restart: none. Interpreter, `venv` and `ensurepip`
  imports succeed; `py -3.14` resolves the restored standalone interpreter.

The repair's PATH component removed the two pre-existing standalone-Python
entries from the user's PATH. This preservation check initially **failed**.
After verifying the post-installer PATH was exactly the pre-recorded value
minus only those two entries (no concurrent change), those entries were
restored in their original positions. The final user PATH is byte-for-byte
the original value; system PATH never changed. No execution-policy, Windows
security, file-association or launcher workaround was applied.

The Anaconda executable SHA256 remains
`7679e53fa969789309e81fdad0d52b8cda5f83c9abf7cb31a3c58bf24b31e264`;
its Python 3.13 install registration is unchanged. No Anaconda package command
was run and no file in its installation was intentionally modified.

A newly created `venv314` uses this restored official Python 3.14.5 base,
with `include-system-site-packages = false`. PowerShell activation succeeds
without changing execution policy, and the resulting `python` points to the
new venv, not Anaconda. This is a same-version installation repair and a new
venv acceptance, not a new Windows-user installation or a claim that 3.14.5 is
the latest patch. The official page lists a newer 3.14 release; patch upgrading
is outside this exact-repair operation. README's specific Python 3.10 example
is not claimed to have been tested.

#### Fresh installation and bounded runtime results

The committed-source snapshot was installed non-editably with `.[desktop]`
into that empty venv. Dependency downloads came from official PyPI's
`files.pythonhosted.org`; the source install is the local committed snapshot.
Neither the old Anaconda-derived venv nor the embeddable control's packages
were reused. Build/install logs and pip's machine-readable report are retained
locally, not staged.

- Fresh wheel: `antibody_risk-4.0.0-py3-none-any.whl`, 183,008 bytes;
  build-reported SHA256:
  `c02ba410c08210251048599543ec1e3ad12ea90bd04d4f80b281104a4194572e`.
- Resolved versions: PySide6/Qt 6.12.0, Gradio 6.30.0, NumPy 2.5.4,
  pandas 3.0.6, SciPy 1.18.1, scikit-learn 1.9.1 and OpenAI 3.33.0.
  These are observed versions, not new production dependency pins.
- `pip check`: no broken requirements.
- Isolated installed-package imports resolve to the fresh site-packages,
  without an Anaconda or checkout fallback. Installed core/scoring and both
  CLI sources match the committed snapshot after line-ending normalization.
- Installed distribution inventory excludes validation datasets, `.env`,
  XLSX, NPZ, joblib, database and private-key artifacts.
- CLI console entry `--help`: exit 0. Initial piped output used a legacy
  encoding; process-local UTF-8 capture displayed Chinese correctly. No
  preserved CLI file was edited to change encoding.
- NNST overlap enumeration, Summary preservation and Copilot metadata-type
  contradiction guard: PASS. These are synthetic functional probes, not
  biological validation or new model-performance evidence.
- Missing models: `MODEL_ARTIFACTS_MISSING`; UI reports the unavailable local
  artifacts, no ML worker starts, and a prediction-call sentinel is never
  called. No model weights, datasets or frozen deployment artifacts were
  installed or rebuilt.
- Gradio page construction: PASS, model/RAG caches remain uninitialized.
- Short Windows Desktop entry-point run: exit 0, 32 timer heartbeats, normal
  close, fault handler enabled, empty stderr. Loaded ICU is Windows System32,
  without the diagnostic DLL-preloading workaround.
- Runtime probes block external socket connections and observed 0 attempts;
  loopback is allowed only for Windows asyncio's local socketpair. Desktop
  probes use isolated Mock settings and patched credential reads. This is a
  probe boundary, not a claim that all product features never use the network.

The longer visible installed-entry run was independently read through the
computer-use native accessibility API. It displayed SYNTHETIC-NNST, NNST/ACD,
score 73, overlap_v2 Summary including NNS@1–3 and NST@2–4, and the correct
missing-model message. It auto-closed with exit 0 and 3,681 heartbeats, but
emitted one `0x8001010d` diagnostic. Its 427-byte raw stderr remains retained:
this run is a functional PASS, **not CLEAN**, and that original uninstrumented
run has no captured native stack of its own.

#### Python 3.14 diagnostic review and regressions

An empty QWidget probe initially had no event and exited CLEAN; its automatic
close occurred before the attempted accessibility capture. A second observed
empty-window run captured one verified UIA/COM/RPC event, 2,903 post-event
heartbeats, normal close/exit 0 and no product import. Its then-current strict
classifier returned FAIL for the newly encountered Python 3.14 C-stack
fallback, and that original decision/log are retained unchanged.

CPython 3.14 adds C-stack dumping by default. Its [versioned traceback source](https://github.com/python/cpython/blob/v3.14.5/Python/traceback.c)
contains the exact unavailable-stack fallback observed here; the [official
faulthandler documentation](https://docs.python.org/3.14/library/faulthandler.html)
describes printing an error if the build cannot dump a C stack. The opt-in
test diagnostic now records Python version and accepts only that exact paired
fallback for verified Python 3.14 payloads. Other versions, malformed/missing/
repeated blocks, arbitrary C frames, extra errors, unverified native chains,
missing post-event responsiveness and nonzero exits still fail. Original
streams and the existing strict startup tests remain unchanged; production
does not import the classifier.

A new full-Desktop observer run with the restored interpreter independently
captured the same verified `UiaReturnRawElementProvider + 0xd8` frame in the
ordered RPC/COM/UIA/qwindows/USER32 chain. It exited 0 with 3,000 heartbeats
after the event and a healthy observer. Decision:
`REVIEWED_UIA_COM_DIAGNOSTIC`, `clean=false`. This reproduces the reviewed
environment/runtime diagnostic; it does not establish which external UIA
client initiated it or claim the diagnostic has been eliminated.

Latest checks (2026-10-18):

- New official-Python venv: 10 Desktop acceptance/startup tests passed (2.36 s),
  against the archived source; the separate isolated probes above exercise
  the installed package. A prior run of the same 10 cases also passed.
- Diagnostic-classification tests in that new venv: 52 passed (0.11 s),
  including 17 new Python 3.14 format/negative cases.
- Full application regression in the existing development environment:
  **717 passed, 7 deselected, 5 warnings** (13.68 s). This uses the existing
  Anaconda interpreter without installing/upgrading any of its packages.
- Frozen ML runtime regression in that existing environment: 10 passed
  (2.03 s), not live inference or retraining of the frozen models.
- Full validation's latest 185-pass result remains the earlier run below;
  it was not rerun for this test-only format/installation follow-up.
- Final preservation checks: user/system PATH, Anaconda binary/registration,
  protected CLI/manual/batch artifacts and core/scoring hashes remain as
  recorded. Git index is empty; HEAD is still the audited checkpoint.
  `git diff --check` and no-index whitespace checks on the new diagnostic
  source/tests and this report pass. No source, model or dataset is staged.

The supported standalone-CPython control passes the bounded installed-runtime
probes. Default launch in the Anaconda-derived fresh venv remains a recorded
environment incompatibility. The authorized full-installer repair and fresh
official-Python venv now pass the bounded Desktop installation workflow above,
with the visible COM diagnostic explicitly retained/reviewed. A pristine
Windows-user installation, README's exact Python 3.10 selection and optional
frozen-model-artifact provisioning are not claimed here.

The previous checkpoint's regression results were 665 application tests passed,
7 deselected, 5 warnings, and 185 validation tests passed. The initial
documentation-only acceptance did not rerun those suites. The subsequent
native COM investigation added 35 diagnostic-classification regressions and
reran the application suite: **700 passed, 7 deselected, 5 warnings** (11.18 s).
The validation suites passed **185** tests (208.06 s); ML runtime separately
passed **10** (2.17 s). Existing strict startup assertions were not relaxed.
Earlier real
Provider checks and their rejected response remain documented separately in
`DESKTOP_ACCEPTANCE_2026-10-17.md`.

The listed assisted functional acceptance checks are complete. Overall release
gate was initially NOT_READY pending review of the reproduced visible Windows
diagnostic. That review is now complete: native traces reproduce the provider
handoff in an empty Qt window and full Desktop, with normal continuation and
exit. See `WINDOWS_QT_DIAGNOSTIC_2026-10-17.md` for the evidence and strict
test-only classification. The message is retained as a reviewed UIA/COM
diagnostic, not relabeled as a clean run or removed from logs. No production
startup or scientific behavior was changed.

The installation blocker is now closed within the stated repair/new-venv
scope: **READY_FOR_RELEASE_REVIEW**, not release authorization. Overall release
remains NOT_READY for publication until the version/release decision and
supported Python patch policy are explicitly resolved. The same-version repair
does not recommend deploying an old patch or erase the known COM diagnostic.
The 2026-10-18 [release decision](RELEASE_PLAN_V4_1.md) subsequently selected
v4.1.0 and CPython 3.14.8. The later authorized exact-patch acceptance and
candidate build are now complete as recorded in the candidate audit; the
five-file diagnostic scope expanded to 11 reviewed metadata/test/document
files. Remote exact-commit CI and publication authorization remain separate.
The diagnostic review alone does not authorize a release. No new
commit, push, tag or release is performed during this follow-up. Original local
CLI changes, manual workbook, batch artifacts, datasets and frozen models must
remain untouched.
