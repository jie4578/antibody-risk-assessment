# Research Decision Summary

The Desktop Single Analysis workflow can build a deterministic Research
Decision Summary from evidence already present in the session. It is an
evidence snapshot for human review and experimental planning, not a scientific
verdict or an overall score.

The summary keeps these layers separate:

- rule-based sequence liability screening;
- local experimental ML estimates;
- mutation rule comparison and mutation ML comparison;
- selected literature evidence;
- evidence gaps, limitations, and provenance.

Building the summary is an explicit user action. It does not invoke the rule
engine, ML inference, ESM, a Provider, an LLM, Europe PMC, or PubMed. It reads
structured results already held by the Desktop workflow. No categorical ML
decision threshold or mutation recommendation is created.

Each summary has a deterministic evidence fingerprint. If relevant sequence,
analysis, ML, mutation, or literature state changes, the displayed snapshot is
marked `Outdated — evidence has changed.` The user must rebuild it explicitly.

ML values remain research-support estimates from the internal AIntibody
benchmark and require experimental verification. Mutation ML deltas are
differences between model estimates and are not validated experimental
mutation-effect measurements. Literature relevance labels remain DIRECT,
GENERAL, or IRRELEVANT; GENERAL evidence is not promoted to antibody-specific
validation.

Export is deferred in Phase 6D so the existing report/export infrastructure is
not changed. The structured DTO and renderer are intentionally independent of
Qt and can be connected to a safe export path later.
