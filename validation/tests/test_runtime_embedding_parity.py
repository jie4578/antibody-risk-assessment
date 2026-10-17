import numpy as np
import pandas as pd

from ml_inference.esm2_runtime import extract_pair
from validation.ml_benchmark.esm2_embeddings import extract_paired_embeddings
from validation.tests.test_esm2_embeddings import _ArrayTensor, _FakeModel, _FakeTokenizer, _FakeTorch


def test_installed_runtime_preserves_frozen_embedding_arithmetic():
    class SpecialTokenModel(_FakeModel):
        def __call__(self, input_ids, attention_mask):
            hidden = super().__call__(input_ids, attention_mask).last_hidden_state.value
            hidden[:, 0, :] = 1000
            hidden[:, -1, :] = 9999
            return type("Output", (), {"last_hidden_state": _ArrayTensor(hidden)})()
    tokenizer, model, torch = _FakeTokenizer(), SpecialTokenModel(), _FakeTorch()
    for vh, vl in (("AAAA", "GGGG"), ("ACDEFG", "GG"), ("AAAAAAA", "GGGGGGGG")):
        frame = pd.DataFrame([{"sequence_hash": "fixture", "VH": vh, "VL": vl}])
        frozen = extract_paired_embeddings(frame, tokenizer, model, torch, "cpu").paired_embeddings
        runtime = extract_pair(vh, vl, tokenizer, model, torch, "cpu")
        assert runtime.dtype == frozen.dtype == np.float32
        assert runtime.tobytes() == frozen.tobytes()
        assert np.all(runtime[:, :640] == 1.0)
        assert np.all(runtime[:, 640:] == 2.0)
