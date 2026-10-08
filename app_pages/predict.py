import json

import altair as alt
import pandas as pd
import streamlit as st

from mofchat.agent import _fmt
from mofchat.config import COLUMN_BY_NAME, PROPERTY_MODEL_DIR
from mofchat.db import resolve_mof_id
from mofchat.features import PROPERTY_TARGETS
from mofchat.properties import available_targets, predict
from mofchat.ui import label, materials

st.title("Predict & explain", anchor=False)
st.caption("Surrogate models predict a property from cheaper geometric descriptors. XGBoost gives the main "
           "prediction with a calibrated 90% interval; SHAP explains it feature by feature; the FT-Transformer "
           "gives a deep-learning second opinion.")

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
        submitted = st.form_submit_button("Predict", icon=":material/play_arrow:")
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
        submitted = st.form_submit_button("Predict", icon=":material/play_arrow:")

if inputs:
    p = predict(target, inputs, actual=actual)
    with st.container(horizontal=True):
        f = lambda v: _fmt(target, v)  # noqa: E731
        st.metric(f"Predicted {COLUMN_BY_NAME[target].label.lower()}", f"{f(p.value)} {p.unit}", border=True)
        st.metric("90% prediction interval", f"{f(p.low)} – {f(p.high)} {p.unit}", border=True)
        if p.ft_value is not None:
            st.metric("FT-Transformer", f"{f(p.ft_value)} {p.unit}", border=True)
        if p.actual is not None:
            st.metric("Database value", f"{f(p.actual)} {p.unit}", f"error {f(p.value - p.actual)}",
                      delta_color="off", border=True)
    if p.hurdle_applied:
        st.info(f"Pore limiting diameter {p.inputs['PLD']:.2f} Å is below the 3.31 Å probe diameter, so the "
                "accessible surface area is exactly 0 (physics rule; holds for every MOF in the dataset).",
                icon=":material/block:")
    else:
        c1, c2 = st.columns(2)
        with c1:
            st.markdown("**Why this value? (SHAP)**")
            shap_df = pd.DataFrame({"feature": [label(k) for k in p.contributions],
                                    "value": [f"{p.inputs[k]:.3g}" for k in p.contributions],
                                    "shap": list(p.contributions.values())})
            st.altair_chart(alt.Chart(shap_df).mark_bar().encode(
                x=alt.X("shap:Q", title=f"Contribution ({p.unit})"),
                y=alt.Y("feature:N", sort=alt.EncodingSortField("shap", op="max", order="descending"), title=None,
                        axis=alt.Axis(labelLimit=320)),
                color=alt.condition(alt.datum.shap > 0, alt.value("#4c78a8"), alt.value("#e45756")),
                tooltip=["feature", "value", alt.Tooltip("shap:Q", format=".2f")]).properties(height=240))
            st.caption(f"Average prediction (base value) {_fmt(target, p.base_value)} {p.unit} + contributions = "
                       f"{_fmt(target, p.value)} {p.unit}.")
        with c2:
            if p.ft_attention:
                st.markdown("**FT-Transformer attention ([CLS] → descriptor, last layer)**")
                att = pd.DataFrame({"feature": [label(k) for k in p.ft_attention],
                                    "attention": list(p.ft_attention.values())})
                st.altair_chart(alt.Chart(att).mark_bar(color="#72b7b2").encode(
                    x=alt.X("attention:Q", title="attention weight"),
                    y=alt.Y("feature:N", sort="-x", title=None, axis=alt.Axis(labelLimit=320))).properties(height=240))
                st.caption("Attention shows where the model looks, not causal importance; SHAP is the "
                           "explanation to rely on.")
    if p.imputed:
        st.caption("Filled with database medians: " + ", ".join(p.imputed))

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
