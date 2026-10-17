# AI Research Copilot

The AI Research Copilot is an optional explanation layer on top of the
deterministic `ResearchDecisionSummary`. It is intentionally downstream of
the existing rule, literature, mutation, and local ML workflows.

The user must first build a current Research Summary and then explicitly
select `Explain with AI`. The request runs asynchronously through the existing
provider compatibility layer. There is no automatic request, tool calling,
literature search, rule recomputation, ML recomputation, mutation generation,
ranking, overall score, verdict, or recommendation.

The provider receives a structured summary context containing existing
evidence, limitations, evidence gaps, provenance, and literature metadata.
Raw VH/VL sequences, credentials, local paths, and private configuration are
excluded by default. The UI displays a provider-specific privacy disclosure
before the request. A remote provider may receive the structured summary;
Ollama and Mock are labelled as local/offline providers.

Responses are checked for unsupported decision language and citations that are
not present in the summary. A response that crosses the boundary is blocked.
The explanation prompts also prohibit importing background knowledge,
mechanistic effects, per-site severity, assumed antibody format, invented
evidence tensions, or shared-residue relationships absent from the snapshot.
Targeted bilingual guards reject known ungrounded CDR/functional-effect and
shared-start/shared-residue claims, including hedged wording. A literal claim
already recorded in the snapshot can be quoted; literature titles still need
to be described as titles and GENERAL must remain GENERAL. These pattern
checks are not a general semantic verifier: arbitrary paraphrases and all
natural-language claims cannot be certified automatically. Named assertions
about provenance `literature_identifiers`, `rule_result_id` and `sequence_hashes`
types and empty states are checked against the actual snapshot, including
joint English/Chinese claims. The prompt receives read-only shape facts; no
array/string/object/null coercion or Summary schema change is performed.
An inconsistent response is blocked, not silently rewritten. Human review remains
required, and the deterministic summary is the source of truth.
When the underlying summary changes, a previous explanation is marked
historical and a new current summary must be built before another request.

The copilot is not a clinical predictor, a family-independent generalization
claim, a wet-lab replacement, or a source of validated mutation-effect
measurements. Its output supports human review of already-computed evidence.
