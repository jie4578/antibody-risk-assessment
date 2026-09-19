"""Centralized user-facing metadata for the frozen local ML estimates."""

from __future__ import annotations

HIC_MODEL_ID = "hic_esm2_v1"
DEVELOPABILITY_MODEL_ID = "developability_esm2_v1"
ESM_MODEL_NAME = "facebook/esm2_t30_150M_UR50D"
ESM_MODEL_REVISION = "a695f6045e2e32885fa60af20c13cb35398ce30c"
BENCHMARK_ID = "AINTIBODY_INTERNAL_ENTITY_EXACT_V1"
MODEL_MANIFEST_ID = "7826881c04887d274f73e737caf35d83e7b62dd2"
BENCHMARK_SCOPE = "internal AIntibody sequence landscape"
LIMITATION = (
    "84/95 held-out TEST sequences had paired-min identity >=0.90 to training data. "
    "Performance on distant antibody families is unknown."
)
EVIDENCE = {
    "hic": {"spearman": 0.834662, "r2": 0.625834, "n": 72},
    "developability": {"pr_auc": 0.611665, "roc_auc": 0.691468, "prevalence": 0.336842, "n": 95},
}
LOCAL_INFERENCE_NOTICE = "Local inference; sequence ML inference runs locally and does not require DeepSeek/OpenAI. No provider API call and no sequence upload."
RESEARCH_SUPPORT_NOTICE = "Use as research support; experimental verification remains required."
NO_CATEGORICAL_DECISION_NOTICE = "No categorical decision threshold is defined."


def evidence_text(task: str) -> str:
    """Return concise benchmark evidence for the optional details panel."""

    if task == "hic":
        values = EVIDENCE["hic"]
        return f"Frozen Phase 5 TEST evidence: Spearman {values['spearman']:.6f}, R² {values['r2']:.6f}, N={values['n']}."
    values = EVIDENCE["developability"]
    return (
        f"Frozen Phase 5 TEST evidence: PR-AUC {values['pr_auc']:.6f}, "
        f"ROC-AUC {values['roc_auc']:.6f}, prevalence {values['prevalence']:.6f}, N={values['n']}."
    )
