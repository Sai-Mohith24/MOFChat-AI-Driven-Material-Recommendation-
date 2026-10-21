"""
train_ft.py - self-supervised FT-Transformer embeddings for "find MOFs similar to X".

  python train_ft.py

1. Preprocess all 10 numeric descriptors (log1p for heavy-tailed ones, z-score)
   plus primary metal and open-metal-site flag as categorical tokens.
2. Train an FT-Transformer masked autoencoder: 30 % of descriptor tokens are
   replaced by a [MASK] token and the [CLS] state must reconstruct all
   descriptors (train/validation split, early stopping, fixed seed).
3. Embed every MOF (L2-normalised [CLS] state) and build a FAISS inner-product
   (= cosine) index.
4. Evaluate: reconstruction R^2 per descriptor and similarity quality against
   a plain k-NN on the standardised descriptors and a random baseline.

Outputs in artifacts/ft_embeddings/: model.pt, preprocessor.json, ids.json,
embeddings.npy, index.faiss, metrics.json, training_curve.png
"""

import json
import time

# PyTorch stays single-threaded (the mofchat default): with 8 threads the first numpy -> tensor copy
# segfaults on macOS (torch 2.13, 2026-10). One thread trains in about 90 s.
from mofchat._faiss import faiss  # import order matters on macOS (see mofchat/_faiss.py)

import matplotlib
import numpy as np
import torch

matplotlib.use("Agg")
import matplotlib.pyplot as plt

from mofchat.config import FT_EMBED_DIR, RANDOM_SEED
from mofchat.db import load_materials
from mofchat.features import SSL_CATEGORICAL, SSL_NUMERIC, Preprocessor
from mofchat.ft_transformer import FTMaskedAutoencoder, FTTransformer

MODEL_CFG = dict(d_token=64, n_layers=3, n_heads=4, ffn_mult=2.0, dropout=0.1)
EPOCHS, BATCH, LR, PATIENCE, MASK_P = 200, 256, 1e-3, 15, 0.3


def set_seed(seed=RANDOM_SEED):
    np.random.seed(seed)
    torch.manual_seed(seed)


def train():
    set_seed()
    FT_EMBED_DIR.mkdir(parents=True, exist_ok=True)
    df = load_materials()
    pre = Preprocessor(SSL_NUMERIC, SSL_CATEGORICAL, Preprocessor.default_log_cols(SSL_NUMERIC)).fit(df)
    Xn = torch.tensor(pre.transform_num(df))
    Xc = torch.tensor(pre.transform_cat(df))

    rng = np.random.default_rng(RANDOM_SEED)
    perm = rng.permutation(len(df))
    n_val = int(0.15 * len(df))
    va, tr = perm[:n_val], perm[n_val:]
    g = torch.Generator().manual_seed(RANDOM_SEED)
    val_mask = torch.rand(Xn[va].shape, generator=g) < MASK_P   # fixed mask -> comparable val loss

    backbone = FTTransformer(len(SSL_NUMERIC), pre.cardinalities(), **MODEL_CFG)
    model = FTMaskedAutoencoder(backbone, mask_prob=MASK_P)
    opt = torch.optim.AdamW(model.parameters(), lr=LR, weight_decay=1e-5)
    sched = torch.optim.lr_scheduler.ReduceLROnPlateau(opt, factor=0.5, patience=5)

    best, best_state, wait, hist = float("inf"), None, 0, {"train": [], "val": []}
    t0 = time.time()
    for epoch in range(EPOCHS):
        model.train()
        order = tr[torch.randperm(len(tr), generator=g).numpy()]
        tot = 0.0
        for s in range(0, len(order), BATCH):
            b = order[s:s + BATCH]
            _, rec, _ = model(Xn[b], Xc[b])
            loss = torch.nn.functional.mse_loss(rec, Xn[b])
            opt.zero_grad()
            loss.backward()
            opt.step()
            tot += loss.item() * len(b)
        model.eval()
        with torch.no_grad():
            _, rec, _ = model(Xn[va], Xc[va], mask=val_mask)
            vloss = torch.nn.functional.mse_loss(rec, Xn[va]).item()
        hist["train"].append(tot / len(tr))
        hist["val"].append(vloss)
        sched.step(vloss)
        if vloss < best - 1e-5:
            best, wait = vloss, 0
            best_state = {k: v.clone() for k, v in model.state_dict().items()}
        else:
            wait += 1
        if epoch % 10 == 0 or wait == 0 and epoch % 5 == 0:
            print(f"epoch {epoch:3d}  train {hist['train'][-1]:.4f}  val(masked) {vloss:.4f}")
        if wait >= PATIENCE:
            print(f"early stop at epoch {epoch} (best val {best:.4f})")
            break
    model.load_state_dict(best_state)
    train_time = time.time() - t0

    # ---- reconstruction quality on validation (unmasked and masked)
    model.eval()
    with torch.no_grad():
        _, rec_full, _ = model(Xn[va], Xc[va], mask=torch.zeros_like(val_mask))
        _, rec_mask, _ = model(Xn[va], Xc[va], mask=val_mask)
    y = Xn[va].numpy()
    r2_full = {c: float(1 - ((y[:, j] - rec_full[:, j].numpy()) ** 2).sum() / ((y[:, j] - y[:, j].mean()) ** 2).sum())
               for j, c in enumerate(SSL_NUMERIC)}
    mj = val_mask.numpy()
    r2_masked = {}
    for j, c in enumerate(SSL_NUMERIC):
        sel = mj[:, j]
        yt, yp = y[sel, j], rec_mask.numpy()[sel, j]
        r2_masked[c] = float(1 - ((yt - yp) ** 2).sum() / ((yt - yt.mean()) ** 2).sum())

    # ---- embeddings + FAISS index
    with torch.no_grad():
        emb = model.embed(Xn, Xc).numpy().astype("float32")
    index = faiss.IndexFlatIP(emb.shape[1])
    index.add(emb)

    torch.save({"state_dict": model.state_dict(), "backbone_config": backbone.config, "mask_prob": MASK_P},
               FT_EMBED_DIR / "model.pt")
    pre.save(FT_EMBED_DIR / "preprocessor.json")
    np.save(FT_EMBED_DIR / "embeddings.npy", emb)
    faiss.write_index(index, str(FT_EMBED_DIR / "index.faiss"))
    (FT_EMBED_DIR / "ids.json").write_text(json.dumps(df["MOF_ID"].tolist()))

    sim = evaluate_similarity(emb, Xn.numpy(), Xc.numpy())
    metrics = {"epochs_trained": len(hist["val"]), "best_val_masked_mse": best, "train_seconds": round(train_time, 1),
               "model": MODEL_CFG, "mask_prob": MASK_P, "n_params": sum(p.numel() for p in model.parameters()),
               "reconstruction_r2_unmasked": r2_full, "reconstruction_r2_masked": r2_masked, "similarity": sim}
    (FT_EMBED_DIR / "metrics.json").write_text(json.dumps(metrics, indent=2))

    plt.figure(figsize=(6, 4))
    plt.plot(hist["train"], label="train (random mask)")
    plt.plot(hist["val"], label="validation (fixed mask)")
    plt.xlabel("epoch"), plt.ylabel("MSE (standardised units)"), plt.yscale("log")
    plt.title("FT-Transformer masked-autoencoder training")
    plt.legend(), plt.tight_layout()
    plt.savefig(FT_EMBED_DIR / "training_curve.png", dpi=150)
    print(json.dumps({k: metrics[k] for k in ("epochs_trained", "best_val_masked_mse", "train_seconds")}, indent=2))
    print("similarity:", json.dumps(sim, indent=2))


def evaluate_similarity(emb, Z, C, n_queries=1000, k=10):
    """Do embedding neighbours have similar descriptors? Compared with k-NN on the
    standardised descriptors themselves (a strong baseline) and random MOFs."""
    rng = np.random.default_rng(RANDOM_SEED)
    q = rng.choice(len(emb), n_queries, replace=False)
    idx_ft = faiss.IndexFlatIP(emb.shape[1]); idx_ft.add(emb)
    _, ft_nn = idx_ft.search(emb[q], k + 1)
    Zc = np.ascontiguousarray(Z.astype("float32"))
    idx_raw = faiss.IndexFlatL2(Zc.shape[1]); idx_raw.add(Zc)
    _, raw_nn = idx_raw.search(Zc[q], k + 1)
    rand_nn = rng.integers(0, len(emb), size=(n_queries, k))

    def drop_self(nn, qi):
        return np.array([[j for j in row if j != i][:k] for row, i in zip(nn, qi)])

    ft_nn, raw_nn = drop_self(ft_nn, q), drop_self(raw_nn, q)

    def score(nn):
        dz = np.abs(Z[nn] - Z[q][:, None, :]).mean(axis=(1, 2))            # mean |Δ| in std units
        same_metal = (C[nn][:, :, 0] == C[q][:, None, 0]).mean()
        same_oms = (C[nn][:, :, 1] == C[q][:, None, 1]).mean()
        return {"mean_abs_descriptor_diff_std": float(dz.mean()), "same_metal_rate": float(same_metal),
                "same_open_metal_site_rate": float(same_oms)}

    overlap = np.mean([len(set(a) & set(b)) / k for a, b in zip(ft_nn, raw_nn)])
    return {"k": k, "n_queries": n_queries, "ft_embedding": score(ft_nn), "raw_descriptor_knn": score(raw_nn),
            "random": score(rand_nn), "overlap_ft_vs_raw_knn": float(overlap)}


if __name__ == "__main__":
    train()
