"""
train_property_models.py - surrogate models that predict MOF properties.

  python train_property_models.py

Targets (see mofchat/features.py::PROPERTY_TARGETS)
  Surface_Area  (m2/g) from density + pore diameters + void fraction + pore volume
  Void_Fraction (-)    from density + pore diameters

Physics-informed hurdle for Surface_Area: the descriptors were computed with
a 3.31 A probe, so a MOF whose pore limiting diameter is below the probe
diameter has zero accessible surface area. The rule is applied first and the
regressors are trained only on accessible MOFs.

Models compared on the same held-out test split (70/10/10/10 train/val/calib/test):
  mean baseline | Ridge | Gaussian Process (RBF-ARD + noise, 2,000-sample subset)
  XGBoost (main model: SHAP explanations + split-conformal 90 % interval)
  FT-Transformer regressor (deep learning, same backbone as the embedding model)

Outputs: artifacts/property_models/<target>/{xgb.json, ft.pt, ft_preprocessor.json, meta.json},
         artifacts/property_models/metrics.json and figures (parity, SHAP).
"""

import json
import math
import time

import mofchat  # noqa: F401  (sets the safe torch/faiss import order)

import matplotlib
import numpy as np
import shap
import torch
import xgboost as xgb
from sklearn.gaussian_process import GaussianProcessRegressor
from sklearn.gaussian_process.kernels import RBF, ConstantKernel, WhiteKernel
from sklearn.linear_model import Ridge
from sklearn.metrics import mean_absolute_error, mean_squared_error, r2_score

matplotlib.use("Agg")
import matplotlib.pyplot as plt

from mofchat.config import PROPERTY_MODEL_DIR, RANDOM_SEED, unit_of
from mofchat.db import load_materials
from mofchat.features import PROPERTY_TARGETS, Preprocessor
from mofchat.ft_transformer import FTRegressor, FTTransformer

GPR_N = 2000
FT_CFG = dict(d_token=64, n_layers=3, n_heads=4, ffn_mult=2.0, dropout=0.1)


def metrics(y, p):
    return {"MAE": float(mean_absolute_error(y, p)), "RMSE": float(math.sqrt(mean_squared_error(y, p))),
            "R2": float(r2_score(y, p)), "n": int(len(y))}


def split(n, seed=RANDOM_SEED):
    perm = np.random.default_rng(seed).permutation(n)
    a, b, c = int(0.7 * n), int(0.8 * n), int(0.9 * n)
    return perm[:a], perm[a:b], perm[b:c], perm[c:]


def hurdle_threshold(df):
    """Largest PLD with zero ASA and smallest PLD with positive ASA -> rule threshold."""
    zero_max = df.loc[df.Surface_Area == 0, "PLD"].max()
    pos_min = df.loc[df.Surface_Area > 0, "PLD"].min()
    thr = float((zero_max + pos_min) / 2) if zero_max < pos_min else float(pos_min)
    rule_acc = float(((df.PLD >= thr) == (df.Surface_Area > 0)).mean())
    return thr, float(zero_max), float(pos_min), rule_acc


def train_ft_regressor(Xtr, ytr, Xva, yva, seed=RANDOM_SEED, epochs=400, patience=25, batch=256):
    torch.manual_seed(seed)
    model = FTRegressor(FTTransformer(Xtr.shape[1], (), **FT_CFG))
    opt = torch.optim.AdamW(model.parameters(), lr=1e-3, weight_decay=1e-5)
    sched = torch.optim.lr_scheduler.ReduceLROnPlateau(opt, factor=0.5, patience=8)
    Xtr, ytr, Xva, yva = map(lambda a: torch.tensor(a, dtype=torch.float32), (Xtr, ytr, Xva, yva))
    g = torch.Generator().manual_seed(seed)
    best, state, wait, hist = float("inf"), None, 0, []
    for ep in range(epochs):
        model.train()
        order = torch.randperm(len(Xtr), generator=g)
        for s in range(0, len(order), batch):
            b = order[s:s + batch]
            loss = torch.nn.functional.mse_loss(model(Xtr[b]), ytr[b])
            opt.zero_grad()
            loss.backward()
            opt.step()
        model.eval()
        with torch.no_grad():
            v = torch.nn.functional.mse_loss(model(Xva), yva).item()
        hist.append(v)
        sched.step(v)
        if v < best - 1e-6:
            best, wait, state = v, 0, {k: t.clone() for k, t in model.state_dict().items()}
        else:
            wait += 1
            if wait >= patience:
                break
    model.load_state_dict(state)
    model.eval()
    return model, hist


def run_target(df, target, spec, out_root):
    out = out_root / target
    out.mkdir(parents=True, exist_ok=True)
    feats = spec["features"]
    tr, va, ca, te = split(len(df))
    res = {"features": feats, "unit": unit_of(target), "split": {"train": len(tr), "val": len(va),
                                                                 "calibration": len(ca), "test": len(te)}}
    y = df[target].to_numpy(float)
    X = df[feats]

    if spec["hurdle"]:
        thr, zmax, pmin, acc = hurdle_threshold(df.iloc[tr])
        res["hurdle"] = {"rule": f"{target} = 0 if PLD < {thr:.4f} A", "threshold": thr,
                         "max_PLD_with_zero": zmax, "min_PLD_with_positive": pmin,
                         "rule_accuracy_train": acc,
                         "rule_accuracy_test": float(((df.PLD.iloc[te] >= thr) == (df[target].iloc[te] > 0)).mean())}
        acc_mask = (df.PLD >= thr).to_numpy()
    else:
        thr, acc_mask = None, np.ones(len(df), bool)

    def sub(idx):
        return idx[acc_mask[idx]]

    trA, vaA, caA, teA = sub(tr), sub(va), sub(ca), sub(te)

    def full_pred(pred_acc_fn):
        p = np.zeros(len(te))
        m = acc_mask[te]
        p[m] = pred_acc_fn(te[m])
        return p

    preds, model_metrics, times = {}, {}, {}

    # mean baseline
    mu = y[trA].mean()
    preds["Mean baseline"] = full_pred(lambda idx: np.full(len(idx), mu))

    # ridge on preprocessed features
    pre = Preprocessor(feats, [], Preprocessor.default_log_cols(feats)).fit(df.iloc[trA])
    Z = pre.transform_num(df)
    t = time.time()
    ridge = Ridge(alpha=1.0).fit(Z[trA], y[trA])
    times["Ridge"] = time.time() - t
    preds["Ridge"] = full_pred(lambda idx: ridge.predict(Z[idx]))

    # gaussian process (subset)
    rng = np.random.default_rng(RANDOM_SEED)
    gidx = rng.choice(trA, size=min(GPR_N, len(trA)), replace=False)
    kernel = ConstantKernel(1.0) * RBF(length_scale=np.ones(len(feats)), length_scale_bounds=(1e-2, 1e3)) \
        + WhiteKernel(1e-2, (1e-6, 1e1))
    t = time.time()
    gpr = GaussianProcessRegressor(kernel=kernel, normalize_y=True, random_state=RANDOM_SEED).fit(Z[gidx], y[gidx])
    times["Gaussian Process"] = time.time() - t
    gm, gs = gpr.predict(Z[teA], return_std=True)
    gp_full = np.zeros(len(te))
    gp_full[acc_mask[te]] = gm
    preds["Gaussian Process"] = gp_full
    gp_cov = float(np.mean(np.abs(y[teA] - gm) <= 1.96 * gs))
    res["gpr"] = {"n_train": int(len(gidx)), "kernel": str(gpr.kernel_), "coverage_95": gp_cov,
                  "mean_std": float(gs.mean())}

    # xgboost (main)
    t = time.time()
    model = xgb.XGBRegressor(n_estimators=4000, learning_rate=0.03, max_depth=6, subsample=0.8,
                             colsample_bytree=0.9, min_child_weight=2, reg_lambda=1.0,
                             early_stopping_rounds=150, eval_metric="rmse", random_state=RANDOM_SEED, n_jobs=4)
    model.fit(X.iloc[trA], y[trA], eval_set=[(X.iloc[vaA], y[vaA])], verbose=False)
    times["XGBoost"] = time.time() - t
    preds["XGBoost"] = full_pred(lambda idx: model.predict(X.iloc[idx]))
    # split-conformal 90 % interval from the calibration split
    cal_res = np.sort(np.abs(y[caA] - model.predict(X.iloc[caA])))
    n = len(cal_res)
    q90 = float(cal_res[min(n - 1, math.ceil((n + 1) * 0.9) - 1)])
    te_res = np.abs(y[teA] - model.predict(X.iloc[teA]))
    res["conformal"] = {"level": 0.9, "half_width": q90, "test_coverage": float(np.mean(te_res <= q90))}
    model.save_model(out / "xgb.json")

    # xgboost without hurdle (ablation)
    if spec["hurdle"]:
        plain = xgb.XGBRegressor(n_estimators=4000, learning_rate=0.03, max_depth=6, subsample=0.8,
                                 colsample_bytree=0.9, min_child_weight=2, early_stopping_rounds=150,
                                 eval_metric="rmse", random_state=RANDOM_SEED, n_jobs=4)
        plain.fit(X.iloc[tr], y[tr], eval_set=[(X.iloc[va], y[va])], verbose=False)
        preds["XGBoost (no physics rule)"] = np.clip(plain.predict(X.iloc[te]), 0, None)

    # ft-transformer regressor
    ymu, ysd = y[trA].mean(), y[trA].std()
    t = time.time()
    ft, ft_hist = train_ft_regressor(Z[trA], (y[trA] - ymu) / ysd, Z[vaA], (y[vaA] - ymu) / ysd)
    times["FT-Transformer"] = time.time() - t
    with torch.no_grad():
        ft_fn = lambda idx: ft(torch.tensor(Z[idx])).numpy() * ysd + ymu  # noqa: E731
        preds["FT-Transformer"] = full_pred(ft_fn)
        att = ft.cls_attention(torch.tensor(Z[teA])).numpy().mean(axis=0)
    torch.save({"state_dict": ft.state_dict(), "backbone_config": ft.backbone.config,
                "y_mean": float(ymu), "y_std": float(ysd)}, out / "ft.pt")
    pre.save(out / "ft_preprocessor.json")
    res["ft_attention_cls_to_feature"] = dict(zip(feats, map(float, att)))
    res["ft_epochs"] = len(ft_hist)

    # metrics
    for name, p in preds.items():
        model_metrics[name] = {"test_all": metrics(y[te], p),
                               "test_accessible": metrics(y[te][acc_mask[te]], p[acc_mask[te]])}
    res["models"] = model_metrics
    res["train_seconds"] = {k: round(v, 2) for k, v in times.items()}

    # SHAP for the main model
    explainer = shap.TreeExplainer(model)
    Xs = X.iloc[teA[:1000]]
    sv = explainer.shap_values(Xs)
    res["shap_mean_abs"] = dict(zip(feats, map(float, np.abs(sv).mean(axis=0))))
    base = explainer.expected_value
    res["shap_base_value"] = float(base[0] if np.ndim(base) else base)
    plt.figure()
    shap.summary_plot(sv, Xs, show=False, plot_size=(7, 4))
    plt.title(f"SHAP values - XGBoost surrogate for {target}")
    plt.tight_layout()
    plt.savefig(out_root / f"shap_summary_{target}.png", dpi=150)
    plt.close("all")

    # parity plots
    names = [m for m in ["Ridge", "Gaussian Process", "XGBoost", "FT-Transformer"]]
    fig, axes = plt.subplots(1, 4, figsize=(16, 4))
    lim = (0, max(y[te].max(), max(preds[m].max() for m in names)) * 1.05)
    for ax, m in zip(axes, names):
        r2 = model_metrics[m]["test_all"]["R2"]
        ax.scatter(y[te], preds[m], s=4, alpha=0.4)
        ax.plot(lim, lim, "k--", lw=1)
        ax.set(xlim=lim, ylim=lim, title=f"{m}  (R² = {r2:.3f})",
               xlabel=f"actual {target} ({unit_of(target)})", ylabel="predicted")
    plt.tight_layout()
    plt.savefig(out_root / f"parity_{target}.png", dpi=150)
    plt.close("all")

    meta = {k: res[k] for k in ("features", "unit", "conformal", "shap_base_value")} | {
        "target": target, "hurdle_threshold": thr, "y_mean": float(ymu), "y_std": float(ysd)}
    (out / "meta.json").write_text(json.dumps(meta, indent=2))
    return res


def main():
    PROPERTY_MODEL_DIR.mkdir(parents=True, exist_ok=True)
    df = load_materials()
    all_res = {}
    for target, spec in PROPERTY_TARGETS.items():
        print(f"\n=== {target} ===")
        r = run_target(df, target, spec, PROPERTY_MODEL_DIR)
        all_res[target] = r
        for m, v in r["models"].items():
            print(f"  {m:28s} MAE={v['test_all']['MAE']:9.3f}  RMSE={v['test_all']['RMSE']:9.3f}  "
                  f"R2={v['test_all']['R2']:.4f}")
        print("  conformal:", r["conformal"], " gpr cov95:", r["gpr"]["coverage_95"])
        if "hurdle" in r:
            print("  hurdle:", r["hurdle"])
        print("  SHAP mean|.|:", {k: round(v, 3) for k, v in r["shap_mean_abs"].items()})
    (PROPERTY_MODEL_DIR / "metrics.json").write_text(json.dumps(all_res, indent=2))


if __name__ == "__main__":
    main()
