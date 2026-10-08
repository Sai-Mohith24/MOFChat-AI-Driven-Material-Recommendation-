"""
evaluate.py - end-to-end evaluation of MOFChat.

  python evaluate.py            # full run: compares the free cloud models and local Ollama models
  python evaluate.py --no-llm   # only the systems that do not need the LLM

0. Model comparison: every model in COMPARE_MODELS on both question sets, fallback off.
   The best one on the held-out set is used for the tables below.

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
2. Answer validation: how often each model's first draft contains unverifiable MOF IDs or numbers,
   and what remains after the validator's retry/correction.
3. Knowledge retrieval: hit@1 / hit@3 of the expected source; off-topic rejection.

Writes artifacts/eval/{summary.json, benchmark_results.csv, benchmark_by_category.png,
model_comparison.csv, model_comparison.png} and docs/RESULTS.md.
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
def run_benchmark(use_llm: bool, path: Path = BENCH, model_id: str | None = None,
                  include_baselines: bool = True) -> tuple[pd.DataFrame, dict]:
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
    if include_baselines:
        baseline = TwoTowerBaseline() if BASELINE_INDEX.exists() else None
        if baseline:
            systems["Review-1 two-tower (shipped)"] = lambda q, g: (None, baseline.run(q["question"], g["plan"].limit))
        systems["Rules planner (no LLM)"] = lambda q, g: _agent_run(rules_agent, q)

    llm_ok = use_llm and llm.status(model_id)[0]
    if llm_ok:
        if not hasattr(llm.llm_plan, "cache_info"):
            llm.llm_plan = _cached_llm_plan(llm.llm_plan)
        llm_agent = MOFChatAgent(use_llm=True, planner_mode="llm", model_id=model_id)
        hybrid_agent = MOFChatAgent(use_llm=True, planner_mode="hybrid", model_id=model_id)

        def single_shot(q, g):
            try:
                obj, _, _ = llm.llm_plan(q["question"], (), model_id)
            except llm.LLMError:
                return None, {"intent": "error", "llm_failed": True}
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
            rows.append({"system": name, "model": model_id if name not in ("Review-1 two-tower (shipped)",
                                                                           "Rules planner (no LLM)") else "",
                         "id": q["id"], "category": q["category"], "question": q["question"],
                         "exact": ok, "precision_at_k": prec, "llm_failed": bool(got.get("llm_failed")),
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
    def cached(question, fb, model_id):
        return fn(question, [tuple(f) for f in fb], model_id)

    def wrapped(question, feedback=(), model_id=None):
        return cached(question, tuple(tuple(f) for f in feedback), model_id)
    wrapped.cache_info = cached.cache_info
    return wrapped


def _agent_run(agent: MOFChatAgent, q):
    plan, trace = agent.plan(q["question"])
    failed = agent.use_llm and any("LLM planner failed" in t for t in trace)   # rate limit / outage
    if plan.intent == "knowledge":
        snippets = knowledge.search(q["question"], 3)
        if not knowledge.is_relevant(snippets):
            plan.intent = "out_of_scope"
    got = outcome(agent, plan)
    got["llm_failed"] = failed
    return plan, got


# ------------------------------------------------------- answer validation
ANSWER_QUESTIONS = ["B1", "B2", "B5", "C1", "C6", "D1", "D7", "E1", "E3", "F1", "F2", "F3", "G1", "G4", "H1", "H4"]


def run_answer_validation(model_id: str | None = None) -> dict | None:
    if not llm.status(model_id)[0]:
        return None
    queries = {q["id"]: q for q in json.loads(BENCH.read_text())}
    agent = MOFChatAgent(use_llm=True, planner_mode="hybrid", model_id=model_id)
    recs = []
    for qid in ANSWER_QUESTIONS:
        t = time.time()
        r = agent.answer(queries[qid]["question"])
        v = r.validation or {}
        first = v.get("first_draft", {})
        recs.append({"id": qid, "seconds": round(time.time() - t, 1), "models_used": r.models_used,
                     "answer_llm_failed": any("LLM answer failed" in x for x in r.trace),
                     "draft_invalid_ids": first.get("invalid_ids", []),
                     "draft_corrected_ids": first.get("corrected_ids", {}),
                     "draft_unverified_numbers": first.get("unverified_numbers", []),
                     "draft_false_claims": first.get("false_claims", []),
                     "final_invalid_ids": v.get("invalid_ids", []),
                     "final_unverified_numbers": v.get("unverified_numbers", []),
                     "final_false_claims": v.get("false_claims", []),
                     "auto_corrected_ids": v.get("corrected_ids", {}), "attempts": v.get("attempts", 1)})
        print(f"  {qid}: draft ids={first.get('invalid_ids')} corr={first.get('corrected_ids')} "
              f"nums={first.get('unverified_numbers')} claims={first.get('false_claims')} -> final "
              f"ids={v.get('invalid_ids')} nums={v.get('unverified_numbers')} claims={v.get('false_claims')} "
              f"({recs[-1]['seconds']}s)")
    n = len(recs)
    draft_bad = sum(bool(r["draft_invalid_ids"] or r["draft_corrected_ids"] or r["draft_unverified_numbers"]
                         or r["draft_false_claims"]) for r in recs)
    final_bad = sum(bool(r["final_invalid_ids"] or r["final_unverified_numbers"] or r["final_false_claims"])
                    for r in recs)
    return {"n_answers": n,
            "answer_llm_failures": sum(r["answer_llm_failed"] for r in recs),   # template answer used instead
            "first_drafts_with_unverifiable_content": draft_bad,
            "first_drafts_with_wrong_or_garbled_ids": sum(bool(r["draft_invalid_ids"] or r["draft_corrected_ids"]) for r in recs),
            "first_drafts_with_unverified_numbers": sum(bool(r["draft_unverified_numbers"]) for r in recs),
            "first_drafts_with_false_claims": sum(bool(r["draft_false_claims"]) for r in recs),
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


RERUN_LABEL = {"answers_rerun_on": "answer validation re-run", "knowledge_rerun_on": "knowledge retrieval re-run",
               "models_rerun_on": "model summary recomputed from the saved results"}


def write_results_md(summary: dict) -> None:
    pm = json.loads((PROPERTY_MODEL_DIR / "metrics.json").read_text()) if (PROPERTY_MODEL_DIR / "metrics.json").exists() else {}
    em = json.loads((FT_EMBED_DIR / "metrics.json").read_text()) if (FT_EMBED_DIR / "metrics.json").exists() else {}
    b = summary["benchmark"]
    dm = summary.get("default_model")
    dm_label = llm.BY_ID[dm].label if dm in llm.BY_ID else "the LLM"
    L = ["# MOFChat - results", "",
         f"_Generated by `python evaluate.py` on {summary['generated']}"
         + "".join(f"; {RERUN_LABEL.get(k, k)} on {v}" for k, v in summary.items() if k in RERUN_LABEL)
         + ". Numbers are copied from `artifacts/` - do not edit by hand._", "",
         f"## 1. Retrieval benchmark ({b['n_queries']} labelled questions, 10 categories)", "",
         "A system is counted correct only if it returns exactly the MOFs (or the count/average) that the "
         "hand-written gold plan returns from the database.", "",
         "| System | Exact answer match | Constraint precision@k | Plan accuracy | Planning latency* |",
         "|---|---:|---:|---:|---:|"]
    llm_lat = (summary.get("model_comparison") or {}).get(dm, {}).get("held-out_planner_latency_s")
    for name, s in b["systems"].items():
        f = lambda v, suf="%": "-" if v is None else f"{v}{suf}"  # noqa: E731
        lat = llm_lat if llm_lat is not None and name.startswith(("LLM", "Hybrid")) else s["mean_latency_s"]
        L.append(f"| {name} | {f(s['result_accuracy'])} | {f(s['constraint_precision_at_k'])} | "
                 f"{f(s['plan_accuracy'])} | {lat:.2f} s |")
    L += ["", f"\\* LLM rows: median time of one {dm_label} planning call on the held-out run of the model comparison (the plans "
          "are cached and reused across the three LLM systems, temperature 0; the median leaves out free-tier "
          "rate-limit waits). Validation and the hybrid merge add under 0.01 s. The full answer (planning + "
          "retrieval + answer writing + validation) is timed in section 2."]
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
    mc = summary.get("model_comparison") or {}
    if mc:
        dm = summary.get("default_model")
        L += ["## 1b. Which free LLM is best? (model comparison)", "",
              "Each model is tested on its own, with automatic fallback switched off. OpenRouter free accounts allow "
              "about 50 requests per day, so the OpenRouter model was tested on the held-out set only. "
              f"The main tables above use **{mc.get(dm, {}).get('label', dm)}**, the best model on the held-out set.", "",
              "| Model | Provider | Held-out: LLM alone | Held-out: hybrid | Development: LLM alone | Development: hybrid "
              "| Median planning time per call (dev / held-out) | Provider errors* |",
              "|---|---|---:|---:|---:|---:|---:|---:|"]
        f = lambda v, suf="%": "-" if v is None else f"{v}{suf}"  # noqa: E731

        def alone(v, st):
            a = v.get(f"{st}_single_shot_answered")
            return f(v.get(f"{st}_single_shot")) + (f" ({a[0]}% of the {a[1]} answered)" if a else "")
        for mid, v in mc.items():
            errs = sum(x for x in (v.get("development_provider_errors"), v.get("held-out_provider_errors")) if x)
            quota = " †" if v.get("development_quota_exhausted") or v.get("held-out_quota_exhausted") else ""
            L.append(f"| {v['label']}{' **(default)**' if mid == dm else ''}{quota} | {v['provider']} | "
                     f"{alone(v, 'held-out')} | {f(v.get('held-out_hybrid'))} | "
                     f"{alone(v, 'development')} | {f(v.get('development_hybrid'))} | "
                     f"{f(v.get('development_planner_latency_s'), '')} / {f(v.get('held-out_planner_latency_s'), ' s')} "
                     f"| {errs} |")
        L += ["", "\\* Requests that failed at the provider (rate limit, overload, outage). In the app, these "
              "fall back to the next model automatically. Free-tier latency also depends on provider load at the "
              "time of the run, so the two medians can differ a lot for the same model."]
        if any(v.get("development_quota_exhausted") or v.get("held-out_quota_exhausted") for v in mc.values()):
            L += ["", "† The model's free daily quota ran out during the run (429 RESOURCE_EXHAUSTED), so most "
                  "planning calls failed and its scores would measure the rule-parser fallback, not the model; "
                  "they are left out (\\-) and the model is not considered for the default."]
        L += ["",
              "![models](../artifacts/eval/model_comparison.png)", ""]
        ans = [(v["label"], v["answers"]) for v in mc.values() if v.get("answers")
               and not v.get("held-out_quota_exhausted")]
        if ans:
            L += ["Answer writing (16 questions per model, checked by the answer validator):", "",
                  "| Model | LLM call failed (template used) | First drafts with any problem "
                  "| of which false comparison claims | Regenerated | Still flagged | Seconds per full answer |",
                  "|---|---:|---:|---:|---:|---:|---:|"]
            for label, a in ans:
                dash = lambda k: "-" if a.get(k) is None else a[k]  # noqa: E731
                L.append(f"| {label} | {dash('answer_llm_failures')} | "
                         f"{a['first_drafts_with_unverifiable_content']} of {a['n_answers']} | "
                         f"{dash('first_drafts_with_false_claims')} | {a['answers_regenerated']} | "
                         f"{a['final_answers_with_flagged_content']} | {a['mean_seconds_per_answer']} |")
            L.append("")
    av = summary.get("answer_validation")
    if av:
        L += ["## 2. Answer validation (hallucination check)", "",
              f"- {dm_label} answers generated: {av['n_answers']}"
              + (f" ({av['answer_llm_failures']} LLM calls failed; a template answer was used)"
                 if av.get("answer_llm_failures") else ""),
              f"- First drafts with at least one problem: {av['first_drafts_with_unverifiable_content']} "
              f"({av['first_drafts_with_wrong_or_garbled_ids']} with wrong/garbled IDs, "
              f"{av['first_drafts_with_unverified_numbers']} with unverified numbers, "
              f"{av.get('first_drafts_with_false_claims', '-')} with false comparison claims such as "
              "\"A, B and C have surface areas >= 6000 m²/g\" when B has less)",
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


COMPARE_MODELS = ["llama3-local", "gpt-oss-120b", "qwen3.8-27b",
                  "gemini-3.5-flash", "gemini-3.1-flash-lite", "nemotron-super-free"]


def run_model_comparison(models: list[str]) -> pd.DataFrame:
    """Every model on both question sets, one model at a time (no fallback), so each score belongs to
    the model named. OpenRouter free accounts allow ~50 requests/day, so those models get the held-out
    set only."""
    frames = []
    for mid in models:
        ok, why = llm.availability(mid)
        if not ok:
            print(f"\n### skipping {mid}: {why}")
            continue
        sets = [("held-out", HELDOUT)] if llm.BY_ID[mid].provider is llm.Provider.OPENROUTER else \
            [("development", BENCH), ("held-out", HELDOUT)]
        for set_name, path in sets:
            print(f"\n##### model {mid} - {set_name}")
            d, _ = run_benchmark(True, path, model_id=mid, include_baselines=False)
            frames.append(d.assign(set=set_name))
    return pd.concat(frames, ignore_index=True) if frames else pd.DataFrame()


def summarise_models(dc: pd.DataFrame, answers: dict) -> dict:
    out = {}
    for mid, g in dc.groupby("model", sort=False):
        spec = llm.BY_ID[mid]
        row = {"label": spec.label, "provider": llm.PROVIDER_LABEL[spec.provider]}
        for set_name, gs in g.groupby("set", sort=False):
            ss = gs[gs.system == "LLM planner, single shot (no validator)"]
            # most calls failed at the provider (e.g. the free daily quota ran out): the scores would
            # measure the rule-parser fallback, not the model, so they are not reported
            exhausted = len(ss) > 0 and ss.llm_failed.mean() > 0.5
            if exhausted:
                row[f"{set_name}_quota_exhausted"] = True
            for sysname, key in (("LLM planner, single shot (no validator)", "single_shot"),
                                 ("LLM planner + validator", "validated"), ("Hybrid (default)", "hybrid")):
                x = gs[gs.system == sysname]
                if len(x):
                    row[f"{set_name}_{key}"] = None if exhausted else round(100 * x.exact.mean(), 1)
            answered = ss[~ss.llm_failed.astype(bool)]
            if not exhausted and 0 < len(answered) < len(ss):     # provider errors count as wrong above
                row[f"{set_name}_single_shot_answered"] = [round(100 * answered.exact.mean(), 1), len(answered)]
            # median, not mean: on free tiers about one call in four waits up to a minute for the budget
            row[f"{set_name}_planner_latency_s"] = round(float(ss.latency_s.median()), 2) if len(ss) and not exhausted \
                else None
            row[f"{set_name}_provider_errors"] = int(ss.llm_failed.sum()) if len(ss) else None
        if mid in answers and answers[mid]:
            a = answers[mid]
            row["answers"] = {k: a.get(k) for k in ("n_answers", "answer_llm_failures", "first_drafts_with_unverifiable_content",
                                                     "first_drafts_with_false_claims", "answers_regenerated",
                                                     "final_answers_with_flagged_content", "mean_seconds_per_answer")}
        out[mid] = row
    return out


def plot_models(models: dict, path: Path) -> None:
    names = [v["label"] for v in models.values()]
    num = lambda v, k: np.nan if v.get(k) is None else v[k]  # noqa: E731
    dev = [num(v, "development_hybrid") for v in models.values()]
    held = [num(v, "held-out_hybrid") for v in models.values()]
    single = [num(v, "held-out_single_shot") for v in models.values()]
    x = np.arange(len(names))
    fig, ax = plt.subplots(figsize=(12, 5.5))
    ax.bar(x - 0.27, single, 0.27, label="held-out, LLM alone (single shot)", color="#f58518")
    ax.bar(x, held, 0.27, label="held-out, hybrid (LLM + validator + rules)", color="#4c78a8")
    ax.bar(x + 0.27, dev, 0.27, label="development set, hybrid", color="#9ecae9")
    for xi, v in zip(x, held):
        if not np.isnan(v):
            ax.text(xi, v + 1, f"{v:.0f}", ha="center", fontsize=8)
    ax.set_xticks(x, names, rotation=20, ha="right")
    ax.set_ylim(0, 108)
    ax.set_ylabel("exact answer match (%)")
    ax.set_title("Which free LLM plans MOF queries best?")
    ax.legend(fontsize=8, loc="upper center", bbox_to_anchor=(0.5, -0.38), ncol=3, frameon=False)
    plt.tight_layout()
    plt.savefig(path, dpi=150)
    plt.close(fig)


def pick_default(models: dict) -> str | None:
    """Best held-out hybrid accuracy, then development accuracy, then fewer provider errors, then speed."""
    scored = []
    for mid, v in models.items():
        if v.get("held-out_hybrid") is None or v.get("development_hybrid") is None:
            continue     # must have been tested on both sets
        scored.append((-v["held-out_hybrid"], -v["development_hybrid"],
                       (v.get("development_provider_errors") or 0) + (v.get("held-out_provider_errors") or 0),
                       v.get("held-out_planner_latency_s") or 99, mid))
    return sorted(scored)[0][-1] if scored else None


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--no-llm", action="store_true")
    ap.add_argument("--models", default=",".join(COMPARE_MODELS),
                    help="comma-separated model ids to compare (see python -m mofchat.llm --list)")
    ap.add_argument("--model", default=None, help="model for the main tables (default: best in the comparison)")
    ap.add_argument("--answers", default="llama3-local,gpt-oss-120b,gemini-3.1-flash-lite,qwen3.8-27b",
                    help="models whose written answers are checked by the answer validator")
    ap.add_argument("--only", choices=["answers", "knowledge", "models"], default=None,
                    help="re-run only the answer validation or the knowledge-retrieval test (after changing the "
                         "validator or the knowledge notes) and update summary.json and docs/RESULTS.md; "
                         "the benchmark results are kept")
    args = ap.parse_known_args()[0]
    EVAL_DIR.mkdir(parents=True, exist_ok=True)
    llm.FALLBACK_ENABLED = False          # attribute every result to exactly one model
    llm.MAX_WAIT_S = 180.0                # wait for free-tier budgets instead of falling back

    if args.only:
        summary = json.loads((EVAL_DIR / "summary.json").read_text())
        if args.only == "knowledge":
            summary["knowledge_retrieval"] = run_knowledge_eval()
        if args.only == "models":           # no API calls: recompute from the saved per-question results
            old = summary.get("model_comparison") or {}
            answers = {m: v["answers"] for m, v in old.items() if v.get("answers")}
            summary["model_comparison"] = summarise_models(pd.read_csv(EVAL_DIR / "model_comparison.csv"), {})
            for m, a in answers.items():
                if m in summary["model_comparison"]:
                    summary["model_comparison"][m]["answers"] = a
            plot_models(summary["model_comparison"], EVAL_DIR / "model_comparison.png")
        for mid in [m.strip() for m in args.answers.split(",") if m.strip()] if args.only == "answers" else []:
            if not llm.availability(mid)[0]:
                continue
            print(f"\n=== Answer validation: {mid} ===")
            a = run_answer_validation(mid)
            if mid == summary.get("default_model"):
                summary["answer_validation"] = a
            row = summary.get("model_comparison", {}).get(mid)
            if row is not None and a:
                row["answers"] = {k: a.get(k) for k in ("n_answers", "answer_llm_failures",
                                                        "first_drafts_with_unverifiable_content",
                                                        "first_drafts_with_false_claims", "answers_regenerated",
                                                        "final_answers_with_flagged_content",
                                                        "mean_seconds_per_answer")}
        summary[f"{args.only}_rerun_on"] = time.strftime("%Y-%m-%d %H:%M")
        (EVAL_DIR / "summary.json").write_text(json.dumps(summary, indent=2, default=str))
        write_results_md(summary)
        return

    models_summary, dc, default_model = {}, pd.DataFrame(), None
    if not args.no_llm:
        llm.llm_plan = _cached_llm_plan(llm.llm_plan)
        dc = run_model_comparison([m.strip() for m in args.models.split(",") if m.strip()])
        if len(dc):
            dc.to_csv(EVAL_DIR / "model_comparison.csv", index=False)
        models_summary = summarise_models(dc, {}) if len(dc) else {}
        default_model = args.model or pick_default(models_summary) or llm.default_model_id()

    print(f"\n=== Main tables (LLM systems use: {default_model}) ===")
    df, gold_info = run_benchmark(use_llm=not args.no_llm, model_id=default_model)
    print("\n=== Held-out questions ===")
    dh, gold_h = run_benchmark(use_llm=not args.no_llm, path=HELDOUT, model_id=default_model)
    pd.concat([df.assign(set="development"), dh.assign(set="held-out")]).to_csv(
        EVAL_DIR / "benchmark_results.csv", index=False)
    plot(df, EVAL_DIR / "benchmark_by_category.png")

    answers = {}
    if not args.no_llm:
        answer_models = [m.strip() for m in args.answers.split(",") if m.strip()]
        answer_models += [default_model] if default_model and default_model not in answer_models else []
        for mid in answer_models:
            if llm.availability(mid)[0]:
                print(f"\n=== Answer validation: {mid} ===")
                answers[mid] = run_answer_validation(mid)
        models_summary = summarise_models(dc, answers) if len(dc) else {}
        if models_summary:
            plot_models(models_summary, EVAL_DIR / "model_comparison.png")

    summary = {"generated": time.strftime("%Y-%m-%d %H:%M"), "default_model": default_model,
               "benchmark": {"n_queries": int(df.id.nunique()), "systems": summarise(df), "gold": gold_info},
               "heldout": {"n_queries": int(dh.id.nunique()), "systems": summarise(dh), "gold": gold_h},
               "model_comparison": models_summary,
               "answer_validation": answers.get(default_model)}
    print("\n=== Knowledge retrieval ===")
    summary["knowledge_retrieval"] = run_knowledge_eval()
    (EVAL_DIR / "summary.json").write_text(json.dumps(summary, indent=2, default=str))
    write_results_md(summary)
    for mid, v in models_summary.items():
        print(f"{v['label']:42s} dev hybrid={v.get('development_hybrid')}  held-out hybrid={v.get('held-out_hybrid')} "
              f"single={v.get('held-out_single_shot')}  errors={v.get('held-out_provider_errors')}  "
              f"latency={v.get('held-out_planner_latency_s')}s")
    print("default model:", default_model)
    for name, s in summary["benchmark"]["systems"].items():
        print(f"{name:45s} exact={s['result_accuracy']:5.1f}%  plan={s['plan_accuracy']}")
    print("held-out:")
    for name, s in summary["heldout"]["systems"].items():
        print(f"{name:45s} exact={s['result_accuracy']:5.1f}%  plan={s['plan_accuracy']}")


if __name__ == "__main__":
    main()
