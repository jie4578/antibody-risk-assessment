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
When the underlying summary changes, a previous explanation is marked
historical and a new current summary must be built before another request.

The copilot is not a clinical predictor, a family-independent generalization
claim, a wet-lab replacement, or a source of validated mutation-effect
measurements. Its output supports human review of already-computed evidence.
