# Desktop acceptance follow-up — 2026-10-17

Scope: remaining acceptance coverage and the two explanation/search-status
P2 repairs. The starting code checkpoint is
`02fb96142957bcb221fece7522321d54a36f216a`. The user authorized a selective
source/test/documentation checkpoint after full regression, without a new tag
or release. Data/model artifacts and unrelated CLI edits are excluded.

## Evidence and boundaries

| Check | Evidence | Result / scope |
|---|---|---|
| Duplicate IDs | Two synthetic CSV rows, real batch worker, filtering, both rows selected; Single and VH/VL Mutation transfer through the full MainWindow | Six Qt integration cases passed; actual selected sequences preserved |
| NNST | Single Analysis button, displayed risk table and Summary | Both NNS@1–3 and NST@2–4, `overlap_v2`; candidates, not measured modifications |
| Close during background work | Full MainWindow, real dedicated QThreadPool, active and queued workers, heartbeat timer | Window remains responsive while closing; queued work and result delivery suppressed; closes after active call ends |
| Real Agent tool calling | Configured official DeepSeek backend, actual Agent ReAct loop, allowlisted `scan_antibody` schema | Actual unblocked call on synthetic AAANNSTTT; length 9, NNS@4–6, NST@5–7, `overlap_v2` returned |
| Copilot privacy repair | User-provided post-restart AB001 answer | Ordinary prose intact, VH hash retained, score 66.3 / six sites / four CDR sites consistent |
| Copilot background repair | Recorded problematic English/Chinese phrases plus a fresh real DeepSeek explanation of synthetic data | Targeted unsupported functional/shared-residue claims blocked; reviewed fresh response contains neither observed claim |
| Literature stale count | Query, empty query, source, max-results edits; late success and late error | Old count/searching text cleared, rows/details/evidence cleared, no automatic search |

The Qt acceptance file has eight cases. They pass with the normal offscreen
platform. A separate Windows-platform run also returned eight passed and
exit 0, **but emitted Windows COM diagnostic `0x8001010d` while showing the
test window**. That original run is not recorded as clean. A follow-up isolated
startup check and four new independent Windows Qt runs were clean; see
`WINDOWS_QT_DIAGNOSTIC_2026-10-17.md`. This does not retroactively remove the
original diagnostic or prove its transient caller.

The Computer Use helper could read the user's live Desktop accessibility
tree. Its click failed with `coordinate input geometry is unavailable`;
one window rebind/activation/capture recovery failed with `FrameArrived timed
out: timed out waiting on channel`. Native inputs were stopped, and the
user's existing window was not closed or overwritten. No native mouse-driven
PASS is claimed for these remaining cases. Qt QTest input is not equivalent
to successful native mouse automation.

## Live checks

`tests/test_desktop_acceptance_live.py` is marked `live` and additionally
requires `ANTIBODY_RUN_LIVE_ACCEPTANCE=1`. It reuses configured credentials
only for the official DeepSeek API. It never extracts a session-only key
from another process, changes settings, logs credentials, or uses Mock as a
successful fallback. Only synthetic AAANNSTTT and its summary are sent.
No private antibody, dataset, sealed labels or ML prediction is used.

The first Agent probe used NNST (four residues). The existing Agent boundary
requires at least five, so it correctly blocked that probe. The test input
was changed to nine residues; the boundary itself was not relaxed.

The initial synthetic Copilot probe also made a false shared-start assertion
despite reporting the motif positions. That observed phrase now has a
regression guard and is not accepted as successful scientific explanation.
The final live run returned **2 passed**, with a real scan and a fresh
Copilot response. Inspection confirmed the requested motif/position facts,
the absence of new functional-effect claims, and no invented evidence tension.

These are scoped checks, not universal semantic validation. In that earlier
Copilot response, an empty `literature_identifiers` list was described together
with `rule_result_id` as "empty strings". That metadata-type description is
imprecise; the actual context/summary still contains the original list. It
was not evidence of altered scientific data. The follow-up now supplies
read-only metadata shape facts and blocks explicit named type/empty-state
misstatements. The original erroneous joint claim is covered by regression
tests; no metadata value is coerced or rewritten.

The focused real Provider recheck described the three fields correctly:
empty array, empty string and non-empty object. An initial general-explanation
probe after the change was rejected by the existing background guard (one
failed live test); the provider text was not retained by that version of the
test. This failure is preserved rather than counted as a successful explanation.
A subsequent bounded diagnostic run captured both focused and general outputs
and passed two tests. The latter still contained an unprovided general comment
about typical domain length: pattern guards are not universal semantic proof.
No further prompt/guard expansion is claimed in this metadata repair.
Rejected synthetic output is now printed by the opt-in general live test for
diagnosis; it is not returned to the UI as an accepted explanation.

The Agent answer also contains suggestions under
its existing Agent prompt; passing its tool-call check does not certify it
as the more restricted, tool-free Copilot.

## Verification

- Application suite after metadata closure: 665 passed, 7 deselected,
  5 warnings (12.90 s).
  There are now three opt-in live acceptance tests, excluded from ordinary runs.
- Real Provider acceptance before metadata closure: 2 passed (7.34 s).
  Metadata closure: one general probe rejected (1 failed), then a separately
  recorded focused/general diagnostic run: 2 passed (6.49 s).
- Qt acceptance: 8 passed, included in application total.
- Metadata regressions: 24 passed; isolated startup regressions: 2 passed.
  Both are included in the application total.
- Full validation suite after metadata closure: 185 passed (205.22 s), covering validation/tests,
  external_family_validation/tests and external_developability/tests.
- `git diff --check`: pass.

No change to `core.py`, `scoring.py`, ResearchDecisionSummary scientific
semantics, ML runtime/model files, rule thresholds, frozen benchmark results,
or experimental datasets. Original CLI edits and batch/manual workbook
artifacts are preserved. No production model retraining, tuning, new model
prediction or experimental performance analysis is performed. Only source,
tests and documentation belong in the authorized checkpoint.
