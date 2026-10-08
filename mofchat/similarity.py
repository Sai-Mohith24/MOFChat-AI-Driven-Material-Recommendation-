"""'Find MOFs similar to X' using the self-supervised FT-Transformer embeddings."""

from __future__ import annotations

import json
from functools import lru_cache

import numpy as np

from ._faiss import faiss
from .config import FT_EMBED_DIR
from .db import load_materials
from .features import SSL_CATEGORICAL, SSL_NUMERIC, Preprocessor


@lru_cache(maxsize=1)
def _index():
    if (FT_EMBED_DIR / "index.faiss").exists():
        ids = json.loads((FT_EMBED_DIR / "ids.json").read_text())
        emb = np.load(FT_EMBED_DIR / "embeddings.npy")
        return "ft_embedding", ids, emb, faiss.read_index(str(FT_EMBED_DIR / "index.faiss"))
    # Fallback: k-NN on standardised descriptors (works before train_ft.py has been run).
    df = load_materials()
    pre = Preprocessor(SSL_NUMERIC, SSL_CATEGORICAL, Preprocessor.default_log_cols(SSL_NUMERIC)).fit(df)
    Z = np.ascontiguousarray(pre.transform_num(df))
    Z /= np.linalg.norm(Z, axis=1, keepdims=True) + 1e-9
    idx = faiss.IndexFlatIP(Z.shape[1])
    idx.add(Z)
    return "descriptor_knn", df["MOF_ID"].tolist(), Z, idx


def method() -> str:
    return _index()[0]


def similar(mof_id: str, k: int = 5, candidates: set[str] | None = None) -> list[tuple[str, float]]:
    """Top-k most similar MOFs (cosine similarity), optionally restricted to `candidates`."""
    _, ids, emb, idx = _index()
    pos = {m: i for i, m in enumerate(ids)}
    if mof_id not in pos:
        return []
    want = k + 1 if candidates is None else min(len(ids), max(200, 20 * k))
    sims, nn = idx.search(emb[pos[mof_id]:pos[mof_id] + 1], want)
    out = []
    for s, j in zip(sims[0], nn[0]):
        m = ids[j]
        if m == mof_id or (candidates is not None and m not in candidates):
            continue
        out.append((m, float(s)))
        if len(out) >= k:
            break
    return out
