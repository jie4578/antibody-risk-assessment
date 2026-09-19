# Phase 5B: frozen ESM-2 representation extraction

Phase 5B extracts frozen Protein Language Model representations for
`AINTIBODY_INTERNAL_ENTITY_EXACT_V1`. It does not fit a predictive model,
calculate performance, access test labels, standardize features, run PCA/UMAP,
or select dimensions using outcomes.

The model is `facebook/esm2_t30_150M_UR50D`, loaded at an immutable Hugging
Exact revision recorded in `embedding_manifest.json`. VH and VL are tokenized
and mean-pooled independently from final hidden states after excluding BOS,
EOS, other special tokens, and padding. The paired vector is exactly
`[VH_embedding || VL_embedding]` with 640 + 640 = 1280 float32 dimensions.

Inputs are the frozen Phase 5A.2 sequence feature files and split manifest.
The extractor never opens `sealed_test_labels.csv`; test row count and hashes
come only from `test_features.csv` and the frozen split manifest. Rule-feature
alignment uses sequence hashes only and does not read experimental outcomes.

The primary inference batch size is 8. If device memory requires it, only the
computational batch size may reduce to 4, 2, or 1. Model, precision, sequence
representation, and split assignments remain unchanged. The runtime records
device, model revision, library versions, batch size, sequence-manifest hashes,
embedding-file hashes, and a deterministic repeatability audit.

Model weights and caches remain outside Git. Generated NPZ/CSV/JSON outputs
under `validation/data/ml_benchmark/entity_exact_v1/embeddings/` are ignored.
