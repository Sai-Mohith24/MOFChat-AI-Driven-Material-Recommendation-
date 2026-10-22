"""
evaluate_dl.py - classification results, learning curves and feature-extraction graphs.

  python evaluate_dl.py

The production models are not changed; this script only measures and plots.

A. Open-metal-site (OMS) classification: a real label in the database (66 % of MOFs have an open
   metal site). Inputs are the ten geometric descriptors plus the primary metal; OMS_Type is left
   out because it would give the answer away. Models: majority baseline, logistic regression,
   XGBoost, an MLP and an FT-Transformer classifier, on a stratified 70/15/15 train/val/test split.
   Reports accuracy, precision, recall, F1, ROC-AUC, PR-AUC, confusion matrices, ROC/PR curves and
   per-epoch train/validation loss and accuracy.
B. Intent classification by the planner, from the saved benchmark plans (no new LLM calls).
C. Off-topic detection by the knowledge retriever: ROC of the top cosine score.
D. The 3.31 A physics rule as a classifier of accessible vs non-accessible MOFs.
E. Regression learning curves: FT-Transformer train/val loss and R2 per epoch, XGBoost train/val
   RMSE per boosting round, and train/val/test metrics of the production XGBoost models.
F. Feature extraction: descriptor distributions, correlations, PCA, t-SNE of the FT embeddings,
   masked-reconstruction R2, attention, XGBoost importance.

Outputs: artifacts/dl_eval/*.png, artifacts/dl_eval/metrics.json and docs/DL_RESULTS.md.
"""

import json
import math
import time

import mofchat  # noqa: F401  (sets the safe torch/faiss import order)

import matplotlib
import numpy as np
import pandas as pd
import torch
import xgboost as xgb
from sklearn.decomposition import PCA
from sklearn.linear_model import LogisticRegression
from sklearn.manifold import TSNE
from sklearn.metrics import (accuracy_score, average_precision_score, confusion_matrix, f1_score,
                             precision_recall_curve, precision_score, r2_score, recall_score, roc_auc_score,
                             roc_curve, mean_absolute_error, mean_squared_error)
from sklearn.model_selection import train_test_split

matplotlib.use("Agg")
import matplotlib.pyplot as plt

from mofchat import knowledge
from mofchat.config import ARTIFACTS_DIR, EVAL_DIR, FT_EMBED_DIR, PROJECT_ROOT as ROOT, PROPERTY_MODEL_DIR, RANDOM_SEED
from mofchat.db import load_materials
from mofchat.features import PROPERTY_TARGETS, SSL_NUMERIC, Preprocessor, primary_metal
from mofchat.ft_transformer import FTRegressor, FTTransformer
from train_property_models import FT_CFG, split

OUT = ARTIFACTS_DIR / "dl_eval"
EVAL = EVAL_DIR
FT_DIR = FT_EMBED_DIR
# Office palette of the review-1 template
BLUE, RED, GREEN, PURPLE, AQUA, ORANGE, GREY = "#4F81BD", "#C0504D", "#9BBB59", "#8064A2", "#4BACC6", "#F79646", "#A6A6A6"
plt.rcParams.update({"font.family": "Arial", "font.size": 11, "axes.spines.top": False, "axes.spines.right": False,
                     "axes.titleweight": "bold", "figure.dpi": 100})


def save(fig, name):
    fig.tight_layout()
    fig.savefig(OUT / name, dpi=200)
    plt.close(fig)


def cls_metrics(y, prob, thr=0.5):
    pred = (prob >= thr).astype(int)
    return {"accuracy": accuracy_score(y, pred), "precision": precision_score(y, pred, zero_division=0),
            "recall": recall_score(y, pred), "f1": f1_score(y, pred),
            "roc_auc": roc_auc_score(y, prob) if len(set(prob)) > 1 else 0.5,
            "pr_auc": average_precision_score(y, prob), "confusion": confusion_matrix(y, pred).tolist()}


def plot_cm(ax, cm, labels, title, cmap="Blues"):
    cm = np.asarray(cm)
    ax.imshow(cm, cmap=cmap)
    ax.set(xticks=range(len(labels)), yticks=range(len(labels)), xticklabels=labels, yticklabels=labels,
           xlabel="Predicted", ylabel="Actual", title=title)
    plt.setp(ax.get_xticklabels(), rotation=30 if len(labels) > 3 else 0, ha="right" if len(labels) > 3 else "center")
    thr = cm.max() / 2
    for i in range(cm.shape[0]):
        for j in range(cm.shape[1]):
            ax.text(j, i, int(cm[i, j]), ha="center", va="center", color="white" if cm[i, j] > thr else "black",
                    fontsize=11 if len(labels) <= 4 else 9)


# ------------------------------------------------------------- deep models
class FTClassifier(torch.nn.Module):
    def __init__(self, backbone):
        super().__init__()
        self.backbone = backbone
        self.head = torch.nn.Sequential(torch.nn.ReLU(), torch.nn.Linear(backbone.config["d_token"], 1))

    def forward(self, x_num, x_cat=None):
        return self.head(self.backbone(x_num, x_cat)).squeeze(-1)


class MLP(torch.nn.Module):
    def __init__(self, n_num, n_metal, d=128, emb=8):
        super().__init__()
        self.emb = torch.nn.Embedding(n_metal, emb)
        self.net = torch.nn.Sequential(torch.nn.Linear(n_num + emb, d), torch.nn.ReLU(), torch.nn.Dropout(0.1),
                                       torch.nn.Linear(d, d), torch.nn.ReLU(), torch.nn.Dropout(0.1),
                                       torch.nn.Linear(d, 1))

    def forward(self, x_num, x_cat):
        return self.net(torch.cat([x_num, self.emb(x_cat[:, 0])], 1)).squeeze(-1)


def train_binary(model, data, epochs=200, patience=20, batch=256, lr=1e-3):
    """Early stopping on validation loss; returns the best model and per-epoch history."""
    (Xtr, Ctr, ytr), (Xva, Cva, yva) = data
    torch.manual_seed(RANDOM_SEED)
    opt = torch.optim.AdamW(model.parameters(), lr=lr, weight_decay=1e-5)
    lossf = torch.nn.BCEWithLogitsLoss()
    g = torch.Generator().manual_seed(RANDOM_SEED)
    hist = {"train_loss": [], "val_loss": [], "train_acc": [], "val_acc": []}
    best, state, wait = float("inf"), None, 0
    for _ in range(epochs):
        model.train()
        order = torch.randperm(len(Xtr), generator=g)
        for s in range(0, len(order), batch):
            b = order[s:s + batch]
            loss = lossf(model(Xtr[b], Ctr[b]), ytr[b])
            opt.zero_grad()
            loss.backward()
            opt.step()
        model.eval()
        with torch.no_grad():
            for X, C, y, tag in ((Xtr, Ctr, ytr, "train"), (Xva, Cva, yva, "val")):
                z = model(X, C)
                hist[f"{tag}_loss"].append(lossf(z, y).item())
                hist[f"{tag}_acc"].append(((z > 0).float() == y).float().mean().item())
        v = hist["val_loss"][-1]
        if v < best - 1e-5:
            best, wait, state = v, 0, {k: t.clone() for k, t in model.state_dict().items()}
            hist["best_epoch"] = len(hist["val_loss"])
        else:
            wait += 1
            if wait >= patience:
                break
    model.load_state_dict(state)
    model.eval()
    return model, hist


# ------------------------------------------------------- A. OMS classifier
def oms_classification(df):
    y = df["Has_OMS"].to_numpy(int)
    idx = np.arange(len(df))
    tr, rest = train_test_split(idx, test_size=0.30, stratify=y, random_state=RANDOM_SEED)
    va, te = train_test_split(rest, test_size=0.50, stratify=y[rest], random_state=RANDOM_SEED)
    pre = Preprocessor(SSL_NUMERIC, ["Metal_Group"], Preprocessor.default_log_cols(SSL_NUMERIC)).fit(df.iloc[tr])
    Z, Cat = pre.transform_num(df), pre.transform_cat(df)
    n_metal = pre.cardinalities()[0]
    res = {"task": "Has_OMS from 10 geometric descriptors + primary metal",
           "split": {"train": len(tr), "val": len(va), "test": len(te)},
           "positive_rate": float(y.mean()), "models": {}, "history": {}}
    probs = {}

    probs["Majority baseline"] = np.full(len(te), float(y[tr].mean()))

    onehot = np.eye(n_metal)[Cat[:, 0]]
    Xlin = np.hstack([Z, onehot])
    lr_ = LogisticRegression(max_iter=2000).fit(Xlin[tr], y[tr])
    probs["Logistic regression"] = lr_.predict_proba(Xlin[te])[:, 1]

    Xx = pd.DataFrame(Z, columns=SSL_NUMERIC).assign(metal=pd.Categorical(Cat[:, 0]))
    t = time.time()
    xg = xgb.XGBClassifier(n_estimators=2000, learning_rate=0.03, max_depth=6, subsample=0.8, colsample_bytree=0.9,
                           early_stopping_rounds=100, eval_metric=["logloss", "error"], enable_categorical=True,
                           tree_method="hist", random_state=RANDOM_SEED, n_jobs=4)
    xg.fit(Xx.iloc[tr], y[tr], eval_set=[(Xx.iloc[tr], y[tr]), (Xx.iloc[va], y[va])], verbose=False)
    res["xgb_seconds"] = round(time.time() - t, 2)
    ev = xg.evals_result()
    res["history"]["XGBoost"] = {"train_loss": ev["validation_0"]["logloss"], "val_loss": ev["validation_1"]["logloss"],
                                 "train_acc": [1 - e for e in ev["validation_0"]["error"]],
                                 "val_acc": [1 - e for e in ev["validation_1"]["error"]],
                                 "best_epoch": int(xg.best_iteration) + 1}
    probs["XGBoost"] = xg.predict_proba(Xx.iloc[te])[:, 1]
    imp = xg.get_booster().get_score(importance_type="gain")
    res["xgb_gain"] = {(SSL_NUMERIC + ["metal"])[int(k[1:])] if k.startswith("f") else k: float(v) for k, v in imp.items()}

    T = lambda a, dt=torch.float32: torch.tensor(a, dtype=dt)  # noqa: E731
    data = lambda ids: (T(Z[ids]), T(Cat[ids], torch.long), T(y[ids]))  # noqa: E731
    for name, model in (("MLP", MLP(len(SSL_NUMERIC), n_metal)),
                        ("FT-Transformer", FTClassifier(FTTransformer(len(SSL_NUMERIC), (n_metal,), **FT_CFG)))):
        t = time.time()
        model, hist = train_binary(model, (data(tr), data(va)))
        res[f"{name}_seconds"] = round(time.time() - t, 1)
        res["history"][name] = hist
        Xte, Cte, _ = data(te)
        with torch.no_grad():
            probs[name] = torch.sigmoid(model(Xte, Cte)).numpy()
        if name == "FT-Transformer":
            res["ft_params"] = sum(p.numel() for p in model.parameters())
            with torch.no_grad():
                _, att = model.backbone(Xte, Cte, return_attention=True)
            res["ft_attention"] = dict(zip(SSL_NUMERIC + ["metal"], map(float, att[-1][:, 0, 1:].mean(0).numpy())))
        # train/val/test accuracy of the final model
        with torch.no_grad():
            res["models"].setdefault(name, {})["acc_train_val_test"] = [
                float(((model(*data(ids)[:2]) > 0).numpy() == y[ids]).mean()) for ids in (tr, va, te)]

    for name, p in probs.items():
        res["models"].setdefault(name, {}).update(cls_metrics(y[te], p))
    res["models"]["XGBoost"]["acc_train_val_test"] = [
        float((xg.predict(Xx.iloc[ids]) == y[ids]).mean()) for ids in (tr, va, te)]
    res["models"]["Logistic regression"]["acc_train_val_test"] = [
        float((lr_.predict(Xlin[ids]) == y[ids]).mean()) for ids in (tr, va, te)]

    # --- figures
    colors = {"Majority baseline": GREY, "Logistic regression": GREEN, "XGBoost": BLUE, "MLP": PURPLE,
              "FT-Transformer": RED}
    fig, axes = plt.subplots(1, 2, figsize=(11, 4.6))
    for name, p in probs.items():
        fpr, tpr, _ = roc_curve(y[te], p)
        axes[0].plot(fpr, tpr, color=colors[name], lw=2, label=f"{name} (AUC = {res['models'][name]['roc_auc']:.3f})")
        pr, rc, _ = precision_recall_curve(y[te], p)
        axes[1].plot(rc, pr, color=colors[name], lw=2, label=f"{name} (AP = {res['models'][name]['pr_auc']:.3f})")
    axes[0].plot([0, 1], [0, 1], "k--", lw=1)
    axes[0].set(xlabel="False positive rate", ylabel="True positive rate", title="ROC curve (test set)")
    axes[1].set(xlabel="Recall", ylabel="Precision", title="Precision-recall curve (test set)", ylim=(0.6, 1.01))
    for ax in axes:
        ax.legend(fontsize=9, loc="lower right" if ax is axes[0] else "lower left")
    save(fig, "oms_roc_pr.png")

    fig, axes = plt.subplots(1, 4, figsize=(15, 3.9))
    for ax, name in zip(axes, ["Logistic regression", "XGBoost", "MLP", "FT-Transformer"]):
        m = res["models"][name]
        plot_cm(ax, m["confusion"], ["No OMS", "OMS"], f"{name}\nacc {m['accuracy']:.3f}")
    save(fig, "oms_confusion.png")

    fig, axes = plt.subplots(2, 3, figsize=(15, 7.6))
    for col, name in enumerate(["FT-Transformer", "MLP", "XGBoost"]):
        h = res["history"][name]
        xs = np.arange(1, len(h["train_loss"]) + 1)
        unit = "boosting round" if name == "XGBoost" else "epoch"
        axes[0, col].plot(xs, h["train_loss"], color=BLUE, lw=2, label="train")
        axes[0, col].plot(xs, h["val_loss"], color=RED, lw=2, label="validation")
        axes[1, col].plot(xs, h["train_acc"], color=BLUE, lw=2, label="train")
        axes[1, col].plot(xs, h["val_acc"], color=RED, lw=2, label="validation")
        te_acc = res["models"][name]["accuracy"]
        axes[1, col].axhline(te_acc, color=GREEN, ls="--", lw=1.5, label=f"test = {te_acc:.3f}")
        for r in (0, 1):
            axes[r, col].axvline(h["best_epoch"], color=GREY, ls=":", lw=1.2)
            axes[r, col].legend(fontsize=9)
        axes[0, col].set(title=f"{name}: loss", xlabel=unit, ylabel="binary cross-entropy")
        axes[1, col].set(title=f"{name}: accuracy", xlabel=unit, ylabel="accuracy")
    save(fig, "oms_learning_curves.png")

    fig, ax = plt.subplots(figsize=(6.5, 3.8))
    att = res["ft_attention"]
    ax.barh(list(att)[::-1], list(att.values())[::-1], color=RED)
    ax.set(xlabel="mean [CLS] attention (last layer)", title="FT-Transformer attention, OMS classifier")
    save(fig, "oms_ft_attention.png")
    return res


# ----------------------------------------------------- B. intent classifier
INTENT_LABELS = ["search", "count", "lookup", "similar", "predict", "knowledge", "out_of_scope"]


def _intent(plan):
    return str(plan).split(";")[0].replace("intent=", "").strip() if isinstance(plan, str) else "failed"


def intent_classification():
    bench = pd.read_csv(EVAL / "benchmark_results.csv")
    comp = pd.read_csv(EVAL / "model_comparison.csv")
    runs = {"Rules planner (no LLM)": bench[bench.system == "Rules planner (no LLM)"]}
    for model, label in (("gemini-3.1-flash-lite", "Gemini 3.1 Flash-Lite"), ("gpt-oss-120b", "GPT-OSS 120B"),
                         ("qwen3.8-27b", "Qwen 3.8 27B"), ("llama3-local", "Llama 3 8B (local)")):
        for system, tag in (("LLM planner, single shot (no validator)", "alone"), ("Hybrid (default)", "hybrid")):
            runs[f"{label}, {tag}"] = comp[(comp.model == model) & (comp.system == system)]
    res = {}
    for name, d in runs.items():
        g, p = d.gold_plan.map(_intent), d.plan.map(_intent)
        labels = [l for l in INTENT_LABELS if l in set(g) | set(p)]
        res[name] = {"n": len(d), "accuracy": float((g == p).mean()),
                     "macro_f1": float(f1_score(g, p, labels=labels, average="macro", zero_division=0)),
                     "plan_exact": float(d.plan_correct.fillna(False).astype(bool).mean()) if d.plan_correct.notna().any() else None,
                     "labels": labels, "confusion": confusion_matrix(g, p, labels=labels).tolist()}
    fig, axes = plt.subplots(1, 3, figsize=(16, 5.2))
    for ax, name in zip(axes, ["Llama 3 8B (local), alone", "Llama 3 8B (local), hybrid", "Gemini 3.1 Flash-Lite, hybrid"]):
        r = res[name]
        plot_cm(ax, r["confusion"], r["labels"], f"{name}\nintent accuracy {r['accuracy']:.3f} (n = {r['n']})")
    save(fig, "intent_confusion.png")
    return res


# ------------------------------------------------- C. off-topic detector
EXTRA_OFF_TOPIC = ["how to bake sourdough bread", "translate good morning into French", "who wrote Hamlet",
                   "cheap flights to Delhi", "how many calories in a banana", "best laptop for gaming",
                   "explain the offside rule in football", "symptoms of the common cold", "how to train a puppy",
                   "stock price of Apple today", "plot of the movie Inception", "how to change a car tyre",
                   "what is the capital of Australia", "tips for a job interview", "how to grow tomatoes at home"]


def offtopic_detection():
    from evaluate import KNOWLEDGE_TESTS, OFF_TOPIC
    bench = json.loads((ROOT / "benchmark" / "queries.json").read_text())
    held = json.loads((ROOT / "benchmark" / "heldout.json").read_text())
    in_domain = [q for q, _ in KNOWLEDGE_TESTS] + [b["question"] for b in bench + held
                                                   if b.get("category") != "knowledge / off-topic"]
    off = OFF_TOPIC + EXTRA_OFF_TOPIC
    score = lambda q: (knowledge.search(q, 1) or [type("S", (), {"score": 0.0})()])[0].score  # noqa: E731
    s_in, s_off = [score(q) for q in in_domain], [score(q) for q in off]
    y = np.r_[np.ones(len(s_in)), np.zeros(len(s_off))]
    s = np.r_[s_in, s_off]
    thr = knowledge.RELEVANCE_THRESHOLD
    pred = (s >= thr).astype(int)
    res = {"n_in_domain": len(s_in), "n_off_topic": len(s_off), "threshold": thr, "roc_auc": roc_auc_score(y, s),
           "accuracy": accuracy_score(y, pred), "confusion": confusion_matrix(y, pred).tolist(),
           "note": "5 original off-topic questions + 15 added for this analysis; threshold fixed beforehand"}
    fig, axes = plt.subplots(1, 3, figsize=(15, 4.3))
    fpr, tpr, _ = roc_curve(y, s)
    axes[0].plot(fpr, tpr, color=BLUE, lw=2, label=f"top cosine score (AUC = {res['roc_auc']:.3f})")
    axes[0].plot([0, 1], [0, 1], "k--", lw=1)
    axes[0].set(xlabel="False positive rate", ylabel="True positive rate", title="Off-topic detector: ROC")
    axes[0].legend(fontsize=9, loc="lower right")
    bins = np.linspace(0, 1, 26)
    axes[1].hist(s_in, bins=bins, color=BLUE, alpha=0.75, label=f"MOF questions (n = {len(s_in)})")
    axes[1].hist(s_off, bins=bins, color=RED, alpha=0.75, label=f"off-topic (n = {len(s_off)})")
    axes[1].axvline(thr, color="k", ls="--", lw=1.2, label=f"threshold {thr}")
    axes[1].set(xlabel="top cosine similarity", ylabel="questions", title="Score distribution")
    axes[1].legend(fontsize=9)
    plot_cm(axes[2], res["confusion"], ["off-topic", "MOF"], f"Confusion matrix, acc {res['accuracy']:.3f}")
    save(fig, "offtopic_roc.png")
    return res


# --------------------------------------------- D. physics rule classifier
def physics_rule(df):
    thr = json.loads((PROPERTY_MODEL_DIR / "Surface_Area" / "meta.json").read_text())["hurdle_threshold"]
    _, _, _, te = split(len(df))
    d = df.iloc[te]
    y, p = (d.Surface_Area > 0).astype(int), (d.PLD >= thr).astype(int)
    res = {"threshold_A": thr, "n_test": len(d), "accuracy": accuracy_score(y, p), "confusion": confusion_matrix(y, p).tolist()}
    fig, axes = plt.subplots(1, 2, figsize=(11, 4.2))
    acc = df.Surface_Area > 0
    axes[0].scatter(df.PLD[~acc], df.Surface_Area[~acc], s=4, color=RED, alpha=0.5, label="zero surface area")
    axes[0].scatter(df.PLD[acc], df.Surface_Area[acc], s=4, color=BLUE, alpha=0.3, label="accessible")
    axes[0].axvline(thr, color="k", ls="--", lw=1.2, label=f"PLD = {thr:.2f} Å (probe)")
    axes[0].set(xscale="log", xlabel="pore limiting diameter PLD (Å, log scale)", ylabel="surface area (m²/g)",
                title="Zero surface area exactly when PLD < probe")
    axes[0].set_xticks([2, 3, 5, 10, 20, 50])
    axes[0].set_xticklabels(["2", "3", "5", "10", "20", "50"])
    axes[0].minorticks_off()
    axes[0].legend(fontsize=9, markerscale=3)
    plot_cm(axes[1], res["confusion"], ["zero area", "accessible"], f"Physics rule on test set, acc {res['accuracy']:.3f}")
    save(fig, "physics_rule.png")
    return res


# ---------------------------------------- E. regression learning curves
def regression_curves(df):
    res = {}
    fig, axes = plt.subplots(2, 3, figsize=(15, 7.6))
    for row, (target, spec) in enumerate(PROPERTY_TARGETS.items()):
        feats = spec["features"]
        tr, va, ca, te = split(len(df))
        y = df[target].to_numpy(float)
        mask = (df.PLD >= json.loads((PROPERTY_MODEL_DIR / target / "meta.json").read_text())["hurdle_threshold"]).to_numpy() \
            if spec["hurdle"] else np.ones(len(df), bool)
        trA, vaA, teA = tr[mask[tr]], va[mask[va]], te[mask[te]]
        X = df[feats]
        # production XGBoost: train / val / test metrics
        prod = xgb.XGBRegressor()
        prod.load_model(PROPERTY_MODEL_DIR / target / "xgb.json")
        split_metrics = {}
        for tag, ids in (("train", trA), ("val", vaA), ("test", teA)):
            p = prod.predict(X.iloc[ids])
            split_metrics[tag] = {"R2": r2_score(y[ids], p), "MAE": mean_absolute_error(y[ids], p),
                                  "RMSE": math.sqrt(mean_squared_error(y[ids], p))}
        # XGBoost curve (same settings as production, eval on train and val)
        m = xgb.XGBRegressor(n_estimators=4000, learning_rate=0.03, max_depth=6, subsample=0.8, colsample_bytree=0.9,
                             min_child_weight=2, reg_lambda=1.0, early_stopping_rounds=150, eval_metric="rmse",
                             random_state=RANDOM_SEED, n_jobs=4)
        m.fit(X.iloc[trA], y[trA], eval_set=[(X.iloc[trA], y[trA]), (X.iloc[vaA], y[vaA])], verbose=False)
        ev = m.evals_result()
        # FT-Transformer regressor curve (same settings as production), loss and R2 per epoch
        pre = Preprocessor(feats, [], Preprocessor.default_log_cols(feats)).fit(df.iloc[trA])
        Z = pre.transform_num(df)
        mu, sd = y[trA].mean(), y[trA].std()
        Xt, yt, Xv, yv = (torch.tensor(a, dtype=torch.float32) for a in (Z[trA], (y[trA] - mu) / sd, Z[vaA], (y[vaA] - mu) / sd))
        torch.manual_seed(RANDOM_SEED)
        model = FTRegressor(FTTransformer(len(feats), (), **FT_CFG))
        opt = torch.optim.AdamW(model.parameters(), lr=1e-3, weight_decay=1e-5)
        sched = torch.optim.lr_scheduler.ReduceLROnPlateau(opt, factor=0.5, patience=8)
        g = torch.Generator().manual_seed(RANDOM_SEED)
        h = {"train_loss": [], "val_loss": [], "train_r2": [], "val_r2": []}
        best, wait, state = float("inf"), 0, None
        for _ in range(400):
            model.train()
            order = torch.randperm(len(Xt), generator=g)
            for s in range(0, len(order), 256):
                b = order[s:s + 256]
                loss = torch.nn.functional.mse_loss(model(Xt[b]), yt[b])
                opt.zero_grad()
                loss.backward()
                opt.step()
            model.eval()
            with torch.no_grad():
                pt, pv = model(Xt), model(Xv)
                h["train_loss"].append(torch.nn.functional.mse_loss(pt, yt).item())
                h["val_loss"].append(torch.nn.functional.mse_loss(pv, yv).item())
                h["train_r2"].append(r2_score(yt.numpy(), pt.numpy()))
                h["val_r2"].append(r2_score(yv.numpy(), pv.numpy()))
            sched.step(h["val_loss"][-1])
            if h["val_loss"][-1] < best - 1e-6:
                best, wait, state = h["val_loss"][-1], 0, {k: t.clone() for k, t in model.state_dict().items()}
                h["best_epoch"] = len(h["val_loss"])
            else:
                wait += 1
                if wait >= 25:
                    break
        model.load_state_dict(state)
        with torch.no_grad():
            ft_test_r2 = r2_score(y[teA], model(torch.tensor(Z[teA], dtype=torch.float32)).numpy() * sd + mu)
        res[target] = {"xgb_production_split_metrics": split_metrics, "xgb_best_round": int(m.best_iteration) + 1,
                       "ft_epochs": len(h["val_loss"]), "ft_best_epoch": h["best_epoch"],
                       "ft_final": {"train_r2": h["train_r2"][h["best_epoch"] - 1], "val_r2": h["val_r2"][h["best_epoch"] - 1],
                                    "test_r2_accessible": ft_test_r2}}
        xs = np.arange(1, len(h["train_loss"]) + 1)
        axes[row, 0].plot(xs, h["train_loss"], color=BLUE, lw=2, label="train")
        axes[row, 0].plot(xs, h["val_loss"], color=RED, lw=2, label="validation")
        axes[row, 0].set(title=f"FT-Transformer, {target}: loss", xlabel="epoch", ylabel="MSE (standardised)", yscale="log")
        axes[row, 1].plot(xs, h["train_r2"], color=BLUE, lw=2, label="train")
        axes[row, 1].plot(xs, h["val_r2"], color=RED, lw=2, label="validation")
        axes[row, 1].axhline(ft_test_r2, color=GREEN, ls="--", lw=1.5, label=f"test = {ft_test_r2:.3f}")
        axes[row, 1].set(title=f"FT-Transformer, {target}: R²", xlabel="epoch", ylabel="R²",
                         ylim=(max(0.5, min(h["val_r2"]) - 0.02), 1.0))
        rx = np.arange(1, len(ev["validation_0"]["rmse"]) + 1)
        axes[row, 2].plot(rx, ev["validation_0"]["rmse"], color=BLUE, lw=2, label="train")
        axes[row, 2].plot(rx, ev["validation_1"]["rmse"], color=RED, lw=2, label="validation")
        axes[row, 2].set(title=f"XGBoost, {target}: RMSE", xlabel="boosting round", ylabel="RMSE", yscale="log")
        for c in range(3):
            if c < 2:
                axes[row, c].axvline(h["best_epoch"], color=GREY, ls=":", lw=1.2)
            axes[row, c].legend(fontsize=9)
    save(fig, "regression_learning_curves.png")
    return res


# ------------------------------------------------- F. feature extraction
def feature_graphs(df):
    res = {}
    num = SSL_NUMERIC
    fig, axes = plt.subplots(2, 5, figsize=(17, 6.4))
    for ax, c in zip(axes.ravel(), num):
        v = df[c].to_numpy(float)
        ax.hist(v, bins=60, color=BLUE, alpha=0.85)
        ax.set(title=c, ylabel="MOFs" if ax in axes[:, 0] else None)
        if c not in ("Void_Fraction",) and (v > 0).any():
            ax.set_yscale("log")
    fig.suptitle("Distributions of the ten geometric descriptors (12,020 MOFs)", fontweight="bold")
    save(fig, "feat_distributions.png")

    corr = df[num].corr()
    fig, ax = plt.subplots(figsize=(8.2, 6.8))
    im = ax.imshow(corr, cmap="RdBu_r", vmin=-1, vmax=1)
    ax.set(xticks=range(len(num)), yticks=range(len(num)), xticklabels=num, yticklabels=num, title="Pearson correlation of descriptors")
    plt.setp(ax.get_xticklabels(), rotation=40, ha="right")
    for i in range(len(num)):
        for j in range(len(num)):
            ax.text(j, i, f"{corr.iat[i, j]:.2f}", ha="center", va="center", fontsize=8,
                    color="white" if abs(corr.iat[i, j]) > 0.6 else "black")
    fig.colorbar(im, ax=ax, fraction=0.046)
    save(fig, "feat_correlation.png")
    res["strongest_correlations"] = sorted(((a, b, float(corr.loc[a, b])) for i, a in enumerate(num) for b in num[i + 1:]),
                                           key=lambda t: -abs(t[2]))[:5]

    pre = Preprocessor(num, [], Preprocessor.default_log_cols(num)).fit(df)
    Z = pre.transform_num(df)
    pca = PCA().fit(Z)
    P = pca.transform(Z)[:, :2]
    res["pca_explained"] = pca.explained_variance_ratio_.round(4).tolist()
    fig, axes = plt.subplots(1, 2, figsize=(12, 4.6))
    ev = pca.explained_variance_ratio_
    axes[0].bar(range(1, len(ev) + 1), ev, color=BLUE, label="per component")
    axes[0].plot(range(1, len(ev) + 1), np.cumsum(ev), "o-", color=RED, label="cumulative")
    axes[0].set(xlabel="principal component", ylabel="explained variance", title="PCA of standardised descriptors")
    axes[0].legend(fontsize=9)
    sc = axes[1].scatter(P[:, 0], P[:, 1], c=df.Surface_Area, cmap="viridis", s=3, alpha=0.6)
    axes[1].set(xlabel=f"PC1 ({ev[0]:.0%})", ylabel=f"PC2 ({ev[1]:.0%})", title="MOFs in PCA space")
    fig.colorbar(sc, ax=axes[1], label="surface area (m²/g)")
    save(fig, "feat_pca.png")

    emb = np.load(FT_DIR / "embeddings.npy")
    ids = json.loads((FT_DIR / "ids.json").read_text())
    sub = np.random.default_rng(RANDOM_SEED).choice(len(emb), 5000, replace=False)
    t = time.time()
    E2 = TSNE(n_components=2, perplexity=40, init="pca", random_state=RANDOM_SEED).fit_transform(emb[sub])
    res["tsne_seconds"] = round(time.time() - t, 1)
    meta = df.set_index("MOF_ID").loc[[ids[i] for i in sub]]
    metal = meta.Metal_Type.map(primary_metal)
    top = metal.value_counts().index[:6]
    fig, axes = plt.subplots(1, 2, figsize=(13, 5.4))
    axes[0].scatter(E2[:, 0], E2[:, 1], s=3, color="#D9D9D9", label="other metals")
    for c, m in zip([BLUE, RED, GREEN, PURPLE, AQUA, ORANGE], top):
        k = (metal == m).to_numpy()
        axes[0].scatter(E2[k, 0], E2[k, 1], s=4, color=c, label=m)
    axes[0].set(title="t-SNE of FT-Transformer embeddings, by metal", xticks=[], yticks=[])
    axes[0].legend(fontsize=9, markerscale=3, loc="best")
    sc = axes[1].scatter(E2[:, 0], E2[:, 1], c=np.log1p(meta.Surface_Area), cmap="viridis", s=3)
    axes[1].set(title="t-SNE of FT-Transformer embeddings, by surface area", xticks=[], yticks=[])
    fig.colorbar(sc, ax=axes[1], label="log(1 + surface area)")
    save(fig, "feat_tsne_embeddings.png")

    ftm = json.loads((FT_DIR / "metrics.json").read_text())
    rm = ftm["reconstruction_r2_masked"]
    fig, axes = plt.subplots(1, 2, figsize=(13, 4.4))
    axes[0].barh(list(rm)[::-1], [max(v, 0) for v in list(rm.values())[::-1]], color=BLUE)
    axes[0].set(xlabel="R² when the descriptor is masked", xlim=(0, 1), title="Self-supervised FT: masked reconstruction")
    pm = json.loads((PROPERTY_MODEL_DIR / "metrics.json").read_text())
    for target, col in (("Surface_Area", BLUE), ("Void_Fraction", RED)):
        s = pm[target]["shap_mean_abs"]
        tot = sum(s.values())
        axes[1].barh([f"{k} ({target.split('_')[0]})" for k in s], [v / tot for v in s.values()], color=col)
    axes[1].set(xlabel="share of mean |SHAP| (XGBoost)", title="Feature importance of the surrogates")
    save(fig, "feat_reconstruction_importance.png")

    fig, axes = plt.subplots(1, 2, figsize=(13, 4.2))
    metal_all = df.Metal_Type.map(primary_metal)
    vc = metal_all.value_counts().head(15)
    axes[0].bar(vc.index, vc.values, color=BLUE)
    axes[0].set(title="Most common primary metals", ylabel="MOFs")
    oms = df.assign(m=metal_all).groupby("m").Has_OMS.mean().loc[vc.index]
    axes[1].bar(oms.index, oms.values, color=ORANGE)
    axes[1].axhline(df.Has_OMS.mean(), color="k", ls="--", lw=1, label=f"overall {df.Has_OMS.mean():.0%}")
    axes[1].set(title="Share with an open metal site, by metal", ylabel="fraction", ylim=(0, 1))
    axes[1].legend(fontsize=9)
    save(fig, "feat_metals.png")
    return res


# ------------------------------------------------------------------ report
def write_report(r):
    o = r["oms"]
    L = ["# MOFChat - deep-learning classification, learning curves and feature extraction", "",
         f"_Generated by `python evaluate_dl.py` on {time.strftime('%Y-%m-%d %H:%M')}. Figures in `artifacts/dl_eval/`._", "",
         "MOFChat's property models are regressors (surface area, void fraction); their results are in "
         "[RESULTS.md](RESULTS.md). This file adds the classification tasks the project contains, with "
         "accuracy, ROC-AUC and confusion matrices, plus learning curves and feature-extraction graphs.", "",
         "## A. Open-metal-site classification (deep learning vs baselines)", "",
         f"Task: {o['task']}. Stratified split train {o['split']['train']} / val {o['split']['val']} / "
         f"test {o['split']['test']}; {o['positive_rate']:.1%} of MOFs have an open metal site.", "",
         "| Model | Accuracy | Precision | Recall | F1 | ROC-AUC | PR-AUC | Train / val / test acc |",
         "|---|---:|---:|---:|---:|---:|---:|---|"]
    for n, m in o["models"].items():
        tvt = " / ".join(f"{a:.3f}" for a in m["acc_train_val_test"]) if "acc_train_val_test" in m else "-"
        L.append(f"| {n} | {m['accuracy']:.3f} | {m['precision']:.3f} | {m['recall']:.3f} | {m['f1']:.3f} | "
                 f"{m['roc_auc']:.3f} | {m['pr_auc']:.3f} | {tvt} |")
    L += ["", f"FT-Transformer classifier: {o['ft_params']:,} parameters, best epoch "
          f"{o['history']['FT-Transformer']['best_epoch']}, {o['FT-Transformer_seconds']} s.", "",
          "![roc](../artifacts/dl_eval/oms_roc_pr.png)", "![cm](../artifacts/dl_eval/oms_confusion.png)",
          "![curves](../artifacts/dl_eval/oms_learning_curves.png)", "",
          "## B. Intent classification by the planner (84 benchmark questions)", "",
          "| Planner | Intent accuracy | Macro F1 | Exact plan |", "|---|---:|---:|---:|"]
    for n, m in r["intent"].items():
        pe = f"{m['plan_exact']:.3f}" if m["plan_exact"] is not None else "-"
        L.append(f"| {n} | {m['accuracy']:.3f} | {m['macro_f1']:.3f} | {pe} |")
    f = r["offtopic"]
    L += ["", "Plans that failed at the provider (rate limit or overload) count as wrong (intent \"failed\"); "
          "Gemini 3.1 Flash-Lite alone had 13 such failures in the development run, which the hybrid planner absorbs.",
          "", "![intent](../artifacts/dl_eval/intent_confusion.png)", "",
          "## C. Off-topic detection (knowledge retriever)", "",
          f"{f['n_in_domain']} MOF questions vs {f['n_off_topic']} off-topic questions ({f['note']}): "
          f"ROC-AUC {f['roc_auc']:.3f}, accuracy {f['accuracy']:.3f} at cosine threshold {f['threshold']}.", "",
          "![offtopic](../artifacts/dl_eval/offtopic_roc.png)", "",
          "## D. Physics rule as a classifier", "",
          f"Accessible vs zero surface area from PLD ≥ {r['physics']['threshold_A']:.4f} Å: test accuracy "
          f"{r['physics']['accuracy']:.4f} on {r['physics']['n_test']} MOFs.", "",
          "## E. Regression: train / validation / test", "",
          "| Target | XGBoost R² train / val / test | FT-Transformer R² train / val / test (accessible) | FT epochs (best) |",
          "|---|---|---|---|"]
    for t, m in r["regression"].items():
        x = m["xgb_production_split_metrics"]
        L.append(f"| {t} | {x['train']['R2']:.3f} / {x['val']['R2']:.3f} / {x['test']['R2']:.3f} | "
                 f"{m['ft_final']['train_r2']:.3f} / {m['ft_final']['val_r2']:.3f} / {m['ft_final']['test_r2_accessible']:.3f} | "
                 f"{m['ft_epochs']} ({m['ft_best_epoch']}) |")
    L += ["", "![reg](../artifacts/dl_eval/regression_learning_curves.png)", "",
          "## F. Feature extraction", "",
          f"PCA: the first two components explain {sum(r['features']['pca_explained'][:2]):.0%} of the variance. "
          "Strongest correlations: " + "; ".join(f"{a}-{b} {c:+.2f}" for a, b, c in r["features"]["strongest_correlations"]) + ".", ""]
    for name in ("feat_distributions", "feat_correlation", "feat_pca", "feat_tsne_embeddings",
                 "feat_reconstruction_importance", "feat_metals", "physics_rule"):
        L.append(f"![{name}](../artifacts/dl_eval/{name}.png)")
    (ROOT / "docs" / "DL_RESULTS.md").write_text("\n".join(L) + "\n")


def main():
    OUT.mkdir(parents=True, exist_ok=True)
    df = load_materials()
    r = {}
    for key, fn in (("oms", lambda: oms_classification(df)), ("intent", intent_classification),
                    ("offtopic", offtopic_detection), ("physics", lambda: physics_rule(df)),
                    ("regression", lambda: regression_curves(df)), ("features", lambda: feature_graphs(df))):
        t = time.time()
        r[key] = fn()
        print(f"{key:<10} done in {time.time() - t:6.1f} s")
    (OUT / "metrics.json").write_text(json.dumps(r, indent=2, default=float))
    write_report(r)
    for n, m in r["oms"]["models"].items():
        print(f"  OMS {n:<20} acc={m['accuracy']:.3f} f1={m['f1']:.3f} auc={m['roc_auc']:.3f}")


if __name__ == "__main__":
    main()
