# Audit repair notes (unreleased)

## Scientific version boundary

The immutable validation baseline remains commit
`d1487ed74bdfc52fb0b2015a25c4e91ee90af66d`. Product scanning now identifies
itself as `overlap_v2`: the sequence `NNST` has N-glycosylation candidates
`NNS@1–3` and `NST@2–4`. This is candidate enumeration, not evidence of
experimental occupancy. No weights, thresholds, CDR coordinates, mutation
operation, or ML model have been changed.

`core.analyze_sequence(..., rule_version="frozen_v1")` preserves the original
non-overlapping scanner, including its reports and metadata. Historical
RULE48 feature extraction explicitly selects that version. Sequence-only
compatibility tests compare it with the original Git source, and the scoring
source is checked against that same checkpoint. Existing benchmark artifacts,
model binaries, sealed predictions, and Phase 8C JSON are not rewritten.
The old v4.0.0 Git tag remains historical; these repairs require a separate
release review before publication. Scores from the two rule versions must not
be presented as an unchanged scientific baseline.
Batch CSV/XLSX outputs append a `rule_version` metadata column. Existing
columns and canonical input fields retain their names and order. Mutation
results and tool text also identify the rule version.

## Product repairs

- Installed ML inference uses a small runtime ESM2 module, with synthetic
  parity tests against the frozen extractor. A wheel built outside the source
  tree imports without validation datasets or research code. `config.py` is
  included. Supported Python is 3.10+.
- Batch table rows carry their own records, including duplicate IDs.
- Mutation and Literature workers validate their input generation before
  accepting completion. Research Summaries check mutation baseline hashes and
  antibody identity, excluding unverifiable/mismatched evidence with a gap.
- Copilot validation checks explicit numerical claims and bilingual decision
  language, allowing negated scientific limitations. These checks cover
  selected explicit claims; natural-language explanation still requires human
  review and is not an independent source of scientific evidence.
- Copilot privacy filtering preserves ordinary evidence prose and validated
  SHA256 chain hashes in `sequence_hashes`. Raw sequence/credential fields
  remain excluded; free-text sequence tokens, wrapped blocks and residue-wise
  input are redacted. Regression tests cover the real Windows explanation's
  corrupted missing-ML and experimental-verification statements. The provider
  context must not confuse omitted raw sequences with missing provenance.
- Single Analysis explicitly labels its single-chain rule scope and fixed
  index CDR regions. A VL partner does not contribute to that rule score.
- Literature selection works from every column. Search, filter and context
  changes clear selected evidence and notify Summary state.
- Batch deamidation detail counts use the actual core category name.

## Background work and CI

Closing Desktop cancels queued workers, suppresses cancelled result/error
callbacks, and waits for active calls with a responsive Qt timer. An executing
network request or model kernel finishes under its own timeout/completion;
Python threads are not forcibly terminated. No new work can be started from
the closing window. The current app owns the global Qt thread pool.

CI includes Windows/Linux Desktop tests, source-independent wheel imports,
and explicitly selected offline validation tests that do not need raw
datasets, labels, or model weights. The larger historical validation suite
still requires the local reproducibility bundle. Real Provider compatibility
and interactive Windows use require a separate manual check.

Local verification: application suite 605 passed, 4 deselected, 5 warnings;
project validation suites 185 passed; offline CI subset 12 passed. The subset
is included in the validation coverage, not an additional scientific study.
The 22 privacy regressions are included in the application total. No Phase 8C
evaluation was rerun. CI workflow YAML parses locally; remote Windows/Linux
job results must be checked for the pushed repair checkpoint.

The first remote run exposed fresh-runner setup gaps: Qt's Linux EGL library
was absent, the optional-dependency job did not install pytest, and the offline
wheel build lacked setuptools on Windows. CI now installs the Linux Qt runtime
libraries, the optional job installs `all,dev`, and `dev` explicitly includes
the setuptools build backend. No test is skipped to hide these failures.

User-provided Windows screenshots confirm normal batch import, N55Q rule
comparison, mutation edit invalidation, cross-antibody Summary exclusion,
Year-column literature selection, GENERAL-label preservation and evidence
clearing. A real DeepSeek connection and explanation request succeeded, but
the explanation exposed the privacy-filter defect fixed above. A post-fix
live explanation has not yet been rechecked and is not recorded as passing.
Duplicate-ID and in-flight shutdown behavior are covered by automated tests;
their separate interactive Windows checks are not claimed as completed.

Remaining non-blocking UI issue: after editing a literature query, results
and selected evidence clear correctly, but the previous result-count status
can remain visible. This checkpoint does not change that status message.
