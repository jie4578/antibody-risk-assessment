# v4.1.0 release decision and selective-commit review

Decision date: 2026-10-18. Review base:
`fbc47eae0b898a6afba2f06b2af949616beac568` on `main`.

Latest authorized follow-up (2026-10-18): exact CPython 3.14.8 base-Desktop
acceptance passed and local **4.1.0rc1** wheel/sdist were built and audited.
See [the candidate audit](RELEASE_CANDIDATE_4_1_0RC1_AUDIT.md). The original
planning/review boundary below is retained with its subsequent disposition;
this is still not a published release or new Git tag.

## Release identity

The next target release is **v4.1.0**. It is not released or tagged yet.
The existing v4.0.0 tag remains immutable. At the initial planning checkpoint,
metadata stayed at 4.0.0 pending exact-patch acceptance. That gate subsequently
passed; current candidate package metadata is **4.1.0rc1**, not a final-version
artifact advertised as already released.

This is a minor scientific/product revision, not a documentation-only refresh
of v4.0.0. Since that tag, the product's default motif enumeration explicitly
uses `overlap_v2`, exports rule-version metadata, and adds compatibility and
evidence-handling repairs. NNST includes both NNS@1–3 and NST@2–4; therefore
calculated outputs can differ from the historical scanner. No unchanged-score
or unchanged-scientific-baseline claim is permitted across these versions.

The immutable validation baseline remains
`d1487ed74bdfc52fb0b2015a25c4e91ee90af66d`, with historical feature extraction
using `frozen_v1`. Scoring weights/thresholds, frozen ESM representation,
model IDs/versions, protocol versions, sealed predictions and experimental
results are not version-bumped or recomputed by this release decision.

## Python policy and qualified base profile

For the next Windows x64 **base Desktop installation** qualification, select
official, standard-GIL **CPython 3.14.8** in a fresh venv with `.[desktop]`.
The [official 3.14.8 release](https://www.python.org/downloads/release/python-3148/)
is a security maintenance release. Do not promote the repaired 3.14.5 install
as the newly recommended deployment patch merely because it passed the
bounded functional checks.

Initially 3.14.8 was only a target: a security release's existence did not prove
application/dependency/native compatibility. The subsequently authorized
exact-patch acceptance now qualifies the stated **base Desktop/CLI profile**;
it does not qualify every extra or runtime. Only the independent per-user
Python was updated from 3.14.5 to 3.14.8, with Anaconda/PATH preserved.

| Profile | Exact evidence | Policy / remaining gate |
|---|---|---|
| Windows base Desktop / CLI | Official 3.14.8, new venv; 677 passed, 2 optional skips, 7 live deselected, 2 warnings; 12 offline compatibility cases; installed RC/visible-window checks | Qualified for the stated local base profile, with retained reviewed COM diagnostic; optional ML and remote CI are separate |
| Prior standalone repair | Official 3.14.5 repaired full install and 10 acceptance/startup cases | Historical comparison, not the new deployment recommendation |
| Windows development regressions | Existing Anaconda 3.13.9; 717 application cases passed, 7 live deselected, 5 warnings; 10 frozen-runtime regression cases passed | Historical development evidence, not a clean standalone or security-current deployment recommendation; do not modify this environment |
| Optional frozen ML / ESM2 | Earlier frozen inference/runtime evidence; the fresh 3.14.5 Desktop install intentionally lacked torch, transformers and model binaries | Not covered by base Desktop qualification; exact Python/dependency/model-artifact compatibility needs its own offline, no-training qualification |
| Existing CI compatibility | Workflow declares Python 3.10, 3.11 and 3.12; optional-dependency and Windows/Linux integrity jobs use 3.12 | Declared CI configuration, not newly verified remote results or exact-patch support evidence; inspect actual candidate-checkpoint results before release |
| Newer Python / free-threaded builds | No qualification in this checkpoint | No support claim inferred from `requires-python` or the standard-GIL results |

`requires-python = ">=3.10"` remains the current package compatibility floor,
not a promise that every later minor/patch and every optional dependency is
qualified. Do not raise the minimum to 3.14 or pin every user to one exact
patch to disguise missing qualification. Likewise, do not transfer the base
Desktop result to `[dl]`, `[all]`, real Provider calls or frozen-model loading.

For a later optional-ML qualification in the 3.13 line, the
[official 3.13.16 release](https://www.python.org/downloads/release/python-31316/)
is an available security-maintenance target, **not a qualified ML environment
in this review**. Choose and test an exact environment before publishing an
ML-supported-patch list; do not change model parameters or rebuild models to
make a new environment pass.

The observed native host is Windows 10 build 19045. That is test provenance,
not a claim about Microsoft OS support/security coverage or a new manual
Windows 11 acceptance result. The UIA/COM diagnostic remains disclosed:
reviewed native path, healthy continuation/exit, **not CLEAN or eliminated**.

## Selective-commit review

Review disposition: **PASS for the following narrow diagnostic/acceptance/
planning checkpoint**, not approval to publish v4.1.0. This review does not
stage anything or make a commit.

Original five-file prospective allowlist (expanded by the later authorized
candidate-preparation step below):

- `docs/RELEASE_PLAN_V4_1.md` — this version/policy/gate decision.
- `docs/RELEASE_ACCEPTANCE_2026-10-17.md` — acquisition, installation,
  functional acceptance, failures, native diagnostics and preservation record.
- `docs/WINDOWS_QT_DIAGNOSTIC_2026-10-17.md` — chronological native diagnostic
  evidence, source references and conservative interpretation.
- `tests/qt_startup_diagnostic.py` — opt-in Windows x64 observer/classifier;
  no product import by normal startup, no exception resumption/suppression.
- `tests/test_qt_startup_diagnostic.py` — 52 fail-closed classification cases,
  including Python 3.14 fallback and unknown/fatal-output rejection cases.

Review findings:

- The diagnostic preserves original child stdout/stderr, verifies the ordered
  native chain and exact UIA function frame, and requires responsiveness after
  the event plus normal exit. Its reviewed status is explicitly not CLEAN.
- The 3.14 C-stack fallback is limited to the exact reviewed two-line format
  with version metadata; arbitrary C frames, unknown errors, missing health
  evidence and nonzero exits remain failures. Strict startup tests are not
  relaxed. This helper is not a crash-proofing production workaround.
- Reports preserve failed attempts and distinguish installed-package smoke,
  archived-source regressions, native accessibility observation, assisted
  manual checks, historical results and unperformed checks.
- The five files contain synthetic test sequences, public software hashes and
  documented scientific caveats. No live API key, private key, password,
  personal profile path, raw data or generated model file was found in the
  reviewed content. Machine-local raw logs can contain paths and remain out
  of this allowlist; this is a bounded review, not a repository-wide secret
  scan or permission to publish local evidence wholesale.
- No current worktree changes exist in core/scoring, Desktop, Agent, ML
  inference or model implementations. Existing scientific/model/protocol
  versions and frozen results are unchanged by this checkpoint.

Explicit exclusions (never use a blanket `git add .`):

- Preserved `cli.py` and `literature/cli.py` modifications.
- `manual_acceptance.csv.xlsx` and all existing batch artifacts.
- Raw/processed datasets, NPZ embeddings, model binaries, caches/databases,
  `.env`, credentials and machine-local installer/diagnostic logs.
- The original decision checkpoint made no README, `pyproject.toml` or CI
  changes. The later user-authorized candidate phase adds reviewed version/
  packaging edits below; CI itself remains unchanged.

## Evidence and release gates

Latest existing evidence, not rerun merely to choose a version:

- Full application: 717 passed, 7 deselected, 5 warnings (13.68 s).
- New official 3.14.5 venv: 10 Desktop acceptance/startup passed (2.36 s);
  52 diagnostic-classification cases passed (0.11 s).
- Frozen runtime regressions: 10 passed (2.03 s).
- Full validation: previous 185 passed (208.06 s); historical result, not a
  new 3.14.8 or optional-ML qualification.
- Working-tree/whitespace/security/preservation checks for this review are
  separate from those prior test executions: tracked `git diff --check` and
  explicit whitespace/conflict/EOF checks across all five allowlisted files
  passed. Content review and scans found no credential/private-key/profile-path
  candidate in that narrow scope. Protected CLI/manual/batch and core/scoring
  SHA256 values match the pre-review record; index is empty and production
  source directories have no worktree diff. These checks do not make the
  historical test executions into new test runs.

Before an actual v4.1.0 release:

1. **Completed locally:** exact 3.14.8 base Desktop/CLI packaging and offline
   entry-point qualification, independently of the old 3.14.5 result. See the
   candidate audit for acquisition, retained diagnostics and exact results.
2. Define and qualify the optional-ML deployment environment separately, or
   explicitly limit the release's verified-environment claims; no retraining,
   new model-performance calculation or sealed-label access.
3. **Completed locally:** package/README/new release notes consistently use
   4.1.0rc1 and preserve `overlap_v2`, `frozen_v1`, existing external evidence
   and caveats. Artifacts were built from clean base plus explicit overlays,
   installed/tested and source-audited, excluding the dirty CLI modifications.
4. Check the exact candidate's required Windows/Linux CI and applicable
   offline regressions. A workflow file or prior run is not a new CI PASS.
5. Obtain explicit authority for commit/push and, separately, tag/Release
   publication. Never amend v4.0.0, replace its tag, or force-push.

The original decision step made no interpreter/version change. The later
authorized follow-up is **EXACT_PATCH_ACCEPTANCE_PASS / CANDIDATE_BUILD_PASS /
READY_FOR_SELECTIVE_COMMIT_REVIEW / NOT_PUBLISHED**. No production source
behavior, model or scientific result changed. No staging, commit, push or tag
has occurred. Remote CI for the future exact commit and publication authority
are still outstanding.

## Expanded candidate-preparation commit scope

The original five files plus only these six release files form the current
11-file prospective allowlist:

- `.gitignore` — ignore generated local `dist/` artifacts.
- `pyproject.toml` — package version 4.1.0rc1 only; compatibility floor unchanged.
- `README.md` — candidate identity and exact base-profile qualification.
- `MANIFEST.in` — explicit diagnostic helper/release-note inclusion in sdist.
- `docs/RELEASE_NOTES_V4_1.md` — candidate changes, boundaries and exclusions.
- `docs/RELEASE_CANDIDATE_4_1_0RC1_AUDIT.md` — environment, scoped tests, build
  inputs, final artifact hashes, retained diagnostics and publication gates.

Distribution files, local evidence logs, source staging copies and all earlier
protected/excluded files remain outside this allowlist. Earlier test counts
are historical; the candidate's new exact-patch results are in its audit.
