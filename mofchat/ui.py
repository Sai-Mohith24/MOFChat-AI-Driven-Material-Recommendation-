"""Shared Streamlit helpers (cached resources + rendering of agent responses)."""

from __future__ import annotations

import json

import altair as alt
import pandas as pd
import streamlit as st

from .agent import AgentResponse, MOFChatAgent
from .config import COLUMN_BY_NAME, EVAL_DIR, unit_of
from .db import load_materials
from .optimizer import pareto_front_mask


@st.cache_resource(show_spinner="Loading MOFChat (models, indexes)…", max_entries=4)
def get_agent(use_llm: bool, planner_mode: str) -> MOFChatAgent:
    return MOFChatAgent(use_llm=use_llm, planner_mode=planner_mode)


@st.cache_data(show_spinner=False)
def materials() -> pd.DataFrame:
    return load_materials().copy()


@st.cache_data(show_spinner=False, ttl=60)
def eval_summary() -> dict | None:
    p = EVAL_DIR / "summary.json"
    return json.loads(p.read_text()) if p.exists() else None


def label(col: str) -> str:
    c = COLUMN_BY_NAME.get(col)
    if not c:
        return col
    return f"{c.label} ({c.unit})" if c.unit else c.label


def column_config(df: pd.DataFrame) -> dict:
    cfg = {}
    for col in df.columns:
        if col == "why":
            cfg[col] = st.column_config.TextColumn("Why it fits", width="large")
        elif col == "similarity":
            cfg[col] = st.column_config.ProgressColumn("Similarity", min_value=0.0, max_value=1.0, format="%.4f")
        elif col == "pareto_front":
            cfg[col] = st.column_config.NumberColumn("Pareto front", format="%d")
        elif col == "Has_OMS":
            cfg[col] = st.column_config.CheckboxColumn("Open metal site")
        elif col in COLUMN_BY_NAME and COLUMN_BY_NAME[col].kind == "numeric":
            fmt = "%.0f" if col in ("Surface_Area", "ASA_vol", "NASA_grav", "NASA_vol") else "%.3f"
            cfg[col] = st.column_config.NumberColumn(label(col), format=fmt)
        elif col in COLUMN_BY_NAME:
            cfg[col] = st.column_config.TextColumn(COLUMN_BY_NAME[col].label)
        elif col == "violated":
            cfg[col] = st.column_config.TextColumn("Constraint(s) missed", width="medium")
        elif col == "constraint_violation":
            cfg[col] = st.column_config.NumberColumn("Total violation (σ)", format="%.2f")
    return cfg


def pareto_chart(cand: pd.DataFrame, picked: pd.DataFrame, objectives) -> alt.Chart:
    (x, dx), (y, dy) = [(o.column, o.direction) for o in objectives[:2]]
    data = cand[["MOF_ID", x, y]].copy()
    data["set"] = "candidate"
    data.loc[pareto_front_mask(data, [(x, dx), (y, dy)]), "set"] = "Pareto front"
    data.loc[data.MOF_ID.isin(set(picked.MOF_ID)), "set"] = "recommended"
    if len(data) > 5000:  # keep the chart light; never drop front / recommended points
        keep = data[data.set != "candidate"]
        data = pd.concat([data[data.set == "candidate"].sample(5000, random_state=0), keep])
    scale = alt.Scale(domain=["candidate", "Pareto front", "recommended"], range=["#c7c7c7", "#4c78a8", "#e45756"])
    return (alt.Chart(data).mark_circle().encode(
        x=alt.X(f"{x}:Q", title=label(x)), y=alt.Y(f"{y}:Q", title=label(y)),
        color=alt.Color("set:N", scale=scale, title=None),
        size=alt.condition(alt.datum.set == "recommended", alt.value(120), alt.value(18)),
        order=alt.Order("set:N", sort="ascending"),
        tooltip=["MOF_ID", alt.Tooltip(f"{x}:Q", format=".3f"), alt.Tooltip(f"{y}:Q", format=".3f")])
        .properties(height=340))


def shap_chart(shap_df: pd.DataFrame) -> alt.Chart:
    long = shap_df.melt(id_vars="MOF_ID", var_name="feature", value_name="shap")
    long["feature"] = long["feature"].map(lambda c: COLUMN_BY_NAME[c].label if c in COLUMN_BY_NAME else c)
    return (alt.Chart(long).mark_bar().encode(
        x=alt.X("shap:Q", title=f"SHAP contribution to predicted surface area ({unit_of('Surface_Area')})"),
        y=alt.Y("feature:N", title=None, axis=alt.Axis(labelLimit=320)),
        color=alt.condition(alt.datum.shap > 0, alt.value("#4c78a8"), alt.value("#e45756")),
        row=alt.Row("MOF_ID:N", title=None, header=alt.Header(labelAngle=0, labelAlign="left")),
        tooltip=["MOF_ID", "feature", alt.Tooltip("shap:Q", format=".1f")])
        .properties(height=110, width=420))


def render_response(r: AgentResponse, show_details: bool = True) -> None:
    st.markdown(r.answer)
    res = r.result
    if r.table is not None and not r.table.empty:
        st.dataframe(r.table, hide_index=True, column_config=column_config(r.table))
    if res is not None and res.candidates is not None and len(r.plan.objectives) >= 2:
        with st.expander("Pareto front (NSGA-II)", icon=":material/scatter_plot:"):
            st.altair_chart(pareto_chart(res.candidates, res.rows, r.plan.objectives))
            st.caption("Grey: all MOFs that pass the filters. Blue: first Pareto front (no other MOF is better in "
                       "both objectives). Red: recommended set chosen by NSGA-II crowding distance.")
    if r.shap is not None and not r.shap.empty and (r.shap.drop(columns="MOF_ID").abs().to_numpy().sum() > 0):
        with st.expander("Explain: what drives these MOFs' surface area (SHAP)", icon=":material/insights:"):
            st.altair_chart(shap_chart(r.shap))
            st.caption("SHAP values of the XGBoost surrogate model: how much each descriptor pushes the predicted "
                       "surface area above (blue) or below (red) the dataset average. MOFs whose pore limiting "
                       "diameter is below the 3.31 Å probe have zero accessible area and no bars.")
    if r.snippets:
        with st.expander(f"Sources ({len(r.snippets)})", icon=":material/menu_book:"):
            for i, s in enumerate(r.snippets, 1):
                st.markdown(f"**[{i}] {s.citation()}** · relevance {s.score:.2f}")
                st.caption(s.text[:600] + ("…" if len(s.text) > 600 else ""))
    if show_details:
        with st.expander("How this answer was produced", icon=":material/account_tree:"):
            st.markdown(f"**Plan** ({r.plan.source}): `{r.plan.summary()}`")
            notes = r.plan.notes + (res.notes if res else [])
            for n in notes:
                st.markdown(f"- {n}")
            if res is not None and res.sql:
                st.markdown("**SQL** (parameterised, read-only):")
                st.code(res.sql, language="sql")
            if res is not None and res.method:
                st.markdown(f"**Ranking:** {res.method}")
            if r.validation:
                v = r.validation
                status = "passed" if v.get("ok") else "issues found"
                st.markdown(f"**Answer validator:** {status} (attempts: {v.get('attempts', 1)})")
                st.json({k: v[k] for k in ("invalid_ids", "corrected_ids", "unretrieved_ids", "unverified_numbers")},
                        expanded=False)
            st.markdown("**Trace**")
            st.code("\n".join(r.trace) or "-", language="text")
            st.caption(" · ".join(f"{k} {v:.2f}s" for k, v in r.timings.items()))
