# tests/test_mutation.py
# B2：mutation 原氨基酸校验
import pytest

from core import mutate_sequence, mutate_and_rescan

SEQ_A55 = "A" * 60
SEQ_G55 = "A" * 54 + "G" + "A" * 5


def _cdr_defaults():
    return (31, 35, 50, 65, 99, 110)


class TestMutateSequence:
    def test_valid_mutation_success(self):
        assert mutate_sequence("ACD", "A1C") == "CCD"

    def test_a55q_when_position_is_a(self):
        mutated = mutate_sequence(SEQ_A55, "A55Q")
        assert len(mutated) == 60
        assert mutated[54] == "Q"
        assert mutated.count("Q") == 1

    def test_a55q_when_position_is_g_raises(self):
        with pytest.raises(ValueError) as exc:
            mutate_sequence(SEQ_G55, "A55Q")
        assert "Expected residue A at position 55, but found G." in str(exc.value)

    def test_invalid_position_raises(self):
        with pytest.raises(ValueError):
            mutate_sequence("ACD", "A4Q")

    def test_position_beyond_length_raises(self):
        with pytest.raises(ValueError):
            mutate_sequence(SEQ_A55, "A61Q")

    def test_invalid_mutant_residue_raises(self):
        with pytest.raises(ValueError):
            mutate_sequence(SEQ_A55, "A55X")

    def test_invalid_original_residue_raises(self):
        with pytest.raises(ValueError):
            mutate_sequence(SEQ_A55, "X55Q")

    def test_lowercase_mutation_works(self):
        assert mutate_sequence("acd", "a1c") == "CCD"


class TestMutateAndRescan:
    def test_mismatch_is_graceful(self):
        report, risks, summary, mutated = mutate_and_rescan(SEQ_G55, "A55Q", *_cdr_defaults())
        assert "突变失败" in report
        assert risks == []
        assert summary == "突变失败"
        assert mutated == SEQ_G55
