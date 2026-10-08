"""
Executor: runs a validated QueryPlan against the database.

The LLM never writes SQL that gets executed. The plan is compiled into a
parameterised query whose column names come only from the whitelist in
config.py and whose values are bound parameters, on a read-only connection.
"""

from __future__ import annotations

from dataclasses import dataclass, field

import numpy as np
import pandas as pd

from . import db, similarity
from .config import COLUMN_BY_NAME, DISPLAY_COLUMNS, NUMERIC_COLUMNS
from .optimizer import nsga2_rank
from .plan import QueryPlan

SQL_OPS = {">": ">", ">=": ">=", "<": "<", "<=": "<=", "==": "="}


@dataclass
class ExecResult:
    kind: str                                   # rows | count | similar | lookup | none
    rows: pd.DataFrame = field(default_factory=pd.DataFrame)
    n_matches: int | None = None                # MOFs satisfying all constraints
    sql: str = ""
    method: str = ""                            # how rows were ranked
    relaxed: bool = False                       # True when no exact match existed and closest MOFs are shown
    value: float | None = None                  # aggregate result
    notes: list[str] = field(default_factory=list)
    candidates: pd.DataFrame | None = None      # full matching set (for Pareto plots)


def compile_where(plan: QueryPlan, use_categorical: bool = True) -> tuple[str, list]:
    clauses, params = [], []
    for c in plan.constraints:
        if c.column not in NUMERIC_COLUMNS or c.op not in SQL_OPS:
            raise ValueError(f"unsafe constraint {c}")       # validator should make this unreachable
        clauses.append(f"{c.column} {SQL_OPS[c.op]} ?")
        params.append(float(c.value))
    if use_categorical and plan.metals:
        clauses.append("MOF_ID IN (SELECT MOF_ID FROM mof_metals WHERE Metal IN (%s))" % ",".join("?" * len(plan.metals)))
        params += list(plan.metals)
    if use_categorical and plan.open_metal_site is not None:
        clauses.append("Has_OMS = ?")
        params.append(int(plan.open_metal_site))
    return (" WHERE " + " AND ".join(clauses)) if clauses else "", params


def render_sql(sql: str, params: list) -> str:
    """Readable SQL for display (parameters inlined) - never executed."""
    out = sql
    for p in params:
        out = out.replace("?", repr(p) if isinstance(p, str) else f"{p:g}", 1)
    return out


def _default_order(plan: QueryPlan) -> tuple[str, str, str]:
    if plan.constraints:
        c = plan.constraints[0]
        return c.column, "DESC" if c.op in (">", ">=") else "ASC", \
            f"sorted by {c.column} ({'highest' if c.op in ('>', '>=') else 'lowest'} first)"
    return "Surface_Area", "DESC", "sorted by surface area (highest first)"


def search(plan: QueryPlan) -> ExecResult:
    where, params = compile_where(plan)
    n = int(db.query_df(f"SELECT COUNT(*) AS n FROM materials{where}", params)["n"].iloc[0])
    if n == 0:
        return closest_matches(plan, f"SELECT * FROM materials{where}", params)
    k = plan.limit
    if len(plan.objectives) >= 2:
        sql = f"SELECT * FROM materials{where}"
        cand = db.query_df(sql, params)
        rows = nsga2_rank(cand, [(o.column, o.direction) for o in plan.objectives], k)
        method = ("NSGA-II selection (non-dominated sorting + crowding distance) over "
                  + ", ".join(o.text() for o in plan.objectives)
                  + "; candidates in the worst 25% of any objective were screened out first")
        return ExecResult("rows", rows, n, render_sql(sql, params), method, candidates=cand)
    if len(plan.objectives) == 1:
        o = plan.objectives[0]
        col, direction, method = o.column, "DESC" if o.direction == "max" else "ASC", f"sorted by {o.text()}"
    else:
        col, direction, method = _default_order(plan)
    sql = f"SELECT * FROM materials{where} ORDER BY {col} {direction}, MOF_ID LIMIT ?"
    rows = db.query_df(sql, params + [k])
    return ExecResult("rows", rows, n, render_sql(sql, params + [k]), method)


def closest_matches(plan: QueryPlan, sql: str, params: list) -> ExecResult:
    """No MOF satisfies everything: rank all MOFs by how far they are from the
    constraints (in robust standard-deviation units) and say so explicitly."""
    df = db.load_materials().copy()
    notes = []
    if plan.metals or plan.open_metal_site is not None:
        w, p = compile_where(QueryPlan(metals=plan.metals, open_metal_site=plan.open_metal_site))
        sub = db.query_df(f"SELECT MOF_ID FROM materials{w}", p)
        if len(sub):
            df = df[df.MOF_ID.isin(set(sub.MOF_ID))]
        else:
            notes.append("No MOF matches the metal/open-metal-site filter either; it was relaxed too.")
    viol = np.zeros(len(df))
    detail = [[] for _ in range(len(df))]
    for c in plan.constraints:
        x = df[c.column].to_numpy(float)
        q75, q25 = np.percentile(df[c.column], [75, 25])
        scale = (q75 - q25) / 1.349 or df[c.column].std() or 1.0
        if c.op in (">", ">="):
            gap = np.maximum(0, c.value - x)
        elif c.op in ("<", "<="):
            gap = np.maximum(0, x - c.value)
        else:
            gap = np.abs(x - c.value)
        viol += gap / scale
        for i in np.flatnonzero(gap > 0):
            detail[i].append(f"{c.column} {x[i]:.4g} (needs {c.op} {c.value:g})")
    df = df.assign(constraint_violation=viol, violated=["; ".join(d) for d in detail])
    rows = df.sort_values(["constraint_violation", "MOF_ID"]).head(plan.limit).reset_index(drop=True)
    notes.insert(0, "No MOF in the database satisfies all constraints. Showing the closest MOFs "
                    "(smallest total violation in robust standard-deviation units).")
    return ExecResult("rows", rows, 0, render_sql(sql, params), "closest matches (constraints relaxed)",
                      relaxed=True, notes=notes)


def aggregate(plan: QueryPlan) -> ExecResult:
    where, params = compile_where(plan)
    func = (plan.aggregate or {}).get("func", "count")
    col = (plan.aggregate or {}).get("column")
    expr = "COUNT(*)" if func == "count" else f"{func.upper()}({col})"
    sql = f"SELECT {expr} AS value, COUNT(*) AS n FROM materials{where}"
    r = db.query_df(sql, params)
    value = r["value"].iloc[0]
    res = ExecResult("count", n_matches=int(r["n"].iloc[0]), sql=render_sql(sql, params),
                     value=None if value is None or pd.isna(value) else float(value), method=func)
    if res.n_matches:
        # show a few example MOFs from the matching set
        order_col = col or (plan.constraints[0].column if plan.constraints else "Surface_Area")
        res.rows = db.query_df(f"SELECT * FROM materials{where} ORDER BY {order_col} DESC LIMIT ?",
                               params + [min(plan.limit, 5)])
    return res


def lookup(plan: QueryPlan) -> ExecResult:
    rows = db.get_rows(plan.mof_ids[: max(plan.limit, len(plan.mof_ids[:10]))])
    return ExecResult("lookup", rows, len(rows), method="exact ID lookup")


def similar(plan: QueryPlan) -> ExecResult:
    ref = plan.mof_ids[0]
    candidates = None
    if plan.constraints or plan.metals or plan.open_metal_site is not None:
        where, params = compile_where(plan)
        candidates = set(db.query_df(f"SELECT MOF_ID FROM materials{where}", params)["MOF_ID"])
    hits = similarity.similar(ref, plan.limit, candidates)
    rows = db.get_rows([ref] + [h for h, _ in hits])
    sim = {h: s for h, s in hits} | {ref: 1.0}
    rows.insert(1, "similarity", rows["MOF_ID"].map(sim))
    how = ("cosine similarity of self-supervised FT-Transformer embeddings"
           if similarity.method() == "ft_embedding" else "cosine similarity of standardised descriptors")
    return ExecResult("similar", rows, len(hits), method=how)


def display_frame(rows: pd.DataFrame, plan: QueryPlan | None = None) -> pd.DataFrame:
    """Order columns: ID, the columns the user asked about, then the defaults."""
    if rows is None or rows.empty:
        return rows
    first = ["MOF_ID"]
    extra = [c for c in ("similarity", "pareto_front", "constraint_violation", "violated") if c in rows]
    asked = []
    if plan is not None:
        asked = [c.column for c in plan.constraints] + [o.column for o in plan.objectives]
    cols = list(dict.fromkeys(first + extra + asked + DISPLAY_COLUMNS))
    cols = [c for c in cols if c in rows.columns]
    return rows[cols]


def describe_columns(cols) -> str:
    return ", ".join(f"{c} ({COLUMN_BY_NAME[c].unit})" for c in cols if c in COLUMN_BY_NAME and COLUMN_BY_NAME[c].unit)
