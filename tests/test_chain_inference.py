import pandas as pd

from desktop.chain_inference import infer_chain, infer_column_chain
from desktop.column_mapping import infer_smart_mapping


VH = "EVQLVESGGGLVQPGGSLRLSCAASGFNIKDTYIHWVRQAPGKGLEWVARIYPTNGYTRYADSVKGRFTISADTSKNTAYLQMNSLRAEDTAVYYCSRWGGDGFYAMDYWGQGTLVTVSS"
VL = "DIQMTQSPSSLSASVGDRVTITCRASQSISSYLAWYQQKPGKAPKLLIYAASSLQSGVPSRFSGSGSGTDFTLTISSLQPEDFATYYCQQSYSTPYTFGQGTKVEIK"


def test_known_sequences_and_input_normalization():
    assert infer_chain(VH).chain == "VH"
    assert infer_chain(VL.lower()).chain == "VL"
    assert infer_chain("  " + VH + "  ").chain == "VH"


def test_unknown_invalid_and_short_sequences_are_conservative():
    assert infer_chain("A" * 30).chain == "UNKNOWN"
    assert infer_chain("A" * 100 + "X").chain == "UNKNOWN"
    assert infer_chain("A" * 100).chain == "UNKNOWN"


def test_column_voting_is_deterministic():
    vh_result = infer_column_chain([VH] * 9 + ["A" * 100])
    vl_result = infer_column_chain([VL] * 10)
    mixed = infer_column_chain([VH] * 5 + [VL] * 5)
    assert (vh_result.chain, vh_result.vh_count, vh_result.unknown_count) == ("VH", 9, 1)
    assert (vl_result.chain, vl_result.vl_count) == ("VL", 10)
    assert mixed.chain == "AMBIGUOUS"


def test_ambiguous_sequence_columns_auto_map_only_with_pairwise_confidence():
    frame = pd.DataFrame({"Sample": ["S-001", "S-002"], "Seq_A": [VH, VH], "Seq_B": [VL, VL]})
    mapping, ambiguous = infer_smart_mapping(frame)
    assert not ambiguous
    assert mapping == {"antibody_id": "Sample", "VH": "Seq_A", "VL": "Seq_B"}


def test_real_two_row_import_maps_seq_a_vh_and_seq_b_vl(tmp_path):
    path = tmp_path / "real_mapping.csv"
    pd.DataFrame({"Sample": ["S-001", "S-002"], "Seq_A": [VH, VH + "AA"], "Seq_B": [VL, VL + "A"]}).to_csv(path, index=False)
    from desktop.batch_adapter import analyze_file
    result = analyze_file(path)
    assert [(record.vh_length, record.vl_length, record.status) for record in result.records] == [(120, 107, "SUCCESS"), (122, 108, "SUCCESS")]
    from desktop.batch_adapter import input_mapping
    assert input_mapping(path) == {"antibody_id": "Sample", "VH": "Seq_A", "VL": "Seq_B"}


def test_conflicting_or_weak_column_inference_falls_back_to_dialog():
    frame = pd.DataFrame({"Sample": ["S-001"], "Seq_A": [VH], "Seq_B": ["A" * 100]})
    mapping, ambiguous = infer_smart_mapping(frame)
    assert ambiguous and mapping == {"antibody_id": "Sample", "VH": "Seq_A"}
    frame = pd.DataFrame({"Sample": ["S-001"], "Seq_A": [VH], "Seq_B": [VH]})
    mapping, ambiguous = infer_smart_mapping(frame)
    assert ambiguous and mapping == {"antibody_id": "Sample"}
