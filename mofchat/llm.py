"""Llama 3 (Ollama) planner and answer writer."""

from __future__ import annotations

import json
from functools import lru_cache

import httpx

from .config import APPLICATIONS, COLUMNS, LLM_MODEL, OLLAMA_URL

PLANNER_SYSTEM = """You translate questions about a database of 12,020 metal-organic frameworks (MOFs) into a JSON query plan.
Return ONLY one JSON object with these keys:
  "intent": one of "search" (find/rank MOFs), "similar" (MOFs similar to a named MOF), "lookup" (properties of named MOFs / compare named MOFs),
            "count" (how many / average of a property), "predict" (predict a property), "knowledge" (conceptual question, no database query),
            "out_of_scope" (not about MOFs or materials)
  "constraints": list of {"column": <numeric column>, "op": one of ">", ">=", "<", "<=", "between", "value": number or [low, high]}
  "objectives": list of {"column": <numeric column>, "direction": "max" or "min"}
  "metals": list of element symbols, e.g. ["Cu", "Zn"]
  "open_metal_site": true, false or null
  "application": one of APPLICATIONS or null
  "gases": list of gas formulas for separations, e.g. ["CO2", "N2"]
  "mof_ids": list of MOF IDs exactly as written in the question
  "aggregate": null or {"func": "count" | "avg" | "min" | "max", "column": <numeric column or null>}
  "target_property": column to predict (only for intent "predict")
  "feature_values": {column: number} given in the question (only for intent "predict")
  "limit": number of MOFs requested (default 5; 1 when the question asks for "the MOF" / "which MOF has the highest ...")

Numeric columns (name: unit - meaning):
COLUMNS

RULES
1. Add a constraint ONLY when the question states a number. Words like high, low, large, lightest, best are objectives, never constraints.
2. Void fraction is a number between 0 and 1: "80%" means 0.8.
3. "pore size"/"pore diameter" means LCD; "pore aperture"/"window"/"PLD" means PLD; "porosity" means Void_Fraction; "surface area" means Surface_Area (m2/g).
4. Never invent MOF IDs, numbers or columns. Use null or [] when something is not mentioned.
5. Applications (APPLICATIONS) only when the question names that use.
"""

EXAMPLES = [
    ("Find 3 MOFs with surface area above 4000 m2/g and void fraction over 80%",
     {"intent": "search", "constraints": [{"column": "Surface_Area", "op": ">", "value": 4000},
                                          {"column": "Void_Fraction", "op": ">", "value": 0.8}],
      "objectives": [], "metals": [], "open_metal_site": None, "application": None, "gases": [], "mof_ids": [],
      "aggregate": None, "limit": 3}),
    ("Which zinc MOF has the highest surface area while being as light as possible?",
     {"intent": "search", "constraints": [], "objectives": [{"column": "Surface_Area", "direction": "max"},
                                                            {"column": "Density", "direction": "min"}],
      "metals": ["Zn"], "open_metal_site": None, "application": None, "gases": [], "mof_ids": [],
      "aggregate": None, "limit": 1}),
    ("Cu MOFs with open metal sites and a pore limiting diameter between 4 and 6 angstrom",
     {"intent": "search", "constraints": [{"column": "PLD", "op": "between", "value": [4, 6]}], "objectives": [],
      "metals": ["Cu"], "open_metal_site": True, "application": None, "gases": [], "mof_ids": [],
      "aggregate": None, "limit": 5}),
    ("Recommend MOFs for CO2 capture", {"intent": "search", "constraints": [], "objectives": [], "metals": [],
                                        "open_metal_site": None, "application": "co2_capture", "gases": [],
                                        "mof_ids": [], "aggregate": None, "limit": 5}),
    ("Which MOFs could separate CO2 from CH4?", {"intent": "search", "constraints": [], "objectives": [],
                                                 "metals": [], "open_metal_site": None,
                                                 "application": "gas_separation", "gases": ["CO2", "CH4"],
                                                 "mof_ids": [], "aggregate": None, "limit": 5}),
    ("How many MOFs have a density below 0.5?",
     {"intent": "count", "constraints": [{"column": "Density", "op": "<", "value": 0.5}], "objectives": [],
      "metals": [], "open_metal_site": None, "application": None, "gases": [], "mof_ids": [],
      "aggregate": {"func": "count", "column": None}, "limit": 5}),
    ("Show me MOFs similar to ABAVIJ", {"intent": "similar", "constraints": [], "objectives": [], "metals": [],
                                        "open_metal_site": None, "application": None, "gases": [],
                                        "mof_ids": ["ABAVIJ"], "aggregate": None, "limit": 5}),
    ("Predict the surface area of a MOF with density 0.6, void fraction 0.75, LCD 11 and PLD 7",
     {"intent": "predict", "constraints": [], "objectives": [], "metals": [], "open_metal_site": None,
      "application": None, "gases": [], "mof_ids": [], "aggregate": None, "target_property": "Surface_Area",
      "feature_values": {"Density": 0.6, "Void_Fraction": 0.75, "LCD": 11, "PLD": 7}, "limit": 1}),
    ("What does pore limiting diameter mean?", {"intent": "knowledge", "constraints": [], "objectives": [],
                                                "metals": [], "open_metal_site": None, "application": None,
                                                "gases": [], "mof_ids": [], "aggregate": None, "limit": 5}),
]

ANSWER_SYSTEM = """You are MOFChat, an assistant for metal-organic framework (MOF) selection.
You are given the user's question, the query plan that was executed, and VERIFIED RESULTS from the database.
Write a short, helpful answer in Markdown (at most about 180 words):
- Use ONLY numbers and MOF IDs that appear in the VERIFIED RESULTS, the PLAN or the KNOWLEDGE. Copy MOF IDs exactly.
- Say briefly why the top MOFs fit the request, referring to the property values.
- Start directly with the answer - no preamble such as "Here's a helpful answer".
- Mention important caveats from the NOTES (e.g. heuristics, assumptions). Cite knowledge as [1], [2].
- Do not repeat the whole table; the user can see it below your answer.
"""


def _columns_text() -> str:
    return "\n".join(f"  {c.name}: {c.unit} - {c.description}" for c in COLUMNS if c.kind == "numeric")


def planner_prompt() -> str:
    apps = ", ".join(f'"{k}"' for k in APPLICATIONS)
    return PLANNER_SYSTEM.replace("COLUMNS", _columns_text()).replace("APPLICATIONS", apps)


@lru_cache(maxsize=1)
def _chat(json_mode: bool):
    from langchain_ollama import ChatOllama
    kw = dict(model=LLM_MODEL, temperature=0, base_url=OLLAMA_URL, num_ctx=8192)
    if json_mode:
        kw["format"] = "json"
    return ChatOllama(**kw)


def status() -> tuple[bool, str]:
    """(available, message). Checks that Ollama runs and the model is pulled."""
    try:
        r = httpx.get(f"{OLLAMA_URL}/api/tags", timeout=2.0)
        names = [m["name"] for m in r.json().get("models", [])]
    except Exception:
        return False, "Ollama is not running (start it with `ollama serve`)."
    if not any(n.split(":")[0] == LLM_MODEL.split(":")[0] for n in names):
        return False, f"Model '{LLM_MODEL}' is not pulled (run `ollama pull {LLM_MODEL}`)."
    return True, f"{LLM_MODEL} via Ollama"


def plan_messages(question: str, feedback: list[tuple[str, str]] = ()) -> list:
    from langchain_core.messages import AIMessage, HumanMessage, SystemMessage
    msgs = [SystemMessage(planner_prompt())]
    for q, plan in EXAMPLES:
        msgs += [HumanMessage(q), AIMessage(json.dumps(plan))]
    msgs.append(HumanMessage(question))
    for bad_json, errors in feedback:
        msgs += [AIMessage(bad_json), HumanMessage(
            "That plan is invalid:\n- " + errors + "\nReturn the corrected JSON plan for the same question.")]
    return msgs


def llm_plan(question: str, feedback: list[tuple[str, str]] = ()) -> tuple[dict | None, str]:
    raw = _chat(True).invoke(plan_messages(question, feedback)).content
    try:
        obj = json.loads(raw)
        return (obj if isinstance(obj, dict) else None), raw
    except json.JSONDecodeError:
        return None, raw


def write_answer(context: str) -> str:
    from langchain_core.messages import HumanMessage, SystemMessage
    return _chat(False).invoke([SystemMessage(ANSWER_SYSTEM), HumanMessage(context)]).content.strip()
