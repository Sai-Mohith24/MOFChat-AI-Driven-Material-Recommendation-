"""Unit tests for the deterministic parts of MOFChat (no LLM needed).

    venv/bin/python -m pytest -q
"""

import sqlite3

import numpy as np
import pandas as pd
import pytest

import mofchat  # noqa: F401
from mofchat import db, rules, tools, validator
from mofchat.optimizer import _dominated_mask, crowding_distance, non_dominated_fronts, nsga2_rank
from mofchat.plan import Constraint, QueryPlan


# ----------------------------------------------------------------- database
def test_database_schema_and_size():
    df = db.load_materials()
    assert len(df) == 12020
    assert df.MOF_ID.is_unique
    for col in ["Surface_Area", "Density", "Void_Fraction", "Pore_Volume", "LCD", "PLD", "LFPD", "Has_OMS"]:
        assert col in df
    # physics facts the system relies on
    assert ((df.PLD < 3.31) == (df.Surface_Area == 0)).mean() > 0.999
    assert np.allclose(df.Pore_Volume, df.Void_Fraction / df.Density, rtol=1e-4)


def test_database_is_read_only():
    conn = db.connect()
    with pytest.raises(sqlite3.OperationalError):
        conn.execute("DELETE FROM materials")
    conn.close()


def test_metal_table_handles_multi_metal_mofs():
    m = db.query_df("SELECT * FROM mof_metals WHERE MOF_ID IN (SELECT MOF_ID FROM materials WHERE Metal_Type LIKE '%,%') LIMIT 50")
    assert m.groupby("MOF_ID").size().max() >= 2


def test_common_names_resolve():
    assert db.resolve_mof_id("HKUST-1") == ["FIQCEN"]
    assert db.resolve_mof_id("zif-8") == ["OFERUN"]
    assert db.resolve_mof_id("RUBTAK")[0].startswith("RUBTAK")
    assert db.resolve_mof_id("MOF-5") == []


# ------------------------------------------------------------------- parser
@pytest.mark.parametrize("q, cons, objs, limit", [
    ("Find me 3 MOFs with a surface area greater than 4000 and a void fraction greater than 0.8",
     {("Surface_Area", ">", 4000), ("Void_Fraction", ">", 0.8)}, [], 3),
    ("MOFs with surface area > 4,000 m2/g, density < 0.5 and void fraction >= 85%",
     {("Surface_Area", ">", 4000), ("Density", "<", 0.5), ("Void_Fraction", ">=", 0.85)}, [], 5),
    ("pore limiting diameter between 4 and 6 Å", {("PLD", ">=", 4), ("PLD", "<=", 6)}, [], 5),
    ("MOFs with a PLD larger than 3.3 Å but smaller than 3.64 Å", {("PLD", ">", 3.3), ("PLD", "<", 3.64)}, [], 5),
    ("surface area 3000 m2/g or more and density below 0.6",
     {("Surface_Area", ">=", 3000), ("Density", "<", 0.6)}, [], 5),
    ("Which MOF has the lowest density?", set(), [("Density", "min")], 1),
    ("MOFs with very LOW surface area and HIGH density", set(), [("Surface_Area", "min"), ("Density", "max")], 5),
    ("top 10 lightest MOFs with porosity above 80%", {("Void_Fraction", ">", 0.8)}, [("Density", "min")], 10),
])
def test_rule_parser_numeric(q, cons, objs, limit):
    p = rules.parse(q)
    assert {(c.column, c.op, round(c.value, 6)) for c in p.constraints} == cons
    assert [(o.column, o.direction) for o in p.objectives] == objs
    assert p.limit == limit


def test_rule_parser_categorical_and_intents():
    p = rules.parse("Show Cu-based MOFs with open metal sites")
    assert p.metals == ["Cu"] and p.open_metal_site is True
    assert rules.parse("MOFs without open metal sites with LCD of at least 20 Å").open_metal_site is False
    assert rules.parse("How many MOFs have a density below 0.3?").intent == "count"
    assert rules.parse("Find MOFs similar to ABAVIJ").intent == "similar"
    assert rules.parse("Tell me about HKUST-1").mof_ids == ["FIQCEN"]
    assert rules.parse("What is void fraction?").intent == "knowledge"
    assert rules.parse("recipe for chocolate cake").intent == "knowledge"
    sep = rules.parse("MOFs to separate CO2 from N2")
    assert sep.application == "gas_separation" and sep.gases == ["CO2", "N2"]
    # "In" at the start of a sentence is not indium
    assert rules.parse("In MOFs with density at most 0.3, which has the largest pore volume?").metals == []


# ---------------------------------------------------------------- validator
def test_validator_rejects_unknown_column_and_bad_values():
    _, errs = validator.validate_plan({"intent": "search", "constraints": [
        {"column": "melting_point", "op": ">", "value": 300}]}, "melting point above 300")
    assert any("Unknown column" in e for e in errs)
    _, errs = validator.validate_plan({"intent": "search", "constraints": [
        {"column": "Density", "op": ">", "value": "abc"}]}, "density above abc")
    assert errs
    # impossible value invented by the planner -> error; typed by the user -> kept with a note
    _, errs = validator.validate_plan({"intent": "search", "constraints": [
        {"column": "Void_Fraction", "op": ">", "value": 250}]}, "very porous MOFs")
    assert any("outside" in e for e in errs)
    p, errs = validator.validate_plan({"intent": "search", "constraints": [
        {"column": "Surface_Area", "op": ">", "value": 20000}]}, "surface area above 20000")
    assert not errs and p.constraints and any("No real MOF" in n for n in p.notes)


def test_validator_percent_alias_and_grounding():
    p, errs = validator.validate_plan({"intent": "search", "constraints": [
        {"column": "porosity", "op": "greater", "value": 80}]}, "porosity greater than 80%")
    assert not errs and p.constraints[0].column == "Void_Fraction" and p.constraints[0].value == pytest.approx(0.8)
    # LLM invents a threshold that is not in the question -> becomes a preference
    p, errs = validator.validate_plan({"intent": "search", "constraints": [
        {"column": "Surface_Area", "op": ">", "value": 3000}]}, "MOFs with high surface area")
    assert not p.constraints and p.objectives[0].column == "Surface_Area"
    # LLM invents a MOF ID -> dropped
    p, _ = validator.validate_plan({"intent": "lookup", "mof_ids": ["ABAVIJ", "FIQCEN"]}, "tell me about ABAVIJ")
    assert p.mof_ids == ["ABAVIJ"]


def test_validator_contradiction_and_application_expansion():
    p, _ = validator.validate_plan({"intent": "search", "constraints": [
        {"column": "Density", "op": ">", "value": 2}, {"column": "Density", "op": "<", "value": 1}]},
        "density above 2 and below 1")
    assert any("Contradictory" in n for n in p.notes)
    p, _ = validator.validate_plan({"intent": "search", "application": "co2 capture"}, "MOFs for CO2 capture")
    assert p.open_metal_site is True and any(c.column == "PLD" for c in p.constraints)
    p, _ = validator.validate_plan({"intent": "search", "application": "separation", "gases": ["CO2", "methane"]},
                                   "separate CO2 and methane")
    assert {(c.op, c.value) for c in p.constraints if c.column == "PLD"} == {(">=", 3.30), ("<=", 3.80)}


def test_validator_drops_objectives_not_in_application_question():
    # GPT-OSS 20B planned "Best MOFs for CO2 capture" with its own objectives, which replaced the preset
    raw = {"intent": "search", "application": "co2_capture",
           "objectives": [{"column": "Surface_Area", "direction": "max"}, {"column": "Void_Fraction", "direction": "max"}]}
    p, _ = validator.validate_plan(raw, "Best MOFs for CO2 capture")
    assert [(o.column, o.direction) for o in p.objectives] == [("ASA_vol", "max"), ("LCD", "min")]
    p, _ = validator.validate_plan(raw, "CO2 capture MOFs with the highest surface areas")
    assert [o.column for o in p.objectives] == ["Surface_Area"]       # the user asked for this one
    p, _ = validator.validate_plan(dict(raw, source="rules"), "Best MOFs for CO2 capture")
    assert len(p.objectives) == 2                                        # rule plans are not grounding-checked


def test_answer_validator_catches_garbled_id_and_numbers():
    rows = db.get_rows(["ACOCOM", "ACOCUS", "ACODAZ"])
    allowed = validator.allowed_numbers(rows, None)
    text = "I found ACOCOM, ACOCLUS and ACODAZ. ACOCUS has a surface area of 4382.42 m2/g and 9999.5 m2/g."
    v = validator.validate_answer(text, rows, allowed)
    assert v["corrected_ids"] == {"ACOCLUS": "ACOCUS"}
    assert "9999.5" in v["unverified_numbers"] and "4382.42" not in v["unverified_numbers"]
    assert "ACOCLUS" not in v["text"]
    ok = validator.validate_answer("ACOCOM has a surface area of 4,394 m²/g and void fraction 0.86.", rows, allowed)
    assert ok["ok"]
    # GPT-OSS writes thousands with a narrow no-break space ("4\u202f394"); that is one number, not "394"
    assert validator.validate_answer("ACOCOM has a surface area of 4\u202f394 m²/g.", rows, allowed)["ok"]


def test_answer_validator_catches_false_comparison_claims():
    # GPT-OSS 20B wrote this for "Zinc MOFs with high surface area and low density": every number
    # matches something in the results, but UHUPOD01 has 4,564 m²/g, not >= 6000.
    rows = db.get_rows(["acscombsci.5b00188_5036495", "UHUPOD01", "RUTNOK"])
    allowed = validator.allowed_numbers(rows, None)
    bad = validator.validate_answer(
        "The remaining three (acscombsci.5b00188_5036495, UHUPOD01, RUTNOK) still offer high surface areas "
        "(≥ 6000 m²/g) with relatively low densities (≤ 0.34 g/cm³).", rows, allowed)
    assert not bad["ok"] and len(bad["false_claims"]) == 1 and "UHUPOD01" in bad["false_claims"][0]
    for text in ("All three have surface areas above 4,500 m²/g and densities below 0.35 g/cm³.",
                 "No MOF has a surface area above 20,000 m²/g; the closest are UHUPOD01 and RUTNOK.",
                 "MOFs with PLD below 3.31 Å have zero surface area, so these were excluded.",
                 "RUTNOK has a void fraction above 80%."):
        assert validator.validate_answer(text, rows, allowed)["false_claims"] == [], text
    # restating the user's own (impossible) threshold next to the closest matches is not a claim
    assert validator.validate_answer("The closest MOFs to surface area > 20000 m²/g are UHUPOD01 and RUTNOK.",
                                     rows, allowed + [20000.0], skip_values=[20000.0])["ok"]
    # Pareto-front claims are checked against the NSGA-II ranks
    ranked = rows.assign(pareto_front=[1, 2, 2])
    v = validator.validate_answer("acscombsci.5b00188_5036495 and UHUPOD01 are on the first Pareto front.", ranked, allowed)
    assert v["false_claims"] == ['"first Pareto front" is false for UHUPOD01 (Pareto front 2)']
    assert validator.validate_answer("They lie on Pareto front 1 (except the last two on front 2).",
                                     ranked, allowed)["false_claims"] == []


# -------------------------------------------------------------------- tools
def test_search_matches_pandas_ground_truth():
    plan, _ = validator.validate_plan(rules.parse(
        "MOFs with surface area greater than 4000 and void fraction greater than 0.8"), "", check_grounding=False)
    plan.limit = 50
    res = tools.search(plan)
    df = db.load_materials()
    gt = df[(df.Surface_Area > 4000) & (df.Void_Fraction > 0.8)]
    assert res.n_matches == len(gt) == 206
    assert set(res.rows.MOF_ID) <= set(gt.MOF_ID)
    assert res.rows.Surface_Area.is_monotonic_decreasing


def test_sql_values_are_parameters_not_code():
    plan = QueryPlan(intent="search", metals=["Cu'); DROP TABLE materials; --"])
    where, params = tools.compile_where(plan)
    assert "DROP" not in where and any("DROP" in str(p) for p in params)
    with pytest.raises(ValueError):
        tools.compile_where(QueryPlan(constraints=[Constraint("Density; DROP TABLE materials", ">", 1)]))


def test_impossible_query_returns_closest_and_says_so():
    res = tools.search(QueryPlan(constraints=[Constraint("Surface_Area", ">", 20000)], limit=3))
    assert res.relaxed and res.n_matches == 0
    assert res.rows.iloc[0].MOF_ID == "c6ce00407e_c6ce00407e5"


def test_count_and_average():
    res = tools.aggregate(QueryPlan(intent="count", constraints=[Constraint("Surface_Area", ">", 5000)],
                                    aggregate={"func": "count", "column": None}))
    assert res.n_matches == 112
    res = tools.aggregate(QueryPlan(intent="count", metals=["Zr"], aggregate={"func": "avg", "column": "Density"}))
    df = db.load_materials()
    zr = db.query_df("SELECT MOF_ID FROM mof_metals WHERE Metal='Zr'").MOF_ID
    assert res.value == pytest.approx(df[df.MOF_ID.isin(zr)].Density.mean())


# ---------------------------------------------------------------- optimizer
@pytest.mark.parametrize("m", [2, 3])
def test_non_dominated_sort_matches_brute_force(m):
    rng = np.random.default_rng(1)
    F = rng.random((600, m))
    F[::5] = F[::5].round(1)          # ties and duplicates
    fronts = non_dominated_fronts(F)
    assert sum(len(f) for f in fronts) == len(F)
    remaining = np.ones(len(F), bool)
    for f in fronts:
        brute = set(np.flatnonzero(remaining & ~_dominated_mask(F, remaining)))
        assert set(f) == brute
        remaining[f] = False


def test_crowding_and_nsga2_rank():
    F = np.array([[0, 1], [0.5, 0.5], [1, 0], [0.1, 0.9]])
    cd = crowding_distance(F)
    assert np.isinf(cd[0]) and np.isinf(cd[2])
    df = pd.DataFrame({"MOF_ID": list("abcdef"), "x": [1, 2, 3, 4, 5, 0], "y": [5, 4, 3, 2, 1, 0]})
    top = nsga2_rank(df, [("x", "max"), ("y", "max")], 3, floor_quantile=0)
    assert (top.pareto_front == 1).all() and "f" not in set(top.MOF_ID)


def test_validator_repairs_superlative_written_as_constraint():
    # Llama 3 often writes "lowest density" as {"op": "min"} without a value
    p, errs = validator.validate_plan({"intent": "search", "constraints": [{"column": "Density", "op": "min"}],
                                       "limit": 1}, "Which MOF has the lowest density?")
    assert not errs and not p.constraints and [(o.column, o.direction) for o in p.objectives] == [("Density", "min")]


def test_hybrid_merge_prefers_explicit_application_keyword():
    from mofchat.agent import MOFChatAgent
    q = "Suggest 3 MOFs for methane storage"
    llm_plan, _ = validator.validate_plan({"intent": "search", "application": "h2_storage", "limit": 3}, q, expand=False)
    rule_plan, _ = validator.validate_plan(rules.parse(q), q, expand=False)
    merged = MOFChatAgent._merge(llm_plan, rule_plan, [])
    assert merged.application == "ch4_storage" and merged.limit == 3
