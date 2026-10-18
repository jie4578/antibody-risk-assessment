# 4.1.0rc1 / exact CPython 3.14.8 candidate audit

Date: 2026-10-18. Status: **BASE_DESKTOP_QUALIFIED / LOCAL_CANDIDATE_BUILT**.
This is not a published release, remote CI result, new Git commit or tag.

## Exact environment and acquisition

- Official standard-GIL CPython 3.14.8 x64, fresh venv with system site
  packages disabled. Runtime version and GIL state were asserted, not inferred
  from a launcher label or the earlier 3.14.5 test.
- [Official Windows full installer](https://www.python.org/downloads/release/python-3148/):
  `python-3.14.8-amd64.exe`, 33,387,464 bytes; SHA256
  `759be887b96e736a3ca886daf8d575f18fcae1a09efab6902f42d59e8999f8ef`.
  Official checksum matches; Windows Authenticode Valid, Python Software Foundation.
- Updated only the already-repaired independent per-user installation from
  3.14.5 to 3.14.8. Installer exit 0, no restart. Existing Anaconda executable
  hash and registration, user PATH and machine PATH remained unchanged.
- OpenSSL runtime: 3.5.9. Observed dependency versions include PySide6/Qt
  6.12.0, Gradio 6.30.0, OpenAI 3.35.1, NumPy 2.5.4, pandas 3.0.6,
  SciPy 1.18.1 and scikit-learn 1.9.1. These are resolver observations, not
  new dependency pins. Test/build tools were installed only in the new venv.
- Official PyPI installation had transient metadata-download timeouts that
  retried successfully. Original installer/pip/build/diagnostic logs and pip
  JSON reports remain locally outside the commit allowlist.

The fresh venv first installed the committed 4.0.0 snapshot for exact-patch
preflight. Version metadata was changed only after that scoped gate passed.
The resulting candidate wheel then replaced that package in the same fresh
venv, without changing dependencies, for actual installed-candidate checks.

A second fresh standard-GIL 3.14.8 venv then installed the **final wheel's
`[desktop]` dependencies only**, offline from a separately resolved wheelhouse.
It has no pytest, matplotlib, build, Bio, torch, transformers or LangChain.
`pip check`, isolated installed imports/source comparisons, CLI `--help`, Gradio
construction and the actual installed Desktop entry/close all passed. This
separates source regression in the test/build venv from minimal runtime checks;
development dependencies were not used to mask missing Desktop requirements.
The minimal runtime Desktop run exited 0 with 32 heartbeats, System32 ICU and
zero external socket attempts or model predictions. It emitted 0x8001010d:
functional PASS, **not CLEAN**; original stdout/stderr and the offline pip JSON
installation report are retained locally. No native observer stack was collected
for this additional run, so its code alone is not a stack-level classification.

## Candidate source boundary

Clean base: `fbc47eae0b898a6afba2f06b2af949616beac568`, exported by
`git archive HEAD`. Explicit candidate-source overlays only:

- `pyproject.toml` — `4.1.0rc1`; Python compatibility floor remains `>=3.10`.
- `README.md` — candidate identity, qualified base profile and scope.
- `MANIFEST.in` — include diagnostic test helper and new release notes in sdist.
- `docs/RELEASE_NOTES_V4_1.md` — candidate scientific boundary and limitations.
- `tests/qt_startup_diagnostic.py` and `tests/test_qt_startup_diagnostic.py`.

Every other exported source file was byte-compared with the clean base archive.
The candidate-source manifest digest is
`9e73305324b299f897196ca1fd21e83c8753545a92700b913e7dea4798d10d11`.
The artifact manifest records per-source-file SHA256 values and the exact
overlay list. This is an explicitly uncommitted candidate source, not a claim
that HEAD already contains those overlays. Later acceptance/planning reports
are review evidence outside this sealed build-input overlay list.

Dirty `cli.py` and `literature/cli.py` were never copied into candidate source.
Both packaged CLI files match the committed base. Raw data, local models,
embeddings, credentials, manual workbook and generated batch files were not
added to the candidate source or archives.

## Exact-patch and post-version checks

Scope was fixed before execution: ordinary non-live application tests except
`test_ml.py` and `test_rag.py`, which execute training/fitting workflows.
No failure was hidden by later excluding a test. Two LangChain adapter cases
skip because the optional package is absent; seven live cases are deselected.
Desktop ML tests use deterministic fakes, not the frozen model binaries.

| Check | Exact result |
|---|---|
| Clean-base exact-patch source preflight | 677 passed, 2 skipped, 7 deselected, 2 warnings (6.37 s) |
| Clean-base offline frozen-rule/runtime/documentation compatibility subset | 12 passed (1.31 s) |
| Versioned candidate source, same no-training profile | 677 passed, 2 skipped, 7 deselected, 2 warnings (6.28 s) |
| Versioned candidate offline compatibility subset | 12 passed (1.24 s) |
| Candidate wheel install + `pip check` | PASS, package 4.1.0rc1, no broken requirements |
| Isolated installed imports and source comparison | PASS; site-packages only, no checkout/Anaconda fallback; no validation runtime import |
| CLI console entry `--help` | Exit 0; no training or prediction command invoked |
| Gradio construction | PASS; model/RAG caches uninitialized |
| Installed rule/Summary/Copilot guard probe | PASS; synthetic NNST overlapping candidates and typed metadata preserved |
| Missing-model handling | MODEL_ARTIFACTS_MISSING; correct UI message; no worker/prediction call |
| Installed candidate Windows short entry/close | Exit 0, 33 heartbeats, faulthandler enabled, empty stderr, System32 ICU |

One post-version pytest invocation initially failed argument validation before
test collection because PowerShell did not expand its `--basetemp` expression
as intended. The command was corrected to literal paths and rerun; the two
post-version results in the table are the actual completed runs, not an
assertion failure reclassified as passing. Local test XML/logs are retained.

The unrestricted 717-pass development regression and full 185-pass validation
result in the earlier acceptance report remain historical, not this exact
3.14.8 no-training profile. Optional ESM2/ML/CUDA/all-extra environments and
real Provider requests are not newly qualified here.

## Native Windows evidence

The actual candidate installation's visible window was independently read
through computer-use accessibility APIs: synthetic NNST/ACD input, score 73,
NNS@1–3 and NST@2–4 in the overlap_v2 Summary, unavailable-model message and
offline Mock disclosure. Inputs/actions were prepared by the owned Qt probe;
this is a native accessibility observation, not a native mouse-button test.

It auto-closed normally with exit 0, 4,500 timer heartbeats, faulthandler still
enabled, no external socket attempts and no model prediction. It emitted the
known COM diagnostic: this visible run is a functional PASS, **not CLEAN**,
and has no native observer stack of its own. Its original stderr is retained.

A separate native observer run in the same exact 3.14.8 environment, before
version metadata changed, captured the reviewed ordered RPC/COM/UIA/qwindows/
USER32 path and verified UiaReturnRawElementProvider frame. It closed with
exit 0, healthy observer, one event, 2,999 heartbeats and 2,665 after the event.
Decision: `REVIEWED_UIA_COM_DIAGNOSTIC`, `clean=false`. Production code is
byte-identical between that source snapshot and the installed candidate.
This does not identify the initiating accessibility client or exempt every
future occurrence of the code. See the retained [native diagnostic audit](WINDOWS_QT_DIAGNOSTIC_2026-10-17.md).

Runtime probes block external sockets and observed zero attempts, permitting
only Windows asyncio loopback. Credentials/config were isolated and mocked.
No acquired experimental raw workbook, AIntibody TEST labels, model weights, live ESM
embeddings, predictions, training, threshold tuning or experimental performance
analysis were used or generated in this candidate preparation.

## Final artifacts and integrity

Artifacts are local under ignored `dist/4.1.0rc1/`:

| File | Bytes | SHA256 |
|---|---:|---|
| antibody_risk-4.1.0rc1-py3-none-any.whl | 183346 | 3a48b9076acdb0492bec65c270088fe47dc108a9732afbe4ae34e985938e4d9b |
| antibody_risk-4.1.0rc1.tar.gz | 223910 | b3926e9dc746c91f47a1ec60d62c0904b2cfa7f04109bef9ceafa9f7465432b3 |

`SHA256SUMS.txt` and `artifact_manifest.json` accompany them. Wheel has 81
files; sdist has 134. Both metadata records are version 4.1.0rc1 with Python
floor >=3.10. Archive inspection checks required runtime/config/license files,
forbids traversal/links and data/model/cache/credential binaries, compares
packaged Python source bytes, and verifies the sdist contains its referenced
diagnostic helper and the new release notes.

Initial artifacts were preserved locally before adding the explicit sdist
release-note entry. The final wheel is byte-identical to the installed/tested
wheel. Rebuilding a wheel from the **final sdist** with the recorded build tools
and `SOURCE_DATE_EPOCH=1792228153` also produces the exact same wheel SHA256.
This is observed local round-trip reproducibility, not a cross-machine or
future-dependency reproducibility guarantee. Build tools: build 1.6.1,
setuptools 84.0.0, wheel 0.48.0.

## Review, preservation and remaining gates

Production core/scoring, Desktop, Agent, ML inference, batch scientific logic
and validation source have no worktree changes in this phase. Protected CLI,
manual workbook and existing batch-artifact hashes match the prior record.
Generated distributions are ignored; index is empty. No commit/push/tag or
GitHub release was made. No original release tag or frozen result was changed.

The expanded prospective commit scope is release metadata, this report/new
release notes, the earlier diagnostic/acceptance/planning documents and two
diagnostic test files. Do not include the protected CLI files, manual/batch
workbooks, datasets, model/cache files, installer logs or distribution binaries.

- P0: no blocker found in the scoped local candidate checks.
- Publication gate: the exact future candidate commit still needs applicable
  remote Windows/Linux CI and explicit publication authorization. Local success
  is not a remote CI PASS. Optional-ML verified-environment claims stay limited.
- P2 follow-up: setuptools warns that the existing TOML license table is
  deprecated. MIT text/license file are retained; no license/backend-floor
  redesign was bundled into this version-only preparation. This warning is
  retained in build logs and should be addressed in a separately tested
  packaging change before the stated deprecation deadline.

Result: **EXACT_3_14_8_BASE_ACCEPTANCE_PASS / CANDIDATE_BUILD_PASS /
READY_FOR_SELECTIVE_COMMIT_REVIEW / NOT_PUBLISHED**.

## Subsequent selective-commit review — 2026-10-18

The user subsequently authorized selective commit/push and remote CI for the
candidate. The preceding sections retain their pre-commit/build chronology;
they do not claim a new Git commit or remote CI result at artifact-build time.

The 11-file allowlist in the release plan was re-reviewed for source scope,
scientific wording, bounded secret/profile-path patterns, whitespace and
conflict markers. No production/CI-workflow edits are included. Protected CLI,
data, generated distributions, model artifacts and local raw evidence stay
outside the commit. The opt-in diagnostic is not a production exception filter.

A repeat scoped regression initially omitted the workflow's dummy
`DEEPSEEK_API_KEY`: 9 mocked-Agent constructor cases failed, with 668 passed,
2 skipped, 7 deselected and 2 warnings. The original failure XML is retained.
Restoring the existing CI's process-only `sk-ci-dummy`, without reading a real
key or changing source/assertions, produced **677 passed, 2 skipped,
7 deselected, 2 warnings (6.28 s)**. The same 12 offline compatibility cases
passed again (1.27 s). These are the existing no-training profile, not a new
full optional-ML qualification.

Remote verification must identify the resulting exact candidate commit.
The unchanged workflow covers Linux Python 3.10/3.11/3.12, optional dependencies
and Windows/Linux Desktop/wheel/offline validation. It does not contain a
remote 3.14.8 job. Final commit/CI references belong in the checkpoint hand-off;
no future result is pre-declared here, and no release/tag is authorized.
