"""
MOFChat - Streamlit entry point.

  streamlit run app.py
"""

import mofchat  # noqa: F401  (safe native-library import order; must come first)

import streamlit as st

from mofchat.config import COLUMN_BY_NAME, DB_PATH, FT_EMBED_DIR, KNOWLEDGE_INDEX_DIR
from mofchat import llm, theme
from mofchat.properties import available_targets

st.set_page_config(page_title="MOFChat", page_icon=":material/deployed_code:", layout="wide")
theme.apply_theme()

if not DB_PATH.exists():
    st.error("Database not found. Run `python setup_db.py` (or `python run_pipeline.py`) first.",
             icon=":material/error:")
    st.stop()

if "messages" not in st.session_state:
    st.session_state.messages = []

with st.sidebar:
    theme.brand()
    st.subheader("Settings")
    models = llm.list_models()
    avail = [m.model_id for m, ok_, _ in models if ok_]
    ok = bool(avail)
    st.session_state.models_ready = (len(avail), len(models))
    st.session_state.use_llm = st.toggle("Use a language model", value=ok, disabled=not ok,
                                         help="Without an LLM, MOFChat uses its deterministic rule-based "
                                              "planner and template answers.")
    default = llm.default_model_id()
    st.session_state.model_id = st.selectbox(
        "Language model", avail or ["(none available)"],
        index=avail.index(default) if default in avail else 0,
        format_func=lambda m: llm.BY_ID[m].label if m in llm.BY_ID else m,
        disabled=not st.session_state.use_llm,
        help="Free cloud models (Gemini, Groq, OpenRouter) or local Ollama models. If the chosen model is "
             "rate-limited or down, MOFChat falls back automatically: " + " → ".join(
                 llm.BY_ID[m].label for m in llm.fallback_chain(None)) + " → rule-based planner.")
    if not avail:
        st.session_state.model_id = None
    msg = llm.BY_ID[st.session_state.model_id].label if st.session_state.model_id in llm.BY_ID else \
        "no model available"
    st.session_state.planner_mode = st.segmented_control(
        "Planner", ["hybrid", "llm", "rules"], default="hybrid", disabled=not st.session_state.use_llm,
        help="hybrid = LLM plan + explicit numbers the rule parser is certain about; "
             "llm = LLM only (with validator); rules = deterministic parser only.") or "hybrid"
    st.session_state.show_details = st.toggle("Show plan, SQL and validation", value=True)
    if st.button("Clear chat", icon=":material/delete_sweep:", width="stretch"):
        st.session_state.messages = []
        st.session_state.pop("suggestion", None)
        st.rerun()

    st.subheader("System status")
    kn = (KNOWLEDGE_INDEX_DIR / "index.faiss").exists()
    ft = (FT_EMBED_DIR / "index.faiss").exists()
    t = available_targets()
    theme.status_list([
        (ok, f"LLM: {msg}", f"{len(avail)} of {len(models)} models ready"),
        (True, "CoRE-MOF database", "12,020 MOFs"),
        (kn, "Knowledge index (RAG)", "ready" if kn else "missing: run setup_vectorstore.py"),
        (ft, "FT-Transformer similarity index", "ready" if ft else "missing: run train_ft.py"),
        (bool(t), "Property models", ", ".join(COLUMN_BY_NAME[c].label for c in t) if t
         else "missing: run train_property_models.py"),
    ])
    with st.expander("All language models", icon=":material/smart_toy:"):
        current = None
        for spec, ok_, why in models:
            if spec.provider != current:
                current = spec.provider
                st.markdown(f"**{llm.PROVIDER_LABEL[current]}**")
            st.markdown(f"{':material/check_circle:' if ok_ else ':material/block:'} {spec.label}  \n"
                        f":gray[{why if not ok_ else (spec.notes or why)}]")

page = st.navigation(
    [
        st.Page("app_pages/chat.py", title="Chat", icon=":material/chat:", default=True),
        st.Page("app_pages/explore.py", title="Explore & optimise", icon=":material/travel_explore:"),
        st.Page("app_pages/predict.py", title="Predict & explain", icon=":material/model_training:"),
        st.Page("app_pages/evaluation.py", title="Evaluation", icon=":material/fact_check:"),
        st.Page("app_pages/about.py", title="About", icon=":material/info:"),
    ],
    position="top",
)
page.run()
