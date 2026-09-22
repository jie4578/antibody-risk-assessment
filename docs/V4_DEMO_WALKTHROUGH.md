# v4.0 Demo Walkthrough

This walkthrough uses the tracked `example_antibodies.csv` or another
synthetic/reference sequence supplied by the user. Do not use proprietary
sequences, private credentials, or Phase 5 TEST labels in a public demo.

## Workflow

1. Launch the Desktop application:

   ```powershell
   python -m desktop.main
   ```

2. Open **Single Analysis** and enter a paired VH/VL example.
3. Run the analysis and inspect the sequence-liability sites, CDR/framework
   labels, rule score, and limitations.
4. Run **Experimental ML Estimates** explicitly when local model artifacts and
   the ESM2 cache are available. Read the HIC estimate and
   `P(NOT_DEVELOPABLE)` as research-support outputs, not decisions.
5. Open **Mutation Workspace** and create one mutation hypothesis.
6. Compare the original and mutant rule findings, including removed and added
   liabilities.
7. Run **Mutation ML Comparison** explicitly and inspect the baseline estimate,
   mutant estimate, and arithmetic delta.
8. Open **Literature Evidence**, search a liability-related query, and review
   the returned identifiers, relevance, and source provenance.
9. Build the **Research Decision Summary** from the evidence already present.
10. Use **AI Research Copilot** explicitly to explain that summary.
11. Keep the final decision with the human researcher and verify hypotheses in
    the appropriate experiment.

## Safe scientific wording

Prefer:

- “rule-based liability decreased”;
- “model-estimated HIC changed”;
- “literature provides contextual evidence”;
- “human review remains required.”

Do not say:

- “This mutation is better”;
- “This antibody is developable”;
- “AI recommends…”;
- “the model proves family-independent generalization.”

Mutation ML deltas are arithmetic differences between two antibody-level
model outputs. They are not independently validated single-mutation effect
sizes.

## Public screenshots

**PUBLIC SCREENSHOTS COMPLETE**

These captures use public-safe Synthetic/Reference Demo data and represent
real application workflows. No benchmark TEST data are exposed. Screenshot
08 uses the built-in Mock provider for a deterministic, credential-free public
demo.

1. [Single sequence liability analysis](images/v4/01-single-analysis.png)
2. [Batch analysis](images/v4/02-batch-analysis.png)
3. [Mutation workspace](images/v4/03-mutation-workspace.png)
4. [Literature evidence](images/v4/04-literature-evidence.png)
5. [Local experimental ML estimates](images/v4/05-experimental-ml-estimates.png)
6. [Mutation ML comparison](images/v4/06-mutation-ml-comparison.png)
7. [Deterministic Research Decision Summary](images/v4/07-research-decision-summary.png)
8. [Controlled AI Research Copilot](images/v4/08-ai-research-copilot.png)
