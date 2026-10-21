import json

import pandas as pd
import streamlit as st

from mofchat import theme
from mofchat.config import PROPERTY_MODEL_DIR
from mofchat.db import resolve_mof_id
from mofchat.features import PROPERTY_TARGETS
from mofchat.properties import available_targets, predict
from mofchat.ui import label, materials, render_prediction

theme.page_header("Predict & explain", "Surrogate models · XGBoost + SHAP",
                  "Surrogate models predict a property from cheaper geometric descriptors. XGBoost gives the main "
                  "prediction with a calibrated 90% interval; SHAP explains it feature by feature; the "
                  "FT-Transformer gives a deep-learning second opinion.")

targets = available_targets()
if not targets:
    st.warning("No trained property models yet. Run `python train_property_models.py`.", icon=":material/warning:")
    st.stop()

df = materials()
target = st.segmented_control("Property to predict", list(targets), default=targets[0], format_func=label) or targets[0]
feats = PROPERTY_TARGETS[target]["features"]
source = st.segmented_control("Input", ["Enter descriptors", "Use a MOF from the database"],
                              default="Enter descriptors") or "Enter descriptors"

actual = None
with st.form("predict_form", border=True):
    if source == "Use a MOF from the database":
        mof = st.text_input("MOF ID (CSD refcode or common name, e.g. FIQCEN, HKUST-1, ZIF-8)", "FIQCEN")
        submitted = st.form_submit_button("Predict", icon=":material/play_arrow:", type="primary")
        ids = resolve_mof_id(mof) if mof else []
        inputs = {}
        if ids:
            row = df[df.MOF_ID == ids[0]].iloc[0]
            inputs = {f: float(row[f]) for f in feats}
            actual = float(row[target])
            st.caption(f"Using **{ids[0]}**" + (f" (first of {len(ids)} matches)" if len(ids) > 1 else ""))
        elif mof:
            st.error(f"'{mof}' is not in the CoRE-MOF table.")
    else:
        cols = st.columns(3)
        defaults = {"Density": 0.6, "LCD": 12.0, "PLD": 8.0, "LFPD": 11.0, "Void_Fraction": 0.75}
        inputs = {}
        for i, f in enumerate([f for f in feats if f != "Pore_Volume"]):
            lo, hi = float(df[f].min()), float(df[f].quantile(0.999))
            inputs[f] = cols[i % 3].number_input(label(f), min_value=0.0, max_value=float(df[f].max()),
                                                 value=float(defaults.get(f, df[f].median())),
                                                 step=0.01 if hi < 5 else 0.1, format="%.3f")
        if "Pore_Volume" in feats:
            st.caption("Pore volume is computed as void fraction / density (exact identity in this dataset).")
        submitted = st.form_submit_button("Predict", icon=":material/play_arrow:", type="primary")

if inputs:
    render_prediction(predict(target, inputs, actual=actual))

metrics_path = PROPERTY_MODEL_DIR / "metrics.json"
if metrics_path.exists():
    with st.expander("Model accuracy on the held-out test set", icon=":material/fact_check:"):
        m = json.loads(metrics_path.read_text())[target]
        rows = [{"model": k, "MAE": v["test_all"]["MAE"], "RMSE": v["test_all"]["RMSE"], "R²": v["test_all"]["R2"]}
                for k, v in m["models"].items()]
        st.dataframe(pd.DataFrame(rows), hide_index=True,
                     column_config={"MAE": st.column_config.NumberColumn(format="%.3f"),
                                    "RMSE": st.column_config.NumberColumn(format="%.3f"),
                                    "R²": st.column_config.NumberColumn(format="%.4f")})
        st.caption(f"Split-conformal 90% interval: half-width {m['conformal']['half_width']:.3g} "
                   f"{m['unit']}, test coverage {m['conformal']['test_coverage']:.1%}.")

theme.colophon()
