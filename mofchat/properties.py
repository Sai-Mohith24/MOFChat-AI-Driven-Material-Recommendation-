"""Runtime property prediction + explanation (XGBoost/SHAP and FT-Transformer)."""

from __future__ import annotations

import json
from dataclasses import dataclass
from functools import lru_cache

import numpy as np
import pandas as pd

from .config import PROPERTY_MODEL_DIR, unit_of
from .features import PROPERTY_TARGETS, Preprocessor


@dataclass
class Prediction:
    target: str
    unit: str
    value: float
    low: float
    high: float
    ft_value: float | None
    contributions: dict[str, float]      # SHAP value per input feature
    base_value: float
    inputs: dict[str, float]
    imputed: list[str]
    hurdle_applied: bool
    ft_attention: dict[str, float] | None = None
    actual: float | None = None


def available_targets() -> tuple[str, ...]:
    return tuple(t for t in PROPERTY_TARGETS if (PROPERTY_MODEL_DIR / t / "xgb.json").exists())


@lru_cache(maxsize=8)
def _load(target: str):
    import shap
    import torch
    import xgboost as xgb

    from .ft_transformer import FTRegressor, FTTransformer

    d = PROPERTY_MODEL_DIR / target
    meta = json.loads((d / "meta.json").read_text())
    model = xgb.XGBRegressor()
    model.load_model(d / "xgb.json")
    explainer = shap.TreeExplainer(model)
    ft = None
    if (d / "ft.pt").exists():
        ck = torch.load(d / "ft.pt", map_location="cpu", weights_only=False)
        ft = FTRegressor(FTTransformer(**ck["backbone_config"]))
        ft.load_state_dict(ck["state_dict"])
        ft.eval()
        ft = (ft, Preprocessor.load(d / "ft_preprocessor.json"), ck["y_mean"], ck["y_std"])
    return meta, model, explainer, ft


@lru_cache(maxsize=1)
def _medians() -> dict[str, float]:
    from .db import load_materials
    return load_materials().median(numeric_only=True).to_dict()


def predict(target: str, inputs: dict[str, float], actual: float | None = None) -> Prediction:
    import torch

    meta, model, explainer, ft = _load(target)
    feats = meta["features"]
    med = _medians()
    imputed = [f for f in feats if f not in inputs or inputs[f] is None]
    row = {f: float(inputs[f]) if f not in imputed else float(med[f]) for f in feats}
    # keep derived quantities consistent when the user gives VF and density but not pore volume
    if "Pore_Volume" in feats and "Pore_Volume" in imputed and "Void_Fraction" in row and "Density" in row \
            and "Void_Fraction" not in imputed and "Density" not in imputed:
        row["Pore_Volume"] = row["Void_Fraction"] / row["Density"]
        imputed.remove("Pore_Volume")
    X = pd.DataFrame([row], columns=feats)

    thr = meta.get("hurdle_threshold")
    if thr is not None and row.get("PLD", 99) < thr:
        return Prediction(target, unit_of(target), 0.0, 0.0, 0.0, 0.0, {f: 0.0 for f in feats}, 0.0, row,
                          imputed, True, None, actual)

    value = float(model.predict(X)[0])
    hw = meta["conformal"]["half_width"]
    sv = explainer.shap_values(X)[0]
    lo = max(0.0, value - hw)
    if target == "Void_Fraction":
        value, lo = float(np.clip(value, 0, 1)), max(0.0, value - hw)
    hi = value + hw if target != "Void_Fraction" else min(1.0, value + hw)

    ft_value, att = None, None
    if ft is not None:
        net, pre, ym, ys = ft
        z = torch.tensor(pre.transform_num(X))
        with torch.no_grad():
            ft_value = float(net(z).item() * ys + ym)
        att = dict(zip(feats, map(float, net.cls_attention(z)[0].numpy())))
    return Prediction(target, unit_of(target), value, lo, hi, ft_value, dict(zip(feats, map(float, sv))),
                      float(meta["shap_base_value"]), row, imputed, False, att, actual)


def explain_rows(target: str, rows: pd.DataFrame) -> pd.DataFrame:
    """SHAP contributions for several MOFs (rows from the database)."""
    meta, model, explainer, _ = _load(target)
    X = rows[meta["features"]].astype(float)
    sv = explainer.shap_values(X)
    out = pd.DataFrame(sv, columns=meta["features"])
    out.insert(0, "MOF_ID", rows["MOF_ID"].to_numpy())
    return out
