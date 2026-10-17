"""Installed-runtime ESM2 primitives; no validation dataset dependency.

The arithmetic and token handling follow the frozen Phase 5 extractor.
Parity is checked with synthetic tensors, without downloading weights.
"""
from __future__ import annotations

import hashlib
import random
from pathlib import Path

import numpy as np


def file_sha256(path: str | Path) -> str:
    digest = hashlib.sha256()
    with Path(path).open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def load_frozen_model(model_name: str, revision: str):
    import torch
    from transformers import AutoModel, AutoTokenizer

    tokenizer = AutoTokenizer.from_pretrained(model_name, revision=revision)
    model = AutoModel.from_pretrained(model_name, revision=revision, torch_dtype=torch.float32)
    if int(getattr(model.config, "hidden_size", -1)) != 640:
        raise ValueError("Expected frozen ESM2 hidden size 640")
    device = torch.device("cuda" if torch.cuda.is_available() else "cpu")
    model = model.to(device)
    model.eval()
    random.seed(20260919)
    np.random.seed(20260919)
    torch.manual_seed(20260919)
    if torch.cuda.is_available():
        torch.cuda.manual_seed_all(20260919)
    torch.use_deterministic_algorithms(True)
    return tokenizer, model, revision, {"device": str(device)}


def _embed_chain(sequence, tokenizer, model, torch_module, device):
    encoded = tokenizer(
        [sequence], padding=True, truncation=False,
        return_attention_mask=True, return_special_tokens_mask=True, return_tensors="pt",
    )
    ids, attention = encoded["input_ids"], encoded["attention_mask"]
    special = encoded["special_tokens_mask"]
    limit = getattr(getattr(model, "config", None), "max_position_embeddings", None)
    if limit is not None and int(ids.shape[1]) > int(limit):
        raise ValueError("Sequence exceeds frozen ESM2 token limit; truncation is disabled")
    with torch_module.inference_mode():
        output = model(input_ids=ids.to(device), attention_mask=attention.to(device))
    hidden = output.last_hidden_state if hasattr(output, "last_hidden_state") else output[0]
    hidden = np.asarray(hidden.detach().float().cpu().numpy(), dtype=np.float32)
    mask = np.asarray(attention.detach().cpu().numpy(), dtype=bool) & ~np.asarray(special.detach().cpu().numpy(), dtype=bool)
    counts = mask.sum(axis=1)
    if (counts == 0).any():
        raise ValueError("Tokenized sequence has no residue tokens")
    return np.asarray((hidden * mask[:, :, None]).sum(axis=1) / counts[:, None], dtype=np.float32)


def extract_pair(vh, vl, tokenizer, model, torch_module, device):
    model.eval()
    heavy = _embed_chain(vh, tokenizer, model, torch_module, device)
    light = _embed_chain(vl, tokenizer, model, torch_module, device)
    paired = np.concatenate([heavy, light], axis=1).astype(np.float32, copy=False)
    if paired.shape != (1, 1280) or not np.isfinite(paired).all() or np.linalg.norm(paired) <= 0:
        raise ValueError("Expected one finite, nonzero paired ESM2 embedding")
    return paired
