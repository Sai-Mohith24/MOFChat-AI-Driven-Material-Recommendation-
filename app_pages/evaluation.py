import json

import pandas as pd
import streamlit as st

from mofchat.config import EVAL_DIR, FT_EMBED_DIR, PROPERTY_MODEL_DIR
from mofchat.ui import eval_summary

st.title("Evaluation", anchor=False)
st.caption("All numbers on this page are produced by `python evaluate.py`, `train_ft.py` and "
           "`train_property_models.py` and read from the artifacts folder.")

summary = eval_summary()
if summary is None:
    st.info("No benchmark results yet. Run `python evaluate.py`.", icon=":material/info:")
else:
    b = summary["benchmark"]
    st.subheader(f"Retrieval benchmark ({b['n_queries']} labelled questions)", anchor=False)
    st.markdown("Each question has a hand-written gold plan whose answer is computed directly from the database. "
                "**Answer accuracy** = the system returned exactly the gold MOFs (or the gold count/average, or "
                "correctly declined a non-database question). **Constraint precision@k** = share of returned MOFs "
                "that satisfy all gold filters. **Plan accuracy** = the structured plan equals the gold plan.")
    rows = []
    for name, s in b["systems"].items():
        rows.append({"system": name, "answer accuracy": s["result_accuracy"],
                     "constraint precision@k": s.get("constraint_precision_at_k"),
                     "plan accuracy": s.get("plan_accuracy"), "mean latency (s)": s.get("mean_latency_s")})
    st.dataframe(pd.DataFrame(rows), hide_index=True,
                 column_config={"answer accuracy": st.column_config.ProgressColumn(format="%.1f%%", min_value=0, max_value=100),
                                "constraint precision@k": st.column_config.NumberColumn(format="%.1f%%"),
                                "plan accuracy": st.column_config.NumberColumn(format="%.1f%%"),
                                "mean latency (s)": st.column_config.NumberColumn(format="%.2f")})
    if (EVAL_DIR / "benchmark_by_category.png").exists():
        st.image(str(EVAL_DIR / "benchmark_by_category.png"))
    h = summary.get("heldout")
    if h:
        st.markdown(f"**Held-out set** - {h['n_queries']} new phrasings written after the rule parser was tuned, "
                    "never used for tuning (measures generalisation):")
        st.dataframe(pd.DataFrame([{"system": k, "answer accuracy": v["result_accuracy"],
                                    "plan accuracy": v.get("plan_accuracy")} for k, v in h["systems"].items()]),
                     hide_index=True,
                     column_config={"answer accuracy": st.column_config.ProgressColumn(format="%.1f%%", min_value=0,
                                                                                      max_value=100),
                                    "plan accuracy": st.column_config.NumberColumn(format="%.1f%%")})
    with st.expander("Per-question results", icon=":material/table:"):
        p = EVAL_DIR / "benchmark_results.csv"
        if p.exists():
            st.dataframe(pd.read_csv(p), hide_index=True)
    mc = summary.get("model_comparison") or {}
    if mc:
        dm = summary.get("default_model")
        st.subheader("Which free LLM plans best? (model comparison)", anchor=False)
        st.markdown("Every model is tested on its own with automatic fallback switched off. *LLM alone* is the "
                    "single-shot planner; *hybrid* adds the validator and the rule parser's explicit facts. "
                    f"The tables above use **{mc.get(dm, {}).get('label', dm)}**, the best model on the held-out set.")
        st.dataframe(pd.DataFrame([{
            "model": v["label"] + (" (default)" if k == dm else ""), "provider": v["provider"],
            "held-out: LLM alone": v.get("held-out_single_shot"), "held-out: hybrid": v.get("held-out_hybrid"),
            "development: LLM alone": v.get("development_single_shot"),
            "development: hybrid": v.get("development_hybrid"),
            "median planning time (s)": v.get("held-out_planner_latency_s"),
            "provider errors": sum(x for x in (v.get("development_provider_errors"),
                                               v.get("held-out_provider_errors")) if x)} for k, v in mc.items()]),
            hide_index=True,
            column_config={c: st.column_config.NumberColumn(format="%.1f%%") for c in (
                "held-out: LLM alone", "held-out: hybrid", "development: LLM alone", "development: hybrid")})
        if (EVAL_DIR / "model_comparison.png").exists():
            st.image(str(EVAL_DIR / "model_comparison.png"))
        ans = [(v["label"], v["answers"]) for v in mc.values() if v.get("answers")]
        if ans:
            st.markdown("**Answer writing**, 16 questions per model, checked by the answer validator:")
            st.dataframe(pd.DataFrame([{"model": label, "LLM call failed": a.get("answer_llm_failures"),
                                        "first drafts with a problem": a["first_drafts_with_unverifiable_content"],
                                        "of which false comparison claims": a.get("first_drafts_with_false_claims"),
                                        "regenerated": a["answers_regenerated"],
                                        "still flagged": a["final_answers_with_flagged_content"],
                                        "seconds per answer": a["mean_seconds_per_answer"]} for label, a in ans]),
                         hide_index=True)
    if summary.get("answer_validation"):
        st.subheader("Answer validation (hallucination check)", anchor=False)
        st.json(summary["answer_validation"], expanded=False)
    if summary.get("knowledge_retrieval"):
        st.subheader("Knowledge retrieval", anchor=False)
        st.json(summary["knowledge_retrieval"], expanded=False)

st.subheader("Property prediction (held-out test set)", anchor=False)
mp = PROPERTY_MODEL_DIR / "metrics.json"
if mp.exists():
    m = json.loads(mp.read_text())
    for target, r in m.items():
        st.markdown(f"**{target}** ({r['unit'] or 'dimensionless'}) - features: {', '.join(r['features'])}")
        df = pd.DataFrame([{"model": k, **{f"{kk}": vv for kk, vv in v["test_all"].items() if kk != "n"}}
                           for k, v in r["models"].items()])
        st.dataframe(df, hide_index=True, column_config={c: st.column_config.NumberColumn(format="%.4f")
                                                         for c in ("MAE", "RMSE", "R2")})
        cap = f"Conformal 90% interval coverage on test: {r['conformal']['test_coverage']:.1%}. " \
              f"GPR 95% interval coverage: {r['gpr']['coverage_95']:.1%}."
        if "hurdle" in r:
            cap += f" Physics rule ({r['hurdle']['rule']}) accuracy on test: {r['hurdle']['rule_accuracy_test']:.2%}."
        st.caption(cap)
        c1, c2 = st.columns(2)
        if (PROPERTY_MODEL_DIR / f"parity_{target}.png").exists():
            c1.image(str(PROPERTY_MODEL_DIR / f"parity_{target}.png"))
        if (PROPERTY_MODEL_DIR / f"shap_summary_{target}.png").exists():
            c2.image(str(PROPERTY_MODEL_DIR / f"shap_summary_{target}.png"))
else:
    st.info("Run `python train_property_models.py`.", icon=":material/info:")

st.subheader("FT-Transformer embeddings (similarity search)", anchor=False)
ep = FT_EMBED_DIR / "metrics.json"
if ep.exists():
    e = json.loads(ep.read_text())
    sim = e["similarity"]
    df = pd.DataFrame([{"neighbours from": k.replace("_", " "), **v} for k, v in sim.items()
                       if isinstance(v, dict)])
    st.dataframe(df, hide_index=True)
    st.caption(f"{sim['n_queries']} random query MOFs, {sim['k']} neighbours each. Lower descriptor difference "
               f"(in standard deviations) is better. Overlap between FT-Transformer and plain descriptor k-NN "
               f"neighbour lists: {sim['overlap_ft_vs_raw_knn']:.0%}.")
    if (FT_EMBED_DIR / "training_curve.png").exists():
        st.image(str(FT_EMBED_DIR / "training_curve.png"), width=520)
