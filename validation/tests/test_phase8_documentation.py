from __future__ import annotations

import hashlib
import json
from pathlib import Path


PROJECT_ROOT = Path(__file__).resolve().parents[2]
ROOT = PROJECT_ROOT / "validation"
RESULT_JSON = ROOT / "external_developability" / "phase8c_hic_external_result.json"
RESULT_MD = ROOT / "external_developability" / "PHASE8C_HIC_EXTERNAL_VALIDATION_RESULT.md"
OBSERVED_MARKER = ROOT / "external_developability" / "PHASE8_GDPA3_HIC_OBSERVED.md"


def test_frozen_phase8_result_and_report_digest_agree() -> None:
    payload = RESULT_JSON.read_bytes()
    digest = hashlib.sha256(payload).hexdigest()
    result = json.loads(payload)
    report = RESULT_MD.read_text(encoding="utf-8")

    assert f"`{digest}`" in report
    assert result["status"] == "OBSERVED_ONE_TIME_EXTERNAL_EVALUATION"
    assert result["dataset"] == "GDPa3"
    assert result["endpoint"] == "hic_rt_avg"
    assert result["primary"] == {
        "metric": "Spearman rho",
        "estimate": 0.23190081863356382,
        "n": 79,
    }
    assert result["bootstrap"]["ci"] == [0.0054175577212944165, 0.4375911455240819]
    assert result["join_integrity"] == {
        "matched_rows": 79,
        "prediction_only_rows": 0,
        "label_only_rows": 0,
        "hash_mismatches": 0,
    }
    assert result["model_trained"] is False
    assert result["model_tuned"] is False
    assert result["aintibody_test_labels_accessed"] is False


def test_external_evidence_is_consistent_across_public_summaries() -> None:
    readme = (PROJECT_ROOT / "README.md").read_text(encoding="utf-8")
    validation_summary = (ROOT / "README.md").read_text(encoding="utf-8")
    model_card = (PROJECT_ROOT / "docs" / "ML_MODEL_CARD.md").read_text(encoding="utf-8")
    marker = OBSERVED_MARKER.read_text(encoding="utf-8")

    for text in (readme, validation_summary, model_card):
        assert "0.231901" in text
        assert "0.005418" in text
        assert "0.437591" in text
        assert "79" in text
        assert "family-independent" in text
    assert "External HIC Validation — GDPa3" in validation_summary
    assert "cross-source / cross-protocol" in validation_summary
    assert "0.834662" in validation_summary
    assert hashlib.sha256(RESULT_JSON.read_bytes()).hexdigest() in validation_summary
    assert "OBSERVED AFTER PHASE 8C" in validation_summary
    assert "OBSERVED AFTER PHASE 8C" in marker
    assert "untouched" in marker
