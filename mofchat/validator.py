"""
Validator - the safety layer between the LLM and the database.

validate_plan()   checks/normalises a plan produced by the LLM or the rule parser:
                  unknown columns, bad operators, non-numeric or physically
                  impossible values, invented MOF IDs, invented thresholds,
                  contradictory constraints. Returns blocking `errors` (fed back to
                  the LLM for self-correction) and user-facing `notes`.
validate_answer() checks the final LLM answer: every MOF ID must exist in the
                  retrieved results and every number must be traceable to the
                  results table, the query or a known constant.
"""

from __future__ import annotations

import re
from functools import lru_cache
from pathlib import Path

import pandas as pd

from . import db
from .config import (APPLICATIONS, COLUMN_BY_NAME, COMMON_NAMES, DEFAULT_LIMIT, GAS_ALIASES, KINETIC_DIAMETERS_A,
                     MAX_LIMIT, NUMERIC_COLUMNS, PROBE_DIAMETER_A, resolve_column)
from .plan import AGG_FUNCS, INTENTS, OPS, Constraint, Objective, QueryPlan

INTENT_SYNONYMS = {
    "filter": "search", "find": "search", "rank": "search", "top": "search", "recommend": "search",
    "recommendation": "search", "query": "search", "select": "search", "optimize": "search",
    "compare": "lookup", "describe": "lookup", "info": "lookup", "details": "lookup", "properties": "lookup",
    "aggregate": "count", "stats": "count", "statistics": "count", "average": "count",
    "similarity": "similar", "neighbors": "similar", "nearest": "similar",
    "prediction": "predict", "estimate": "predict",
    "question": "knowledge", "explain": "knowledge", "general": "knowledge", "chat": "knowledge",
    "definition": "knowledge", "none": "knowledge", "other": "out_of_scope", "irrelevant": "out_of_scope",
}
OP_SYNONYMS = {
    ">": ">", "gt": ">", "greater": ">", "greater than": ">", "above": ">", "more than": ">",
    ">=": ">=", "≥": ">=", "gte": ">=", "ge": ">=", "at least": ">=", "=>": ">=",
    "<": "<", "lt": "<", "less": "<", "less than": "<", "below": "<", "under": "<",
    "<=": "<=", "≤": "<=", "lte": "<=", "le": "<=", "at most": "<=", "=<": "<=",
    "==": "==", "=": "==", "eq": "==", "equal": "==", "equals": "==", "is": "==",
}
DIRECTION_SYNONYMS = {
    "max": "max", "maximize": "max", "maximise": "max", "maximum": "max", "high": "max", "highest": "max",
    "desc": "max", "descending": "max", "largest": "max", "most": "max",
    "min": "min", "minimize": "min", "minimise": "min", "minimum": "min", "low": "min", "lowest": "min",
    "asc": "min", "ascending": "min", "smallest": "min", "least": "min",
}
APPLICATION_SYNONYMS = {
    "co2": "co2_capture", "co2 capture": "co2_capture", "carbon capture": "co2_capture", "co2_capture": "co2_capture",
    "h2": "h2_storage", "hydrogen": "h2_storage", "hydrogen storage": "h2_storage", "h2 storage": "h2_storage",
    "h2_storage": "h2_storage", "ch4": "ch4_storage", "methane": "ch4_storage", "methane storage": "ch4_storage",
    "ch4_storage": "ch4_storage", "natural gas storage": "ch4_storage",
    "separation": "gas_separation", "gas separation": "gas_separation", "gas_separation": "gas_separation",
    "catalysis": "catalysis", "catalyst": "catalysis",
}


# --------------------------------------------------------------------------
# helpers
# --------------------------------------------------------------------------
def _num(v) -> float | None:
    if isinstance(v, bool) or v is None:
        return None
    if isinstance(v, (int, float)):
        return float(v)
    m = re.search(r"-?\d[\d,]*(?:\.\d+)?|-?\.\d+", str(v))
    if not m:
        return None
    x = float(m.group(0).replace(",", ""))
    if re.search(r"\d\s*k\b", str(v).lower()):
        x *= 1000
    return x


def _bool(v) -> bool | None:
    if v is None or v == "" or str(v).lower() in ("none", "null", "any", "either"):
        return None
    if isinstance(v, bool):
        return v
    s = str(v).strip().lower()
    if s in ("1", "true", "yes", "y", "required", "with"):
        return True
    if s in ("0", "false", "no", "n", "without"):
        return False
    return None


def query_numbers(query: str) -> list[float]:
    t = re.sub(r"(\d),(\d{3})", r"\1\2", query.lower())
    nums = []
    for m in re.finditer(r"(?<![a-z\d])(-?\d+(?:\.\d+)?|\.\d+)\s*(k\b)?", t):
        v = float(m.group(1)) * (1000 if m.group(2) else 1)
        nums += [v, v / 100]
    return nums


def _grounded(value: float, query: str) -> bool:
    return any(abs(value - q) <= 1e-6 * max(1.0, abs(q)) for q in query_numbers(query))


# --------------------------------------------------------------------------
# plan validation
# --------------------------------------------------------------------------
def validate_plan(raw: dict | QueryPlan, query: str = "", expand: bool = True,
                  check_grounding: bool | None = None,
                  predictable: tuple[str, ...] = ("Surface_Area",)) -> tuple[QueryPlan, list[str]]:
    d = raw.to_dict() if isinstance(raw, QueryPlan) else dict(raw or {})
    errors: list[str] = []
    notes: list[str] = list(d.get("notes") or [])
    source = d.get("source", "llm")
    if check_grounding is None:
        check_grounding = source != "rules"
    plan = QueryPlan(source=source)

    # intent
    intent = str(d.get("intent") or "search").strip().lower()
    intent = INTENT_SYNONYMS.get(intent, intent)
    if intent not in INTENTS:
        errors.append(f"Unknown intent '{intent}'. Use one of {list(INTENTS)}.")
        intent = "search"
    plan.intent = intent

    # metals / OMS (may also arrive disguised as constraints)
    metals_in = list(d.get("metals") or [])
    oms = _bool(d.get("open_metal_site"))

    # constraints
    for c in d.get("constraints") or []:
        if isinstance(c, Constraint):
            c = {"column": c.column, "op": c.op, "value": c.value}
        if not isinstance(c, dict):
            errors.append(f"Constraint {c!r} is not an object with column/op/value.")
            continue
        col_txt = str(c.get("column", "")).strip()
        if col_txt.lower().replace(" ", "_") in ("metal_type", "metal", "metals"):
            metals_in += [str(c.get("value", ""))]
            continue
        if col_txt.lower().replace(" ", "_") in ("has_oms", "open_metal_site", "oms"):
            oms = _bool(c.get("value"))
            continue
        col = resolve_column(col_txt)
        if col is None:
            errors.append(f"Unknown column '{col_txt}'. Valid numeric columns: {NUMERIC_COLUMNS}.")
            continue
        op_txt = str(c.get("op", "")).strip().lower()
        value = c.get("value")
        if op_txt in DIRECTION_SYNONYMS and _num(value) is None:
            # Common LLM slip: a superlative written as {"op": "min"} with no value -> it is an objective.
            direction = DIRECTION_SYNONYMS[op_txt]
            if col not in [o.column for o in plan.objectives]:
                plan.objectives.append(Objective(col, direction))
            notes.append(f"Repaired plan: '{col} {op_txt}' without a value treated as objective "
                         f"({direction}imise {col}).")
            continue
        if op_txt in ("between", "range", "in") or isinstance(value, (list, tuple)):
            vals = [_num(v) for v in (value if isinstance(value, (list, tuple)) else [])]
            if len(vals) != 2 or None in vals:
                errors.append(f"'between' on {col} needs value [low, high], got {value!r}.")
                continue
            pairs = [(">=", min(vals)), ("<=", max(vals))]
        else:
            op = OP_SYNONYMS.get(op_txt)
            if op is None:
                errors.append(f"Unknown operator '{op_txt}' for {col}. Use one of {list(OPS)} or 'between'.")
                continue
            v = _num(value)
            if v is None:
                errors.append(f"Value for {col} must be a number, got {value!r}.")
                continue
            pairs = [(op, v)]
        for op, v in pairs:
            if col == "Void_Fraction" and 1.0 < v <= 100.0:
                notes.append(f"Interpreted void fraction {v:g} as {v / 100:g} (percent -> fraction).")
                v = v / 100
            lo, hi = COLUMN_BY_NAME[col].valid_range or (float("-inf"), float("inf"))
            if not (lo <= v <= hi):
                msg = (f"{col} {op} {v:g} is outside the physically plausible range "
                       f"[{lo:g}, {hi:g}] {COLUMN_BY_NAME[col].unit}.")
                if check_grounding and not _grounded(v, query):
                    errors.append(msg)           # the planner invented an impossible value
                    continue
                notes.append(msg + " No real MOF can satisfy it; the closest MOFs will be shown.")
            if check_grounding and not _grounded(v, query):
                notes.append(f"The planner proposed '{col} {op} {v:g}', but that number is not in your question; "
                             f"treated it as a preference ({'maximise' if op in ('>', '>=') else 'minimise'} {col}).")
                plan.objectives.append(Objective(col, "max" if op in (">", ">=") else "min"))
                continue
            plan.constraints.append(Constraint(col, op, float(v)))

    # objectives
    for o in d.get("objectives") or []:
        if isinstance(o, Objective):
            o = {"column": o.column, "direction": o.direction}
        if isinstance(o, str):
            o = {"column": o, "direction": "max"}
        col = resolve_column(str(o.get("column", "")))
        if col is None:
            errors.append(f"Unknown objective column '{o.get('column')}'. Valid: {NUMERIC_COLUMNS}.")
            continue
        direction = DIRECTION_SYNONYMS.get(str(o.get("direction", "max")).lower())
        if direction is None:
            errors.append(f"Objective direction for {col} must be 'max' or 'min'.")
            continue
        if col not in [x.column for x in plan.objectives]:
            plan.objectives.append(Objective(col, direction))

    # metals
    for m in metals_in:
        for tok in re.split(r"[,/;\s]+|\band\b|\bor\b", str(m)):
            if not tok.strip():
                continue
            sym = db.resolve_metal(tok.replace("-based", ""))
            if sym is None:
                notes.append(f"Metal '{tok}' is not present in the database; ignored.")
            elif sym not in plan.metals:
                plan.metals.append(sym)
    plan.open_metal_site = oms

    # application + gases
    app = d.get("application")
    if app:
        key = APPLICATION_SYNONYMS.get(str(app).strip().lower(), str(app).strip().lower())
        if key in APPLICATIONS:
            plan.application = key
        else:
            notes.append(f"Application '{app}' has no screening preset; ignored.")
    for g in d.get("gases") or []:
        gg = GAS_ALIASES.get(str(g).strip().lower()) or (str(g) if str(g) in KINETIC_DIAMETERS_A else None)
        if gg and gg not in plan.gases:
            plan.gases.append(gg)

    # MOF IDs: must resolve in the DB and be grounded in the query text
    ql = query.lower()
    for i in d.get("mof_ids") or []:
        found = db.resolve_mof_id(str(i))
        if not found:
            notes.append(f"MOF '{i}' is not in the CoRE-MOF table.")
            continue
        mentioned = (str(i).lower() in ql or any(f.lower() in ql for f in found)
                     or any(name in ql and code in [f[:6] for f in found] for name, code in COMMON_NAMES.items()))
        if check_grounding and query and not mentioned:
            notes.append(f"Ignored MOF '{i}' proposed by the planner (not mentioned in your question).")
            continue
        for f in found:
            if f not in plan.mof_ids:
                plan.mof_ids.append(f)

    # aggregate
    agg = d.get("aggregate")
    if agg:
        func = str(agg.get("func", "count")).lower() if isinstance(agg, dict) else str(agg).lower()
        func = {"mean": "avg", "average": "avg", "maximum": "max", "minimum": "min", "number": "count"}.get(func, func)
        col = resolve_column(str(agg.get("column"))) if isinstance(agg, dict) and agg.get("column") else None
        if func not in AGG_FUNCS:
            errors.append(f"Aggregate function '{func}' not supported; use {list(AGG_FUNCS)}.")
        elif func != "count" and col is None:
            errors.append(f"Aggregate '{func}' needs a numeric column.")
        else:
            plan.aggregate = {"func": func, "column": col}
    if plan.intent == "count" and not plan.aggregate:
        plan.aggregate = {"func": "count", "column": None}

    # predict
    if d.get("target_property"):
        tp = resolve_column(str(d["target_property"]))
        if tp in predictable:
            plan.target_property = tp
        else:
            notes.append(f"Prediction of '{d['target_property']}' is not available; "
                         f"supported: {', '.join(predictable)}.")
            plan.target_property = predictable[0]
    for k, v in (d.get("feature_values") or {}).items():
        col, val = resolve_column(str(k)), _num(v)
        if col and val is not None:
            if col == "Void_Fraction" and 1.0 < val <= 100.0:
                val /= 100
            plan.feature_values[col] = val
    if plan.intent == "predict" and not plan.target_property:
        plan.target_property = predictable[0]

    # limit
    try:
        lim = int(d.get("limit") or DEFAULT_LIMIT)
    except (TypeError, ValueError):
        lim = DEFAULT_LIMIT
    if lim > MAX_LIMIT:
        notes.append(f"Limited the result list to {MAX_LIMIT} MOFs.")
    plan.limit = max(1, min(MAX_LIMIT, lim))
    plan.limit_explicit = bool(d.get("limit_explicit", False))

    # intent consistency
    if plan.intent in ("lookup", "similar") and not plan.mof_ids:
        if plan.constraints or plan.objectives:
            plan.intent = "search"
        else:
            errors.append(f"Intent '{plan.intent}' needs a MOF ID from the question (e.g. ABAVIJ), none found.")
    if plan.intent == "predict" and not plan.mof_ids and not plan.feature_values:
        errors.append("Prediction needs a MOF ID or descriptor values (e.g. density 0.5, void fraction 0.8).")
    if plan.intent == "search" and not (plan.constraints or plan.objectives or plan.metals or plan.application
                                        or plan.open_metal_site is not None):
        plan.intent = "knowledge"

    _merge_bounds(plan, notes)
    if expand:
        expand_application(plan, notes)
    plan.notes = list(dict.fromkeys(notes))
    return plan, errors


def _merge_bounds(plan: QueryPlan, notes: list[str]) -> None:
    """Keep the tightest lower/upper bound per column and flag contradictions."""
    lower, upper, other = {}, {}, []
    for c in plan.constraints:
        if c.op in (">", ">="):
            cur = lower.get(c.column)
            if cur is None or c.value > cur.value or (c.value == cur.value and c.op == ">"):
                lower[c.column] = c
        elif c.op in ("<", "<="):
            cur = upper.get(c.column)
            if cur is None or c.value < cur.value or (c.value == cur.value and c.op == "<"):
                upper[c.column] = c
        else:
            other.append(c)
    merged = list(lower.values()) + list(upper.values()) + other
    for col in set(lower) & set(upper):
        if lower[col].value > upper[col].value or (lower[col].value == upper[col].value and
                                                   "=" not in lower[col].op + upper[col].op):
            notes.append(f"Contradictory bounds on {col} ({lower[col].text()} and {upper[col].text()}): "
                         f"no MOF can satisfy both.")
    order = {id(c): i for i, c in enumerate(plan.constraints)}
    plan.constraints = sorted(merged, key=lambda c: order.get(id(c), 0))


def expand_application(plan: QueryPlan, notes: list[str]) -> None:
    """Turn an application keyword into transparent screening constraints/objectives."""
    if not plan.application:
        return
    preset = APPLICATIONS[plan.application]
    explicit_cols = {c.column for c in plan.constraints}
    added = []
    if plan.application == "gas_separation":
        gases = plan.gases[:2]
        if len(gases) < 2:
            notes.append("For size-based separation screening please name two gases (e.g. CO2/N2); "
                         "no sieving window was applied.")
            return
        d1, d2 = sorted(KINETIC_DIAMETERS_A[g] for g in gases)
        if "PLD" not in explicit_cols:
            plan.constraints += [Constraint("PLD", ">=", d1), Constraint("PLD", "<=", d2)]
            added.append(f"{d1:g} Å <= PLD <= {d2:g} Å")
        if not plan.objectives:
            plan.objectives = [Objective("Void_Fraction", "max")]
            added.append("maximise Void_Fraction")
        notes.append(f"Separation of {gases[0]}/{gases[1]}: {preset.rationale} Applied: " + "; ".join(added) + ".")
        return
    for col, op, v in preset.constraints:
        if col not in explicit_cols:
            plan.constraints.append(Constraint(col, op, v))
            added.append(f"{col} {op} {v:g}")
    if not plan.objectives:
        plan.objectives = [Objective(c, dr) for c, dr in preset.objectives]
        added += [f"{dr}imise {c}" for c, dr in preset.objectives]
    if plan.open_metal_site is None and preset.open_metal_site is not None:
        plan.open_metal_site = preset.open_metal_site
        added.append("open metal site required")
    if added:
        notes.append(f"{preset.label} screening heuristic - {preset.rationale} Applied: " + "; ".join(added) + ".")


# --------------------------------------------------------------------------
# answer validation
# --------------------------------------------------------------------------
STOP_TOKENS = {"MOF", "MOFS", "SQL", "NSGA", "SHAP", "CSD", "CORE", "RAG", "LLM", "FAISS", "BET", "GCMC", "DOE",
               "XGBOOST", "PARETO", "NOTE", "IMPORTANT", "CAVEAT", "WARNING", "SUMMARY", "ZEOPP", "OMS", "LCD",
               "PLD", "LFPD", "ASA", "NASA", "NAV", "BTC", "HKUST", "IRMOF", "UIO", "ZIF", "MIL", "COREMOF",
               "CHATMOF", "MOFCHAT", "SQLITE", "TRUE", "FALSE", "YES", "NONE", "METHANE", "HYDROGEN",
               # section headers of the answer-writer prompt
               "QUESTION", "PLAN", "METHOD", "NOTES", "VERIFIED", "RESULTS", "RESULT", "KNOWLEDGE", "PREDICTION",
               "WHY", "IMPORTANT"}


def _is_word(tok: str) -> bool:
    w = tok.lower()
    words = _english_words()
    return w in words or (w.endswith("s") and w[:-1] in words) or (w.endswith("es") and w[:-2] in words)


@lru_cache(maxsize=1)
def _english_words() -> frozenset[str]:
    p = Path("/usr/share/dict/words")
    try:
        return frozenset(w.strip().lower() for w in p.read_text().splitlines())
    except OSError:
        return frozenset()


def _levenshtein(a: str, b: str) -> int:
    prev = list(range(len(b) + 1))
    for i, ca in enumerate(a, 1):
        cur = [i]
        for j, cb in enumerate(b, 1):
            cur.append(min(prev[j] + 1, cur[j - 1] + 1, prev[j - 1] + (ca != cb)))
        prev = cur
    return prev[-1]


def _id_candidates(text: str) -> list[str]:
    out = []
    for tok in re.findall(r"[A-Za-z0-9][A-Za-z0-9_.\-]*[A-Za-z0-9]", text):
        tok = tok.strip(".-")
        if tok.upper() in db.id_index():
            out.append(tok)
        elif re.fullmatch(r"[A-Z]{5,8}\d{0,2}", tok) and tok not in STOP_TOKENS and not _is_word(tok):
            out.append(tok)
        elif "_" in tok and re.search(r"\d", tok) and re.search(r"[a-z]", tok):
            out.append(tok)
    return list(dict.fromkeys(out))


def _numbers(text: str) -> list[tuple[str, float, int, bool]]:
    """(raw text, value, decimals, is_percent) for every number in the text."""
    out = []
    for m in re.finditer(r"(?<![\w.\-])(-?\d{1,3}(?:,\d{3})+(?:\.\d+)?|-?\d+(?:\.\d+)?)(?![\w])(\s*%)?", text):
        s = m.group(1)
        v = float(s.replace(",", ""))
        dec = len(s.split(".")[1]) if "." in s else 0
        out.append((m.group(0).strip(), v, dec, bool(m.group(2))))
    return out


def allowed_numbers(results: pd.DataFrame | None, plan: QueryPlan | None, extra: list[float] = ()) -> list[float]:
    vals: list[float] = list(extra) + list(KINETIC_DIAMETERS_A.values()) + [PROBE_DIAMETER_A]
    if results is not None and not results.empty:
        for c in results.columns:
            if pd.api.types.is_numeric_dtype(results[c]):
                vals += [float(x) for x in results[c].dropna().tolist()]
        vals.append(float(len(results)))
    if plan is not None:
        vals += [c.value for c in plan.constraints] + [float(plan.limit)]
        vals += list(plan.feature_values.values())
    return vals


def _matches(v: float, dec: int, allowed: list[float]) -> bool:
    tol_round = 0.5 * 10 ** (-dec) + 1e-9
    for a in allowed:
        if abs(v - a) <= tol_round or abs(v - a) <= 0.01 * abs(a):
            return True
    return False


def validate_answer(text: str, results: pd.DataFrame | None, allowed: list[float]) -> dict:
    result_ids = list(results["MOF_ID"]) if results is not None and "MOF_ID" in results else []
    rid_upper = {r.upper(): r for r in result_ids}
    idx = db.id_index()
    invalid, corrected, unretrieved = [], {}, []
    for tok in _id_candidates(text):
        up = tok.upper()
        if up in rid_upper:
            continue
        if up in idx:
            unretrieved.append(idx[up])
            continue
        best = min(result_ids, key=lambda r: _levenshtein(up, r.upper()), default=None)
        if best is not None and _levenshtein(up, best.upper()) <= 2:
            corrected[tok] = best
        else:
            invalid.append(tok)
    unverified = []
    for raw, v, dec, pct in _numbers(text):
        if float(v).is_integer() and abs(v) <= 20 and not pct:
            continue                    # list numbering, small counts
        if 1900 <= v <= 2100 and dec == 0:
            continue                    # years
        ok = _matches(v, dec, allowed) or (pct and _matches(v / 100, dec + 2, allowed))
        if not ok:
            unverified.append(raw)
    fixed = text
    for bad, good in corrected.items():
        fixed = re.sub(rf"(?<![A-Za-z0-9_]){re.escape(bad)}(?![A-Za-z0-9_])", good, fixed)
    return {
        "ok": not (invalid or corrected or unverified),
        "invalid_ids": invalid,
        "corrected_ids": corrected,
        "unretrieved_ids": unretrieved,
        "unverified_numbers": list(dict.fromkeys(unverified)),
        "text": fixed,
    }
