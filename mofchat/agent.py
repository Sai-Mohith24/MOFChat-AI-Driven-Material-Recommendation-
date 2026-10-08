"""
MOFChat agent: plan -> validate -> execute -> explain -> answer -> validate answer.
"""

from __future__ import annotations

import json
import re
import time
from dataclasses import dataclass, field
from functools import lru_cache

import numpy as np
import pandas as pd

from . import db, knowledge, rules, tools, validator
from .config import APPLICATIONS, COLUMN_BY_NAME, unit_of
from .plan import QueryPlan
from .properties import Prediction, available_targets, explain_rows, predict

PLANNER_MODES = ("hybrid", "llm", "rules")


@dataclass
class AgentResponse:
    question: str
    answer: str
    plan: QueryPlan
    result: tools.ExecResult | None = None
    table: pd.DataFrame | None = None
    predictions: list[Prediction] = field(default_factory=list)
    shap: pd.DataFrame | None = None
    snippets: list[knowledge.Snippet] = field(default_factory=list)
    validation: dict | None = None
    trace: list[str] = field(default_factory=list)
    timings: dict[str, float] = field(default_factory=dict)
    llm_used: bool = False
    models_used: list[str] = field(default_factory=list)   # which LLMs actually answered (after fallback)


@lru_cache(maxsize=1)
def _percentiles() -> dict[str, np.ndarray]:
    df = db.load_materials()
    return {c: np.sort(df[c].to_numpy(float)) for c in df.select_dtypes("number").columns}


def percentile(col: str, value: float) -> float:
    arr = _percentiles()[col]
    return 100.0 * np.searchsorted(arr, value, side="right") / len(arr)


def _fmt(col: str, v) -> str:
    if v is None or (isinstance(v, float) and np.isnan(v)):
        return "-"
    if col in ("Surface_Area", "ASA_vol", "NASA_grav", "NASA_vol"):
        return f"{v:.0f}"
    if col in ("LCD", "PLD", "LFPD"):
        return f"{v:.2f}"
    if col in ("Density", "Void_Fraction", "Pore_Volume", "constraint_violation"):
        return f"{v:.3f}"
    if col == "similarity":
        return f"{v:.4f}"
    return f"{v:.4g}" if isinstance(v, float) else str(v)


def why_text(row: pd.Series, plan: QueryPlan) -> str:
    """Percentile-based explanation of a recommended MOF for the properties the user cared about."""
    parts = []
    cols = [o.column for o in plan.objectives] + [c.column for c in plan.constraints]
    for col in dict.fromkeys(cols):
        p = percentile(col, row[col])
        direction = next((o.direction for o in plan.objectives if o.column == col), None)
        if direction is None:
            c = next(c for c in plan.constraints if c.column == col)
            direction = "max" if c.op in (">", ">=") else "min"
        arr = _percentiles()[col]
        if direction == "max":
            r = int(len(arr) - np.searchsorted(arr, row[col], side="right")) + 1   # 1 = largest
            rank = f"#{r:,} of {len(arr):,}" if r <= 120 else f"top {100 - p:.0f}%"
        else:
            r = int(np.searchsorted(arr, row[col], side="left")) + 1                # 1 = smallest
            rank = f"#{r:,} lowest of {len(arr):,}" if r <= 120 else f"lowest {p:.0f}%"
        parts.append(f"{COLUMN_BY_NAME[col].label} {_fmt(col, row[col])} {unit_of(col)} ({rank})")
    if plan.open_metal_site is not None:
        parts.append("open metal site" if row.get("Has_OMS") else "no open metal site")
    if plan.metals:
        parts.append(f"metal {row.get('Metal_Type')}")
    if "pareto_front" in row:
        parts.append(f"Pareto front {int(row['pareto_front'])}")
    return "; ".join(parts)


class MOFChatAgent:
    def __init__(self, use_llm: bool = True, planner_mode: str = "hybrid", max_retries: int = 2,
                 validate_answers: bool = True, model_id: str | None = None):
        from . import llm
        self.model_id = (model_id or llm.default_model_id()) if use_llm else None
        self.llm_ok, self.llm_status = llm.status(self.model_id) if use_llm else (False, "LLM disabled")
        self.use_llm = use_llm and bool(llm.fallback_chain(self.model_id))
        self.planner_mode = planner_mode if self.use_llm else "rules"
        self.max_retries = max_retries
        self.validate_answers = validate_answers
        self.targets = available_targets() or ("Surface_Area",)
        self.last_models: list[str] = []

    # ---------------------------------------------------------------- planning
    def plan(self, question: str) -> tuple[QueryPlan, list[str]]:
        trace: list[str] = []
        self.last_models = []
        rp, r_err = validator.validate_plan(rules.parse(question), question, expand=False,
                                            predictable=self.targets)
        if self.planner_mode == "rules" or not self.use_llm:
            trace.append(f"rule-based plan: {rp.summary()}" + (f" (errors: {r_err})" if r_err else ""))
            validator.expand_application(rp, rp.notes)
            return rp, trace

        from . import llm
        feedback, lp = [], None
        for attempt in range(self.max_retries + 1):
            try:
                obj, raw, used = llm.llm_plan(question, feedback, self.model_id)
            except Exception as e:  # every model in the fallback chain failed (offline, rate limits)
                trace.append(f"LLM planner failed ({str(e)[:300]}); using rule-based plan.")
                break
            if used != self.model_id:
                trace.append(f"{self.model_id} unavailable; planned with fallback model {used}.")
            self.last_models.append(used)
            if obj is None:
                errs = ["Output was not a JSON object."]
            else:
                obj["source"] = "llm"
                cand, errs = validator.validate_plan(obj, question, expand=False, predictable=self.targets)
            trace.append(f"LLM plan attempt {attempt + 1} ({used}): {raw[:400]}")
            if not errs:
                lp = cand
                break
            trace.append("validator rejected it: " + "; ".join(errs))
            feedback.append((raw, "\n- ".join(errs)))
        if lp is None:
            trace.append("falling back to the rule-based plan.")
            rp.notes.append("The LLM planner could not produce a valid plan; the rule-based parser was used.")
            validator.expand_application(rp, rp.notes)
            return rp, trace

        if self.planner_mode == "hybrid":
            lp = self._merge(lp, rp, trace)
        validator.expand_application(lp, lp.notes)
        return lp, trace

    @staticmethod
    def _merge(lp: QueryPlan, rp: QueryPlan, trace: list[str]) -> QueryPlan:
        """Hybrid: the LLM plan, plus explicit facts the deterministic parser is certain about."""
        if lp.intent in ("knowledge", "out_of_scope") and rp.intent not in ("knowledge", "out_of_scope"):
            trace.append(f"hybrid: LLM said '{lp.intent}' but the question has explicit filters; using rule plan.")
            rp.source = "llm+rules"
            return rp
        added = []
        for c in rp.constraints:
            if not any(x.column == c.column and x.op[0] == c.op[0] and abs(x.value - c.value) < 1e-6
                       for x in lp.constraints):
                lp.constraints.append(c)
                added.append(c.text())
        if not lp.metals and rp.metals:
            lp.metals = rp.metals
            added.append("metals " + "/".join(rp.metals))
        if lp.open_metal_site is None and rp.open_metal_site is not None:
            lp.open_metal_site = rp.open_metal_site
            added.append(f"open_metal_site={rp.open_metal_site}")
        if rp.application and lp.application != rp.application:
            # the rule parser only sets an application on an explicit keyword match ("methane storage"),
            # which is stronger evidence than the LLM's guess
            if lp.application:
                lp.notes.append(f"Application '{lp.application}' from the LLM replaced by '{rp.application}' "
                                f"(explicit keyword in the question).")
            lp.application, lp.gases = rp.application, rp.gases
            added.append(f"application {rp.application}")
        if rp.gases and not lp.gases:
            lp.gases = rp.gases
        if rp.limit_explicit and lp.limit != rp.limit:
            lp.limit = rp.limit
            added.append(f"limit {rp.limit}")
        if not lp.mof_ids and rp.mof_ids:
            lp.mof_ids = rp.mof_ids
            added.append("MOF IDs " + ", ".join(rp.mof_ids))
        if added:
            trace.append("hybrid: added from rule parser -> " + "; ".join(added))
            lp.source = "llm+rules"
        validator._merge_bounds(lp, lp.notes)
        return lp

    # --------------------------------------------------------------- execution
    def execute(self, plan: QueryPlan):
        if plan.intent == "search":
            return tools.search(plan), []
        if plan.intent == "count":
            return tools.aggregate(plan), []
        if plan.intent == "lookup":
            return tools.lookup(plan), []
        if plan.intent == "similar":
            return tools.similar(plan), []
        if plan.intent == "predict":
            target = plan.target_property or self.targets[0]
            preds = []
            if plan.mof_ids:
                rows = db.get_rows(plan.mof_ids[:5])
                for _, r in rows.iterrows():
                    p = predict(target, r.to_dict(), actual=float(r[target]))
                    preds.append(p)
                return tools.ExecResult("lookup", rows, len(rows), method=f"surrogate prediction of {target}"), preds
            preds.append(predict(target, plan.feature_values))
            return None, preds
        return None, []

    # ------------------------------------------------------------------ answer
    def answer(self, question: str) -> AgentResponse:
        t0 = time.time()
        plan, trace = self.plan(question)
        t1 = time.time()
        resp = AgentResponse(question, "", plan, trace=trace, llm_used=self.use_llm)

        if plan.intent in ("knowledge", "out_of_scope"):
            snippets = knowledge.search(question, 4)
            relevant = knowledge.is_relevant(snippets)
            resp.snippets = [s for s in snippets if s.score >= knowledge.RELEVANCE_THRESHOLD] if relevant else []
            if plan.intent == "out_of_scope" or not relevant:
                plan.intent = "out_of_scope"
                resp.answer = ("I can only help with metal-organic frameworks: searching and ranking the 12,020 "
                               "CoRE-MOF structures, finding similar MOFs, predicting surface area or void fraction, "
                               "and explaining MOF concepts. Try e.g. *\"MOFs with surface area > 4000 m²/g and "
                               "density < 0.5\"* or *\"best MOFs for CO2 capture\"*.")
                resp.timings = {"plan": t1 - t0, "total": time.time() - t0}
                resp.models_used = list(dict.fromkeys(self.last_models))
                return resp
        else:
            res, preds = self.execute(plan)
            resp.result, resp.predictions = res, preds
            if res is not None and res.rows is not None and not res.rows.empty:
                rows = res.rows.copy()
                if plan.intent == "search":
                    rows.insert(1, "why", [why_text(r, plan) for _, r in rows.iterrows()])
                resp.table = tools.display_frame(rows, plan)
                if "why" in rows and "why" not in resp.table:
                    resp.table.insert(1, "why", rows["why"])
                if "Surface_Area" in self.targets and plan.intent in ("search", "similar", "lookup"):
                    try:
                        resp.shap = explain_rows("Surface_Area", rows.head(5))
                    except Exception as e:  # models not trained yet
                        trace.append(f"SHAP explanation unavailable: {e}")
            q = question + (" " + APPLICATIONS[plan.application].label if plan.application else "")
            resp.snippets = [s for s in knowledge.search(q, 3) if s.score >= knowledge.RELEVANCE_THRESHOLD]
        t2 = time.time()

        template = self._template_answer(resp)
        if self.use_llm:
            try:
                resp.answer, resp.validation = self._llm_answer(resp, template)
            except Exception as e:
                trace.append(f"LLM answer failed ({e}); using template answer.")
                resp.answer = template
        else:
            resp.answer = template
        resp.timings = {"plan": round(t1 - t0, 3), "execute": round(t2 - t1, 3),
                        "answer": round(time.time() - t2, 3), "total": round(time.time() - t0, 3)}
        resp.models_used = list(dict.fromkeys(self.last_models))
        return resp

    # -------------------------------------------------------------- templates
    def _template_answer(self, r: AgentResponse) -> str:
        p, res = r.plan, r.result
        lines = []
        if p.intent == "knowledge":
            if r.snippets:
                lines.append("From the knowledge base:")
                for i, s in enumerate(r.snippets[:3], 1):
                    text = re.sub(r"^\[[^\]]+\]\s*", "", s.text).replace("\n", " ")
                    lines.append(f"> {text[:420]}{'…' if len(text) > 420 else ''} [{i}]")
            return "\n\n".join(lines)
        if p.intent == "predict":
            for pr in r.predictions:
                if pr.hurdle_applied:
                    lines.append(f"**Predicted {COLUMN_BY_NAME[pr.target].label}: 0 {pr.unit}** - the pore limiting "
                                 f"diameter ({pr.inputs.get('PLD', 0):.2f} Å) is below the 3.31 Å probe, so no "
                                 f"surface is accessible (physics rule, exact on this dataset).")
                    continue
                head = f"**Predicted {COLUMN_BY_NAME[pr.target].label}: {_fmt(pr.target, pr.value)} {pr.unit}** " \
                       f"(90% interval {_fmt(pr.target, pr.low)}–{_fmt(pr.target, pr.high)})"
                if pr.actual is not None:
                    head += f"; database value {_fmt(pr.target, pr.actual)} {pr.unit}"
                lines.append(head)
                top = sorted(pr.contributions.items(), key=lambda kv: -abs(kv[1]))[:3]
                lines.append("Main drivers (SHAP): " + ", ".join(
                    f"{k} = {_fmt(k, pr.inputs[k])} ({'+' if v >= 0 else '−'}{_fmt(pr.target, abs(v))})" for k, v in top))
                if pr.ft_value is not None:
                    lines.append(f"FT-Transformer second opinion: {_fmt(pr.target, pr.ft_value)} {pr.unit}.")
                if pr.imputed:
                    lines.append("Not given, filled with the database median: " + ", ".join(pr.imputed) + ".")
            return "\n\n".join(lines)
        if res is None:
            return "No result."
        if res.kind == "count":
            cond = " AND ".join(c.text() for c in p.constraints) or "no numeric filter"
            extra = (f", metal {'/'.join(p.metals)}" if p.metals else "") + \
                    (f", open metal site = {'yes' if p.open_metal_site else 'no'}" if p.open_metal_site is not None else "")
            if p.aggregate and p.aggregate.get("func") != "count":
                col = p.aggregate["column"]
                v = "n/a" if res.value is None else f"{_fmt(col, res.value)} {unit_of(col)}"
                return f"The {p.aggregate['func']} {COLUMN_BY_NAME[col].label.lower()} over **{res.n_matches}** MOFs " \
                       f"({cond}{extra}) is **{v}**."
            return f"**{res.n_matches}** of 12,020 MOFs match ({cond}{extra})."
        if res.rows is None or res.rows.empty:
            return "No MOF found."
        show = [c.column for c in p.constraints] + [o.column for o in p.objectives]
        show = list(dict.fromkeys(show + ["Surface_Area", "Density", "Void_Fraction"]))[:5]
        if res.kind == "similar":
            ref = res.rows.iloc[0]
            lines.append(f"MOFs most similar to **{ref.MOF_ID}** ({res.method}):")
            body = res.rows.iloc[1:]
        elif res.relaxed:
            lines.append("**No MOF satisfies all of your constraints.** The closest ones are:")
            body = res.rows
        elif res.kind == "lookup":
            body = res.rows
            lines.append("Database values:")
        elif not (p.constraints or p.metals or p.open_metal_site is not None):
            lines.append(f"Ranked all **{res.n_matches:,}** MOFs; top {len(res.rows)} ({res.method}):")
            body = res.rows
        else:
            lines.append(f"**{res.n_matches:,}** MOFs satisfy your request; top {len(res.rows)} ({res.method}):")
            body = res.rows
        for i, (_, row) in enumerate(body.iterrows(), 1):
            vals = ", ".join(f"{c} {_fmt(c, row[c])} {unit_of(c)}".rstrip() for c in show)
            extra = f" - similarity {row['similarity']:.4f}" if "similarity" in row and res.kind == "similar" else ""
            extra += f" - misses: {row['violated']}" if res.relaxed and row.get("violated") else ""
            lines.append(f"{i}. **{row.MOF_ID}** - {vals}{extra}")
        return "\n".join(lines)

    # ---------------------------------------------------------------- LLM text
    def _context(self, r: AgentResponse) -> str:
        p, res = r.plan, r.result
        out = [f"QUESTION: {r.question}", f"PLAN: {p.summary()}"]
        if res is not None:
            out.append(f"METHOD: {res.method}")
            if res.relaxed:
                out.append("IMPORTANT: NO MOF satisfies all constraints. The rows below are the closest matches "
                           "and each one misses at least one constraint - say this clearly.")
            elif res.kind == "rows" and p.constraints:
                out.append("All listed MOFs satisfy every constraint.")
            if res.kind == "similar" and p.mof_ids:
                out.append(f"The first row, {p.mof_ids[0]}, is the MOF the user asked about (similarity 1 to itself, "
                           f"shown for comparison); the other rows are its nearest neighbours. Do not list "
                           f"{p.mof_ids[0]} as a similar MOF.")
        notes = p.notes + (res.notes if res else [])
        if notes:
            out.append("NOTES:\n- " + "\n- ".join(notes))
        if res is not None and res.kind == "count":
            out.append(f"VERIFIED RESULT: {res.n_matches} MOFs match"
                       + (f"; {p.aggregate['func']}({p.aggregate['column']}) = {res.value:.6g}"
                          if p.aggregate and p.aggregate.get('func') != 'count' and res.value is not None else ""))
        if r.table is not None and not r.table.empty:
            t = r.table.head(10).copy()
            cols = [c for c in t.columns if c not in ("why",)][:9]
            hdr = "| " + " | ".join(cols) + " |"
            rows = ["| " + " | ".join(_fmt(c, row[c]) if c != "MOF_ID" else str(row[c]) for c in cols) + " |"
                    for _, row in t.iterrows()]
            n = res.n_matches if res is not None else len(t)
            out.append(f"VERIFIED RESULTS ({n} matching MOFs; showing {len(t)}):\n{hdr}\n" + "\n".join(rows))
            if "why" in t:
                out.append("WHY (percentiles in the 12,020-MOF database):\n" +
                           "\n".join(f"- {row.MOF_ID}: {row.why}" for _, row in t.iterrows()))
        for pr in r.predictions:
            out.append("PREDICTION: " + json.dumps({"target": pr.target, "value": round(pr.value, 4),
                                                    "interval_90": [round(pr.low, 4), round(pr.high, 4)],
                                                    "database_value": pr.actual, "ft_transformer": pr.ft_value,
                                                    "shap": {k: round(v, 3) for k, v in pr.contributions.items()},
                                                    "inputs": pr.inputs, "imputed": pr.imputed,
                                                    "physics_rule_zero": pr.hurdle_applied}))
        if r.snippets:
            out.append("KNOWLEDGE:\n" + "\n".join(f"[{i}] ({s.citation()}) {s.text[:700]}"
                                                  for i, s in enumerate(r.snippets, 1)))
        return "\n\n".join(out)

    def _llm_answer(self, r: AgentResponse, template: str) -> tuple[str, dict]:
        from . import llm
        ctx = self._context(r)
        allowed = validator.allowed_numbers(r.table if r.table is not None else
                                            (r.result.rows if r.result is not None else None), r.plan)
        allowed += validator.query_numbers(r.question)
        if r.result is not None:
            allowed += [float(v) for v in (r.result.n_matches, r.result.value) if v is not None]
        for pr in r.predictions:
            allowed += [0.90, 90.0, pr.base_value]                          # "90 % interval", SHAP base value
            allowed += [pr.value, pr.low, pr.high] + list(pr.contributions.values()) + list(pr.inputs.values())
            allowed += [pr.ft_value] if pr.ft_value is not None else []
            allowed += [pr.actual] if pr.actual is not None else []
        allowed.append(float(len(db.load_materials())))            # "12,020 MOFs"
        if r.table is not None and "why" in r.table:
            for w in r.table["why"]:
                allowed += [v for _, v, _, _ in validator._numbers(w)]
        for s in r.snippets:
            allowed += [v for _, v, _, _ in validator._numbers(s.text)]
        allowed = [a for a in allowed if a is not None]
        rows_for_ids = r.table if r.table is not None else (r.result.rows if r.result is not None else None)
        own = validator.query_numbers(r.question) + ([c.value for c in r.plan.constraints] if r.plan else [])

        def check(t):
            return validator.validate_answer(t, rows_for_ids, allowed, skip_values=own)

        text, used = llm.write_answer(ctx, self.model_id)
        self.last_models.append(used)
        if not self.validate_answers:
            return text, check(text) | {"attempts": 1, "enforced": False}
        v = check(text)
        first = {k: v[k] for k in ("ok", "invalid_ids", "corrected_ids", "unverified_numbers", "false_claims")}
        attempts = 1
        if v["invalid_ids"] or v["unverified_numbers"] or v["false_claims"]:
            problems = []
            if v["invalid_ids"]:
                problems.append("these MOF IDs are not in the verified results: " + ", ".join(v["invalid_ids"]))
            if v["unverified_numbers"]:
                problems.append("these numbers do not appear in the verified data: " + ", ".join(v["unverified_numbers"]))
            if v["false_claims"]:
                problems.append("these comparisons contradict the verified data: " + "; ".join(v["false_claims"]))
            text, used = llm.write_answer(ctx + "\n\nYOUR PREVIOUS ANSWER WAS REJECTED because " + "; ".join(problems)
                                + ". Rewrite it using only the verified values.", self.model_id)
            self.last_models.append(used)
            v = check(text)
            attempts = 2
        final = v["text"]
        if v["corrected_ids"]:
            final += "\n\n_Validator corrected MOF IDs: " + ", ".join(f"{a} → {b}" for a, b in v["corrected_ids"].items()) + "._"
        if v["invalid_ids"] or v["unverified_numbers"]:
            final += ("\n\n⚠️ _Validator: could not verify " +
                      ", ".join(v["invalid_ids"] + v["unverified_numbers"]) +
                      " against the database - rely on the table below._")
        if v["false_claims"]:
            final += ("\n\n⚠️ _Validator: " + "; ".join(v["false_claims"]) +
                      " - rely on the table below._")
        v["attempts"], v["enforced"], v["first_draft"] = attempts, True, first
        return final, v
