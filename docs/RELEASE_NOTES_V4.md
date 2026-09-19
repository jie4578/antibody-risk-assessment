# Antibody Research Decision-Support Workbench v4.0

## Highlights

v4.0 packages the local-first Desktop research workflow around separate rule,
experimental-ML, literature, summary, and controlled-AI evidence layers.

## Desktop Workflow

The PySide6 Desktop entry point is `python -m desktop.main`. Single Analysis,
Batch Analysis, Mutation Workspace, Literature Evidence, Research Decision
Summary, and AI Research Copilot are available as explicit workflows.

## Sequence Liability Screening

The existing deterministic rule engine scans VH/VL sequences for predefined
PTM and chemical-liability motifs, annotates CDR/framework context, and keeps
the calculated rule score separate from experimental measurements.

## Batch Analysis

CSV, XLSX, and FASTA inputs are normalized to antibody identity and VH/VL
chains. Flexible mapping, chain inference, per-chain analysis, and CSV/XLSX
export support screening of multiple records.

## Mutation Workspace

Users can validate a mutation and compare original versus mutant rule sites.
The workspace can also compare local model estimates, but an ML delta is only
an arithmetic difference between model outputs and is not a validated mutation
effect size or recommendation.

## Literature Evidence

Europe PMC/PubMed retrieval, relevance labels, evidence provenance, and
identifier validation keep literature context separate from sequence-derived
tool facts.

## Experimental ML

The optional local ESM2 runtime exposes a HIC estimate and the probability of
the frozen `NOT_DEVELOPABLE` benchmark class. Models use the frozen
`facebook/esm2_t30_150M_UR50D` representation and are built from TRAIN plus
VALIDATION only. Model binaries are generated locally and are not committed.

## Experimental Validation

Jain 2017 showed broadly weak or null associations for the broad current-rule
feature set. AIntibody showed assay-specific oxidation/HIC relationships.
Frozen Phase 5 evidence was:

- HIC / ESM2: Spearman rho `0.834662`, R² `0.625834`, N=`72`;
- composite / ESM2: PR-AUC `0.611665`, ROC-AUC `0.691468`, N=`95`.

TEST evaluation occurred once under the frozen protocol. 84/95 TEST sequences
had paired-min identity ≥0.90 to TRAIN, so the result does not establish
family-independent generalization. The observed TEST set cannot be reused as
a new untouched final test.

## Research Decision Summary

The summary is deterministic and aggregates existing evidence. It does not
rerun rules or ML, search literature, call a Provider, create an overall
score, or create a final scientific verdict.

## Controlled AI Research Copilot

The Copilot requires explicit user action, explains the current summary, and
uses the configured Provider. Raw VH/VL is not included by default. Citation
identifiers are checked against the current summary. It does not call
scientific tools, rerun analysis, or become the source of truth.

## Provider Compatibility

Supported providers are DeepSeek, OpenAI, OpenAI-compatible endpoints, Ollama,
and Mock. Provider configuration is optional for non-AI workflows.

## Privacy / Local-vs-Network Behavior

Rule analysis, mutation rules, batch analysis, deterministic summaries, and
cached ML inference run locally. The initial ESM2 load may retrieve weights
from Hugging Face. Literature search sends a query to the selected literature
API. A remote Copilot sends structured summary context to the selected
Provider; full raw VH/VL is not sent by default. Local Ollama keeps the
request on the configured local service.

## Scientific Limitations

The rule score is a computational prioritization score, not a probability or
experimental result. The ML benchmark is internal and not family-independent.
Neither model replaces wet-lab testing, clinical assessment, or expert
review. No causal mutation claim is made.

## Known Limitations

- The benchmark's residual sequence similarity limits claims about new antibody
  families.
- Model outputs are available only after local artifacts and dependencies are
  prepared.
- Literature evidence is contextual and does not validate a specific sequence
  without appropriate experiments.
- Public screenshots and a broader prospective validation cohort remain future
  release assets.

## Installation / Model Preparation

Windows PowerShell setup:

```powershell
py -3.10 -m venv .venv
.\.venv\Scripts\Activate.ps1
python -m pip install --upgrade pip
python -m pip install ".[desktop]"
python -m pip install ".[dl]"
python -m desktop.main
```

With the local frozen validation inputs and embeddings available, build the
ignored deployment artifacts with:

```powershell
python validation/run_build_deployment_models.py
```

This produces `hic_esm2_v1.joblib`, `developability_esm2_v1.joblib`, and
`model_manifest.json` under `artifacts/ml_models/`; it does not use frozen TEST
rows. ESM2 weights may require a first-run Hugging Face download; CUDA is
optional and CPU fallback is supported.
