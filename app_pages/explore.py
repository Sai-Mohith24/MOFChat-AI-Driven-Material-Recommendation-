import altair as alt
import pandas as pd
import streamlit as st

from mofchat import theme
from mofchat.config import NUMERIC_COLUMNS
from mofchat.optimizer import nsga2_rank, pareto_front_mask
from mofchat.ui import column_config, label, materials

theme.page_header("Explore & optimise", "Database explorer · NSGA-II",
                  "Filter the database directly, then rank the remaining MOFs on two objectives with NSGA-II.")

df = materials()
metal_options = sorted({m for s in df.Metal_Type for m in s.split(",") if m})

with st.container(border=True, key="filters"):
    cols = st.columns(3)
    ranges = {}
    for i, col in enumerate(["Surface_Area", "Density", "Void_Fraction", "PLD", "LCD", "Pore_Volume"]):
        lo, hi = float(df[col].min()), float(df[col].max())
        if col in ("LCD", "PLD"):
            hi = min(hi, 40.0)
        if col == "Pore_Volume":
            hi = min(hi, 5.0)
        ranges[col] = cols[i % 3].slider(label(col), lo, hi, (lo, hi), key=f"rng_{col}")
    c1, c2 = st.columns([2, 1])
    metals = c1.multiselect("Metal(s)", metal_options, placeholder="Any metal")
    oms = c2.segmented_control("Open metal site", ["Any", "Yes", "No"], default="Any")

mask = pd.Series(True, index=df.index)
for col, (lo, hi) in ranges.items():
    full_lo, full_hi = float(df[col].min()), float(df[col].max())
    if lo > full_lo:
        mask &= df[col] >= lo
    if hi < (min(full_hi, 40.0) if col in ("LCD", "PLD") else min(full_hi, 5.0) if col == "Pore_Volume" else full_hi):
        mask &= df[col] <= hi
if metals:
    mask &= df.Metal_Type.map(lambda s: bool(set(s.split(",")) & set(metals)))
if oms and oms != "Any":
    mask &= df.Has_OMS == (1 if oms == "Yes" else 0)
sub = df[mask]

st.metric("MOFs matching the filters", f"{len(sub):,}", border=True, width="content")

st.subheader("Multi-objective ranking (NSGA-II)", anchor=False)
c1, c2, c3, c4, c5 = st.columns([3, 1.7, 3, 1.7, 1.2])
x = c1.selectbox("Objective 1", NUMERIC_COLUMNS, index=NUMERIC_COLUMNS.index("Surface_Area"), format_func=label)
dx = c2.segmented_control("Direction 1", ["max", "min"], default="max", key="d1") or "max"
y = c3.selectbox("Objective 2", NUMERIC_COLUMNS, index=NUMERIC_COLUMNS.index("Density"), format_func=label)
dy = c4.segmented_control("Direction 2", ["max", "min"], default="min", key="d2") or "min"
k = c5.number_input("Top k", 1, 50, 10)

if sub.empty:
    st.info("No MOF matches these filters.", icon=":material/info:")
elif x == y:
    st.warning("Choose two different objectives.", icon=":material/warning:")
else:
    top = nsga2_rank(sub, [(x, dx), (y, dy)], int(k))
    plot = sub[["MOF_ID", x, y]].copy()
    plot["set"] = "candidate"
    plot.loc[pareto_front_mask(plot, [(x, dx), (y, dy)]), "set"] = "Pareto front"
    plot.loc[plot.MOF_ID.isin(set(top.MOF_ID)), "set"] = "recommended"
    if len(plot) > 6000:
        plot = pd.concat([plot[plot.set == "candidate"].sample(6000, random_state=0), plot[plot.set != "candidate"]])
    scale = alt.Scale(domain=theme.PARETO_DOMAIN, range=theme.PARETO_RANGE)
    chart = alt.Chart(plot).mark_circle().encode(
        x=alt.X(f"{x}:Q", title=label(x)), y=alt.Y(f"{y}:Q", title=label(y)),
        color=alt.Color("set:N", scale=scale, title=None),
        size=alt.condition(alt.datum.set == "recommended", alt.value(110), alt.value(16)),
        order=alt.Order("set:N"), tooltip=["MOF_ID", f"{x}:Q", f"{y}:Q"]).properties(height=420)
    st.altair_chart(chart)
    show = ["MOF_ID", "pareto_front", x, y] + [c for c in ["Surface_Area", "Density", "Void_Fraction", "PLD", "LCD",
                                                            "Metal_Type", "Has_OMS"] if c not in (x, y)]
    st.dataframe(top[show], hide_index=True, column_config=column_config(top[show]))
    st.caption("Before sorting, candidates in the worst 25% of either objective are screened out; NSGA-II then "
               "fills the list front by front, using crowding distance inside a front to keep diverse trade-offs.")

with st.expander(f"All {len(sub):,} matching MOFs", icon=":material/table:"):
    st.dataframe(sub, hide_index=True, column_config=column_config(sub))

theme.colophon()
