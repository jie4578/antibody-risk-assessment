"""Privacy filtering must preserve evidence text and opaque hash provenance."""
import copy
import hashlib

import pytest

from desktop.research_copilot import _redact_question, _scrub_context, build_copilot_context
from desktop.research_summary import build_research_summary


VH = "EVQLVESGGGLVQPGGSLRLSCAASGFNIKDTYIHWVRQAPGKGLEWVARIYPTNGYTRYADSVKGRFTISADTSKNTAYLQMNSLRAEDTAVYYCSRWGGDGFYAMDYWGQGTLVTVSS"
VL = "DIQMTQSPSSLSASVGDRVTITCRASQSISSYLAWYQQKPGKAPKLLIYAASSLQSGVPSRFSGSGSGTDFTLTISSLQPEDFATYYCQQSYSTPYTFGQGTKVEIK"


@pytest.mark.parametrize("text", [
    "Experimental ML estimates have not been calculated.",
    "ML estimates require experimental verification.",
    "These scientific estimates are limited.",
    "Scientific characteristics are not experimental proof.",
    "characteristically differentiated",
    "Family-independent generalization is unknown.",
    "No mutation hypothesis is included in this summary.",
    "Sequence length: 120 aa; calculated rule score: 66.3; CDR sites: 4.",
    "PMID: 12345678; DOI: 10.1000/test; Relevance: GENERAL.",
])
def test_prose_and_evidence_fields_are_not_sequence_substrings(text):
    assert _scrub_context(text) == text
    assert _redact_question(text) == text


@pytest.mark.parametrize("sequence", [
    VH, VH.lower(), VL,
    " ".join(VH[i:i + 10] for i in range(0, len(VH), 10)),
    " ".join(VL[i:i + 10].lower() for i in range(0, len(VL), 10)),
    "\n".join(VH[i:i + 40].lower() for i in range(0, len(VH), 40)),
    " ".join(VH),
])
def test_unstructured_raw_sequences_are_still_redacted(sequence):
    for redact in (_scrub_context, _redact_question):
        assert redact(sequence) == "[SEQUENCE OMITTED]"
        assert redact(f"Sequence: {sequence}; review only.") == "Sequence: [SEQUENCE OMITTED]; review only."


def test_hash_container_does_not_bypass_private_field_filtering():
    digest = hashlib.sha256(VH.encode()).hexdigest()
    raw = {
        "vh": VH, "vl": VL, "original_sequence": VH,
        "api_key": "fixed-fake-credential-for-test", "password": "fixed-fake-password",
        "file_path": "C:/private/example.joblib",
        "sequence_hashes": {
            "VH": digest, "sequence": digest, "original_hash": digest,
            "VL": VL, "mutant_hash": "not-a-digest", "api_key": "a" * 64,
        },
    }
    before = copy.deepcopy(raw)
    assert _scrub_context(raw) == {
        "sequence_hashes": {"VH": digest, "sequence": digest, "original_hash": digest},
    }
    assert raw == before


@pytest.mark.parametrize("value", [None, "not-a-hash-map", {"VH": None}, {}])
def test_missing_or_invalid_hashes_are_not_invented(value):
    assert _scrub_context({"sequence_hashes": value}) == {"sequence_hashes": {}}


def test_real_summary_context_preserves_gaps_limitations_and_chain_hashes():
    summary = build_research_summary({
        "sequence_analysis": {
            "antibody_id": "OTHER-SAMPLE", "vh": VH, "vl": VL,
            "sequence_length": 120, "risk_score": 66.3,
            "total_sites": 6, "cdr_sites": 4, "rule_version": "overlap_v2",
        },
    })
    before = copy.deepcopy(summary.to_dict())
    context = build_copilot_context(summary)
    assert context.payload["evidence_gaps"] == before["evidence_gaps"]
    assert context.payload["limitations"] == before["limitations"]
    for section in ("sequence_analysis", "provenance"):
        assert context.payload[section]["sequence_hashes"] == {
            "VH": hashlib.sha256(VH.encode()).hexdigest(),
            "VL": hashlib.sha256(VL.encode()).hexdigest(),
        }
    serialized = context.to_json()
    assert "[SEQUENCE OMITTED]" not in serialized
    assert VH not in serialized and VL not in serialized
    assert summary.to_dict() == before
