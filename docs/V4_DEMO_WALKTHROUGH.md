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

## Screenshot checklist

**PUBLIC SCREENSHOTS PENDING**

Capture only synthetic/reference data and redact any local paths or provider
identifiers. The later public set should cover:

1. Single Analysis
2. Batch Analysis
3. Mutation Workspace
4. Literature Evidence
5. Experimental ML Estimates
6. Mutation ML Comparison
7. Research Decision Summary
8. AI Research Copilot
