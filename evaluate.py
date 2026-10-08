"""
evaluate.py - end-to-end evaluation of MOFChat.

  python evaluate.py            # full run (uses Ollama/llama3 if it is running)
  python evaluate.py --no-llm   # only the systems that do not need the LLM

1. Retrieval benchmark (benchmark/queries.json, 64 labelled questions in 10 categories).
   Every question has a hand-written gold plan; the gold answer is obtained by running
   the gold plan through the same deterministic executor, whose correctness is unit-tested
   against pandas (tests/test_core.py). Systems compared:
     * Review-1 two-tower (shipped): MiniLM text vector searched in the FT-autoencoder index
     * Rules planner (no LLM)
     * LLM planner, single shot (no grounding check, no self-correction, no fallback)
     * LLM planner + validator (grounding, self-correction, rule fallback)
     * Hybrid (default): LLM plan + explicit facts from the rule parser + validator
   Metrics: exact answer match, constraint precision@k, plan accuracy, latency.
2. Answer validation: how often Llama 3's first draft contains unverifiable MOF IDs or numbers,
   and what remains after the validator's retry/correction.
3. Knowledge retrieval: hit@1 / hit@3 of the expected source; off-topic rejection.

Writes artifacts/eval/{summary.json, benchmark_results.csv, benchmark_by_category.png}
and docs/RESULTS.md.
"""

import argparse
import functools
import json
import time
from pathlib import Path

import mofchat  # noqa: F401  (safe native import order)

import matplotlib
import numpy as np
import pandas as pd

matplotlib.use("Agg")
import matplotlib.pyplot as plt

from mofchat import db, knowledge, llm, tools, validator
from mofchat.agent import MOFChatAgent
from mofchat.config import (ARTIFACTS_DIR, EVAL_DIR, FT_EMBED_DIR, PROJECT_ROOT, PROPERTY_MODEL_DIR,
                            TEXT_EMBEDDING_MODEL)
from mofchat.plan import QueryPlan

BENCH = PROJECT_ROOT / "benchmark" / "queries.json"
HELDOUT = PROJECT_ROOT / "benchmark" / "heldout.json"   # written after the rule parser was tuned; never tuned on
BASELINE_INDEX = ARTIFACTS_DIR / "baseline_review1" / "faiss_ft_index"
NON_DB = {"knowledge", "out_of_scope"}


# ------------------------------------------------------------------ helpers
def gold_plan(q) -> QueryPlan:
    d = dict(q["gold"], source="rules")
    plan, errs = validator.validate_plan(d, q["question"], expand=True, check_grounding=False)
    assert not errs, (q["id"], errs)
    return plan


def outcome(agent: MOFChatAgent, plan: QueryPlan) -> dict:
    if plan.intent in NON_DB:
        return {"intent": "non_db"}
    res, preds = agent.execute(plan)
    if res is None:
        return {"intent": plan.intent, "ids": [], "relaxed": False, "n": None, "value": None}
    ids = list(res.rows.MOF_ID) if res.rows is not None and not res.rows.empty else []
    if res.kind == "similar":
        ids = ids[1:]          # first row is the reference MOF itself
    return {"intent": plan.intent, "ids": ids, "relaxed": res.relaxed, "n": res.n_matches, "value": res.value,
            "kind": res.kind}


def gold_filter_ids(plan: QueryPlan) -> set[str] | None:
    if plan.intent != "search" or not (plan.constraints or plan.metals or plan.open_metal_site is not None):
        return None
    where, params = tools.compile_where(plan)
    return set(db.query_df(f"SELECT MOF_ID FROM materials{where}", params).MOF_ID)


def exact_match(gold: dict, got: dict) -> bool:
    if gold["intent"] == "non_db":
        return got.get("intent") == "non_db"
    if got.get("intent") == "non_db":
        return False
    if gold["intent"] == "count":
        if got.get("kind") != "count" or got.get("n") != gold["n"]:
            return False
        return gold["value"] is None or (got.get("value") is not None and abs(got["value"] - gold["value"]) < 1e-6)
    return set(got.get("ids", [])) == set(gold["ids"]) and bool(got.get("relaxed")) == bool(gold["relaxed"]) \
        and len(gold["ids"]) > 0


def plan_key(p: QueryPlan | None):
    if p is None:
        return None
    intent = "non_db" if p.intent in NON_DB else p.intent
    if intent == "non_db":
        return ("non_db",)
    agg = (p.aggregate or {}).get("func"), (p.aggregate or {}).get("column")
    return (intent, frozenset((c.column, c.op, round(c.value, 4)) for c in p.constraints),
            frozenset((o.column, o.direction) for o in p.objectives), frozenset(p.metals), p.open_metal_site,
            frozenset(p.mof_ids), agg if intent == "count" else None,
            p.limit if intent in ("search", "similar") else None)


# --------------------------------------------------------- review-1 baseline
class TwoTowerBaseline:
    """The retrieval that shipped at review 1: the question is embedded with MiniLM and
    searched directly in the FT-autoencoder index (the two towers were never aligned)."""

    def __init__(self):
        from langchain_community.vectorstores import FAISS
        from langchain_huggingface import HuggingFaceEmbeddings

        class _Dummy:
            def embed_documents(self, texts): pass
            def embed_query(self, text): pass

        self.text = HuggingFaceEmbeddings(model_name=TEXT_EMBEDDING_MODEL)
        self.store = FAISS.load_local(str(BASELINE_INDEX), _Dummy(), allow_dangerous_deserialization=True)

    def run(self, question: str, k: int) -> dict:
        v = self.text.embed_query(question)
        docs = self.store.similarity_search_by_vector(v, k=max(k, 1))
        return {"intent": "search", "ids": [d.metadata["MOF_ID"] for d in docs], "relaxed": False,
                "n": None, "value": None, "kind": "rows"}


# ------------------------------------------------------------- benchmark run
def run_benchmark(use_llm: bool, path: Path = BENCH) -> tuple[pd.DataFrame, dict]:
    queries = json.loads(path.read_text())
    rules_agent = MOFChatAgent(use_llm=False)
    golds = {}
    for q in queries:
        gp = gold_plan(q)
        g = outcome(rules_agent, gp)
        g["filter_ids"] = gold_filter_ids(gp)
        g["plan"] = gp
        golds[q["id"]] = g

    systems: dict[str, callable] = {}
    baseline = TwoTowerBaseline() if BASELINE_INDEX.exists() else None
    if baseline:
        systems["Review-1 two-tower (shipped)"] = lambda q, g: (None, baseline.run(q["question"], g["plan"].limit))
    systems["Rules planner (no LLM)"] = lambda q, g: _agent_run(rules_agent, q)

    llm_ok = use_llm and llm.status()[0]
    if llm_ok:
        if not hasattr(llm.llm_plan, "cache_info"):
            llm.llm_plan = _cached_llm_plan(llm.llm_plan)
        llm_agent = MOFChatAgent(use_llm=True, planner_mode="llm")
        hybrid_agent = MOFChatAgent(use_llm=True, planner_mode="hybrid")

        def single_shot(q, g):
            obj, _ = llm.llm_plan(q["question"], ())
            if obj is None:
                return None, {"intent": "error"}
            obj["source"] = "llm"
            p, errs = validator.validate_plan(obj, q["question"], expand=True, check_grounding=False)
            if errs:
                return p, {"intent": "error"}
            return p, outcome(rules_agent, p)

        systems["LLM planner, single shot (no validator)"] = single_shot
        systems["LLM planner + validator"] = lambda q, g: _agent_run(llm_agent, q)
        systems["Hybrid (default)"] = lambda q, g: _agent_run(hybrid_agent, q)

    rows = []
    for name, fn in systems.items():
        print(f"\n### {name}")
        for q in queries:
            g = golds[q["id"]]
            t = time.time()
            plan, got = fn(q, g)
            dt = time.time() - t
            ok = exact_match(g, got)
            prec = None
            if g["filter_ids"] is not None and not g["relaxed"]:
                ids = got.get("ids") or []
                prec = (sum(i in g["filter_ids"] for i in ids) / len(ids)) if ids and not got.get("relaxed") else 0.0
            pk = plan_key(plan)
            rows.append({"system": name, "id": q["id"], "category": q["category"], "question": q["question"],
                         "exact": ok, "precision_at_k": prec,
                         "plan_correct": None if plan is None and name.startswith("Review") else pk == plan_key(g["plan"]),
                         "latency_s": round(dt, 3),
                         "plan": plan.summary() if plan is not None else "",
                         "gold_plan": g["plan"].summary(), "returned": ", ".join((got.get("ids") or [])[:10]),
                         "gold": ", ".join(g.get("ids", [])[:10]) if g["intent"] != "non_db" else "(no database answer)"})
            mark = "✓" if ok else "✗"
            print(f"  {mark} {q['id']:4s} {q['question'][:70]:70s} {dt:5.2f}s")
    df = pd.DataFrame(rows)
    gold_info = {k: {"n": v.get("n"), "relaxed": v.get("relaxed")} for k, v in golds.items()}
    return df, gold_info


def _cached_llm_plan(fn):
    """Memoise LLM plans (temperature 0) so the llm-only and hybrid systems see identical LLM output."""
    @functools.lru_cache(maxsize=None)
    def cached(question, fb):
        return fn(question, [tuple(f) for f in fb])

    def wrapped(question, feedback=()):
        return cached(question, tuple(tuple(f) for f in feedback))
    wrapped.cache_info = cached.cache_info
    return wrapped


def _agent_run(agent: MOFChatAgent, q):
    plan, trace = agent.plan(q["question"])
    if agent.use_llm and any("LLM planner failed" in t for t in trace):
        raise RuntimeError(f"LLM planner crashed on {q['id']}: {trace}")
    if plan.intent == "knowledge":
        snippets = knowledge.search(q["question"], 3)
        if not knowledge.is_relevant(snippets):
            plan.intent = "out_of_scope"
    return plan, outcome(agent, plan)


# ------------------------------------------------------- answer validation
ANSWER_QUESTIONS = ["B1", "B2", "B5", "C1", "C6", "D1", "D7", "E1", "E3", "F1", "F2", "F3", "G1", "G4", "H1", "H4"]


def run_answer_validation() -> dict | None:
    if not llm.status()[0]:
        return None
    queries = {q["id"]: q for q in json.loads(BENCH.read_text())}
    agent = MOFChatAgent(use_llm=True, planner_mode="hybrid")
    recs = []
    for qid in ANSWER_QUESTIONS:
        t = time.time()
        r = agent.answer(queries[qid]["question"])
        v = r.validation or {}
        first = v.get("first_draft", {})
        recs.append({"id": qid, "seconds": round(time.time() - t, 1),
                     "draft_invalid_ids": first.get("invalid_ids", []),
                     "draft_corrected_ids": first.get("corrected_ids", {}),
                     "draft_unverified_numbers": first.get("unverified_numbers", []),
                     "final_invalid_ids": v.get("invalid_ids", []),
                     "final_unverified_numbers": v.get("unverified_numbers", []),
                     "auto_corrected_ids": v.get("corrected_ids", {}), "attempts": v.get("attempts", 1)})
        print(f"  {qid}: draft ids={first.get('invalid_ids')} corr={first.get('corrected_ids')} "
              f"nums={first.get('unverified_numbers')} -> final ids={v.get('invalid_ids')} "
              f"nums={v.get('unverified_numbers')} ({recs[-1]['seconds']}s)")
    n = len(recs)
    draft_bad = sum(bool(r["draft_invalid_ids"] or r["draft_corrected_ids"] or r["draft_unverified_numbers"]) for r in recs)
    final_bad = sum(bool(r["final_invalid_ids"] or r["final_unverified_numbers"]) for r in recs)
    return {"n_answers": n,
            "first_drafts_with_unverifiable_content": draft_bad,
            "first_drafts_with_wrong_or_garbled_ids": sum(bool(r["draft_invalid_ids"] or r["draft_corrected_ids"]) for r in recs),
            "first_drafts_with_unverified_numbers": sum(bool(r["draft_unverified_numbers"]) for r in recs),
            "answers_regenerated": sum(r["attempts"] > 1 for r in recs),
            "final_answers_with_flagged_content": final_bad,
            "mean_seconds_per_answer": round(float(np.mean([r["seconds"] for r in recs])), 1),
            "details": recs}


# ------------------------------------------------------ knowledge retrieval
KNOWLEDGE_TESTS = [
    ("What is void fraction?", {"coremof_dataset.md"}),
    ("kinetic diameter of methane", {"pore_geometry_and_gases.md"}),
    ("Why are open metal sites good for CO2 capture?", {"applications.md", "mofs_basics.md"}),
    ("What probe diameter was used for the geometric descriptors?", {"coremof_dataset.md", "pore_geometry_and_gases.md", "ChatMOF.pdf"}),
    ("How accurate is ChatMOF for search, prediction and generation tasks?", {"ChatMOF.pdf"}),
    ("What is Chahine's rule?", {"applications.md"}),
    ("How does MOFChat rank MOFs with several objectives?", {"mofchat_methods.md"}),
    ("What is the CSD refcode of HKUST-1?", {"mofs_basics.md"}),
    ("Which topologies does ChatMOF's genetic algorithm use?", {"ChatMOF.pdf"}),
    ("What does molecular sieving mean?", {"pore_geometry_and_gases.md"}),
    ("Is pore volume independent of void fraction and density?", {"coremof_dataset.md"}),
    ("What limits the number of structures ChatMOF can generate?", {"ChatMOF.pdf"}),
]
OFF_TOPIC = ["recipe for chocolate cake", "who won the football world cup", "best smartphone to buy this year",
             "how do I learn to play guitar", "what is the weather in Chennai tomorrow"]


def run_knowledge_eval() -> dict:
    hit1 = hit3 = accepted = 0
    details = []
    for q, expected in KNOWLEDGE_TESTS:
        s = knowledge.search(q, 3)
        srcs = [x.source for x in s]
        h1, h3 = srcs[:1] and srcs[0] in expected, any(x in expected for x in srcs)
        hit1 += bool(h1)
        hit3 += bool(h3)
        accepted += knowledge.is_relevant(s)
        details.append({"question": q, "top3": srcs, "top_score": round(s[0].score, 3) if s else None,
                        "hit@1": bool(h1), "hit@3": bool(h3)})
    rejected = 0
    for q in OFF_TOPIC:
        s = knowledge.search(q, 3)
        rejected += not knowledge.is_relevant(s)
        details.append({"question": q, "off_topic": True, "top_score": round(s[0].score, 3) if s else None})
    n = len(KNOWLEDGE_TESTS)
    return {"n_questions": n, "hit@1": hit1 / n, "hit@3": hit3 / n, "in_domain_accepted": accepted / n,
            "off_topic_rejected": rejected / len(OFF_TOPIC), "threshold": knowledge.RELEVANCE_THRESHOLD,
            "details": details}


# ------------------------------------------------------------------- report
def summarise(df: pd.DataFrame) -> dict:
    out = {}
    for name, g in df.groupby("system", sort=False):
        prec = g.precision_at_k.dropna()
        plans = g.plan_correct.dropna()
        out[name] = {"result_accuracy": round(100 * g.exact.mean(), 1),
                     "constraint_precision_at_k": round(100 * prec.mean(), 1) if len(prec) else None,
                     "plan_accuracy": round(100 * plans.astype(float).mean(), 1) if len(plans) else None,
                     "mean_latency_s": round(g.latency_s.mean(), 3),
                     "by_category": {c: round(100 * gg.exact.mean(), 1) for c, gg in g.groupby("category", sort=False)}}
    return out


def plot(df: pd.DataFrame, path: Path) -> None:
    pivot = df.pivot_table(index="category", columns="system", values="exact", aggfunc="mean", sort=False) * 100
    systems = list(dict.fromkeys(df.system))
    pivot = pivot[systems]
    fig, ax = plt.subplots(figsize=(13, 6))
    w = 0.8 / len(systems)
    x = np.arange(len(pivot))
    colors = ["#bab0ac", "#72b7b2", "#f58518", "#54a24b", "#4c78a8"][-len(systems):]
    for i, s in enumerate(systems):
        ax.bar(x + i * w - 0.4 + w / 2, pivot[s], w, label=s, color=colors[i])
    ax.set_xticks(x, pivot.index, rotation=20, ha="right")
    ax.set_ylabel("exact answer match (%)")
    ax.set_ylim(0, 105)
    ax.set_title("MOFChat retrieval benchmark: answer accuracy by question type")
    ax.legend(fontsize=8, loc="upper center", bbox_to_anchor=(0.5, -0.32), ncol=3, frameon=False)
    plt.tight_layout()
    plt.savefig(path, dpi=150)
    plt.close(fig)


def write_results_md(summary: dict) -> None:
    pm = json.loads((PROPERTY_MODEL_DIR / "metrics.json").read_text()) if (PROPERTY_MODEL_DIR / "metrics.json").exists() else {}
    em = json.loads((FT_EMBED_DIR / "metrics.json").read_text()) if (FT_EMBED_DIR / "metrics.json").exists() else {}
    b = summary["benchmark"]
    L = ["# MOFChat - results", "",
         f"_Generated by `python evaluate.py` on {summary['generated']}. Numbers are copied from "
         "`artifacts/` - do not edit by hand._", "",
         f"## 1. Retrieval benchmark ({b['n_queries']} labelled questions, 10 categories)", "",
         "A system is counted correct only if it returns exactly the MOFs (or the count/average) that the "
         "hand-written gold plan returns from the database.", "",
         "| System | Exact answer match | Constraint precision@k | Plan accuracy | Planning latency* |",
         "|---|---:|---:|---:|---:|"]
    for name, s in b["systems"].items():
        f = lambda v, suf="%": "-" if v is None else f"{v}{suf}"  # noqa: E731
        L.append(f"| {name} | {f(s['result_accuracy'])} | {f(s['constraint_precision_at_k'])} | "
                 f"{f(s['plan_accuracy'])} | {s['mean_latency_s']:.2f} s |")
    L += ["", "\\* LLM plans are cached across the three LLM-based systems (temperature 0, so the outputs are identical); "
          "only the single-shot row shows the real cost of one Llama 3 planning call. Retries and the full answer "
          "(planning + retrieval + answer writing + validation) are timed in section 2."]
    cats = list(next(iter(b["systems"].values()))["by_category"])
    L += ["", "Exact answer match by question type (%):", "",
          "| Category | " + " | ".join(b["systems"]) + " |", "|---|" + "---:|" * len(b["systems"])]
    for c in cats:
        L.append(f"| {c} | " + " | ".join(str(s["by_category"].get(c, "-")) for s in b["systems"].values()) + " |")
    h = summary.get("heldout")
    if h:
        L += ["", f"**Held-out set** ({h['n_queries']} new phrasings written after the rule parser was tuned on the "
              "development set, and never used for tuning):", "",
              "| System | Exact answer match | Constraint precision@k | Plan accuracy |", "|---|---:|---:|---:|"]
        for name, s in h["systems"].items():
            f = lambda v, suf="%": "-" if v is None else f"{v}{suf}"  # noqa: E731
            L.append(f"| {name} | {f(s['result_accuracy'])} | {f(s['constraint_precision_at_k'])} | {f(s['plan_accuracy'])} |")
    csv = EVAL_DIR / "benchmark_results.csv"
    if h and csv.exists():
        d = pd.read_csv(csv)
        fails = d[(d.set == "held-out") & (d.system == "Hybrid (default)") & (~d.exact)]
        if len(fails):
            L += ["", "Held-out questions the default (hybrid) system got wrong, for error analysis:", "",
                  "| Question | System plan | Gold plan |", "|---|---|---|"]
            for _, r in fails.iterrows():
                L.append(f"| {r.question} | `{r.plan}` | `{r.gold_plan}` |")
    L += ["", "![benchmark](../artifacts/eval/benchmark_by_category.png)", "",
          "For context, ChatMOF (GPT-4) reports 96.9 % accuracy on its own 100 search questions "
          "(excluding token-limit failures); the question sets differ, so the numbers are not directly comparable.", ""]
    av = summary.get("answer_validation")
    if av:
        L += ["## 2. Answer validation (hallucination check)", "",
              f"- Llama 3 answers generated: {av['n_answers']}",
              f"- First drafts containing at least one unverifiable MOF ID or number: "
              f"{av['first_drafts_with_unverifiable_content']} ({av['first_drafts_with_wrong_or_garbled_ids']} with wrong/garbled IDs, "
              f"{av['first_drafts_with_unverified_numbers']} with unverified numbers)",
              f"- Answers regenerated after validator feedback: {av['answers_regenerated']}",
              f"- Final answers still carrying a validator warning: {av['final_answers_with_flagged_content']}",
              f"- Mean time per full answer: {av['mean_seconds_per_answer']} s", ""]
    kr = summary.get("knowledge_retrieval")
    if kr:
        L += ["## 3. Knowledge retrieval (RAG)", "",
              f"- hit@1 {kr['hit@1']:.0%}, hit@3 {kr['hit@3']:.0%} on {kr['n_questions']} questions with a known source",
              f"- In-domain questions accepted: {kr['in_domain_accepted']:.0%}; off-topic questions rejected: "
              f"{kr['off_topic_rejected']:.0%} (cosine threshold {kr['threshold']})", ""]
    if pm:
        L += ["## 4. Property prediction (held-out 10 % test split)", ""]
        for t, r in pm.items():
            L += [f"**{t}** ({r['unit'] or 'dimensionless'}) from {', '.join(r['features'])}", "",
                  "| Model | MAE | RMSE | R² |", "|---|---:|---:|---:|"]
            for mname, v in r["models"].items():
                m = v["test_all"]
                L.append(f"| {mname} | {m['MAE']:.4g} | {m['RMSE']:.4g} | {m['R2']:.4f} |")
            L += ["", f"- Split-conformal 90 % interval: ±{r['conformal']['half_width']:.4g}, test coverage "
                      f"{r['conformal']['test_coverage']:.1%}; GPR 95 % interval coverage {r['gpr']['coverage_95']:.1%}"]
            if "hurdle" in r:
                L.append(f"- Physics rule `{r['hurdle']['rule']}`: accuracy {r['hurdle']['rule_accuracy_test']:.2%} on test")
            top = sorted(r["shap_mean_abs"].items(), key=lambda kv: -kv[1])
            L.append("- Mean |SHAP| (XGBoost): " + ", ".join(f"{k} {v:.3g}" for k, v in top))
            L += ["", f"![parity](../artifacts/property_models/parity_{t}.png)",
                  f"![shap](../artifacts/property_models/shap_summary_{t}.png)", ""]
    if em:
        s = em["similarity"]
        L += ["## 5. FT-Transformer embeddings (similarity search)", "",
              f"Masked-descriptor autoencoder, {em['n_params']:,} parameters, {em['epochs_trained']} epochs "
              f"({em['train_seconds']} s). {s['n_queries']} random query MOFs, {s['k']} neighbours each:", "",
              "| Neighbours from | Mean descriptor difference (σ) | Same metal | Same open-metal-site flag |",
              "|---|---:|---:|---:|"]
        for k in ("ft_embedding", "raw_descriptor_knn", "random"):
            v = s[k]
            L.append(f"| {k.replace('_', ' ')} | {v['mean_abs_descriptor_diff_std']:.3f} | {v['same_metal_rate']:.1%} | "
                     f"{v['same_open_metal_site_rate']:.1%} |")
        L += ["", f"Overlap of FT-Transformer and raw-descriptor neighbour lists: {s['overlap_ft_vs_raw_knn']:.0%}.",
              "Raw k-NN optimises exactly the descriptor-difference metric, so it is an upper bound on that "
              "column; the FT embedding is close to it while matching metal and open-metal-site more often, "
              "because those categorical tokens are part of its input.", ""]
    (PROJECT_ROOT / "docs").mkdir(exist_ok=True)
    (PROJECT_ROOT / "docs" / "RESULTS.md").write_text("\n".join(L))


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--no-llm", action="store_true")
    args = ap.parse_args()
    EVAL_DIR.mkdir(parents=True, exist_ok=True)
    df, gold_info = run_benchmark(use_llm=not args.no_llm)
    print("\n=== Held-out questions ===")
    dh, gold_h = run_benchmark(use_llm=not args.no_llm, path=HELDOUT)
    pd.concat([df.assign(set="development"), dh.assign(set="held-out")]).to_csv(
        EVAL_DIR / "benchmark_results.csv", index=False)
    plot(df, EVAL_DIR / "benchmark_by_category.png")
    summary = {"generated": time.strftime("%Y-%m-%d %H:%M"),
               "benchmark": {"n_queries": int(df.id.nunique()), "systems": summarise(df), "gold": gold_info},
               "heldout": {"n_queries": int(dh.id.nunique()), "systems": summarise(dh), "gold": gold_h}}
    print("\n=== Answer validation ===")
    summary["answer_validation"] = None if args.no_llm else run_answer_validation()
    print("\n=== Knowledge retrieval ===")
    summary["knowledge_retrieval"] = run_knowledge_eval()
    (EVAL_DIR / "summary.json").write_text(json.dumps(summary, indent=2, default=str))
    write_results_md(summary)
    for name, s in summary["benchmark"]["systems"].items():
        print(f"{name:45s} exact={s['result_accuracy']:5.1f}%  precision={s['constraint_precision_at_k']}  "
              f"plan={s['plan_accuracy']}  latency={s['mean_latency_s']:.2f}s")
    print("held-out:")
    for name, s in summary["heldout"]["systems"].items():
        print(f"{name:45s} exact={s['result_accuracy']:5.1f}%  plan={s['plan_accuracy']}")
    print(json.dumps({k: v for k, v in summary["knowledge_retrieval"].items() if k != "details"}, indent=2))


if __name__ == "__main__":
    main()
