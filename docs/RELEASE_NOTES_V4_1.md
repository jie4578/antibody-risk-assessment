# v4.1.0rc1 — release candidate

Target stable release: v4.1.0. Candidate preparation: 2026-10-18.
This is a local candidate, not a published GitHub/PyPI release or new tag.
The historical v4.0.0 tag is not moved or amended.

## Scientific version boundary

The candidate packages the already-implemented `overlap_v2` product scanner,
including overlapping N-glycosylation candidates: NNST includes NNS@1–3 and
NST@2–4. These are computational candidates, not measured glycosylation.
Calculated scores can differ from the old default because candidate
enumeration changed. Do not present them as an unchanged scientific baseline.

Historical RULE48 extraction still selects `frozen_v1`, tied to immutable
baseline `d1487ed74bdfc52fb0b2015a25c4e91ee90af66d`. No scoring weights,
thresholds, fixed CDR coordinates, frozen ESM2 representation, model IDs,
hyperparameters, protocol versions, sealed outputs or stored experimental
results are changed by candidate preparation.

## Included repairs since v4.0.0

- Explicit rule-version provenance and frozen-v1 compatibility checks.
- Installed inference modules do not depend on the research validation tree.
- Duplicate-ID batch transfers retain the selected record's identity.
- Mutation edits and asynchronous completions cannot restore obsolete results.
- Research Summary excludes mismatched mutation evidence across samples.
- Literature selection works from any column; changing search inputs clears
  old evidence, details, actions and result-count messages.
- Copilot privacy, citation, numerical/type grounding and scientific-boundary
  safeguards, without making the explanation layer a source of scientific truth.
- Responsive Desktop shutdown that cancels queued work, suppresses cancelled
  results and waits for executing work, without forcibly terminating threads.
- An opt-in test-only native diagnostic retains original logs and separates
  clean startup, strictly reviewed UIA/COM diagnostics and failures.

These are existing repairs being versioned, not new rule tuning or model work
performed during this release-candidate build. Detailed chronology:
[audit repairs](AUDIT_REMEDIATION.md).

## Qualified Python profile

Windows x64 base Desktop/CLI: official standard-GIL **CPython 3.14.8**, fresh
venv, `.[desktop]`. The audited resolver selected PySide6/Qt 6.12.0, Gradio
6.30.0 and OpenAI 3.35.1; these observations are not new dependency pins.
`requires-python >=3.10` remains the package compatibility floor.

Exact-patch preflight: 677 passed, 2 skipped, 7 live deselected, 2 warnings;
12 offline frozen-rule/runtime-packaging/documentation compatibility cases
also passed. The two skipped cases require absent optional LangChain.
Legacy `test_ml.py` and `test_rag.py` were excluded in advance because they
execute training/fitting workflows outside this no-training base profile.
This is not the unrestricted 717-case development-environment result.

Installed-package, CLI, Gradio construction, Desktop entry-point and
missing-local-model checks pass without frozen model prediction. The native
host was Windows 10 build 19045; this is test provenance, not an OS security
support claim or a new Windows 11 manual test.

Optional ESM2/ML dependencies, binary artifacts, CUDA, real Provider calls and
all-extra environments are **not** newly qualified by the base Desktop result.
Model binaries and datasets are not bundled. Models require separately
qualified local dependencies and trusted frozen artifacts; they are not
retrained or rebuilt here. See [the model card](ML_MODEL_CARD.md).

## Known diagnostics and scientific limitations

The native Windows UIA/COM `0x8001010d` message can still occur. Independent
tracing verifies the reviewed provider-handoff path, post-event responsiveness
and normal exit. It remains disclosed as `REVIEWED_UIA_COM_DIAGNOSTIC`,
`clean=false`, not eliminated or a blanket exception exemption. See
[the diagnostic record](WINDOWS_QT_DIAGNOSTIC_2026-10-17.md).

The [existing validation evidence](../validation/README.md) remains
dataset-specific. GDPa3 external HIC evidence is weak and distribution-shifted;
the internal AIntibody benchmark has substantial residual sequence similarity.
No new prediction, label reveal, correlation or model-performance analysis is
performed for this candidate. No broad developability, family-independent,
clinical, causal mutation-effect, best-antibody or wet-lab-replacement claim
is made. Rule and ML evidence remain separate, without a combined verdict.

## Remaining publication gates

Candidate artifact integrity, post-install smoke and scoped regressions must
be checked for the actual versioned artifact. Exact candidate-commit remote
Windows/Linux CI and explicit authorization for publication are separate gates.
Local build success does not create a release or authorize a tag/push.
