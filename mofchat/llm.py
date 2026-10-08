"""
LLM layer: a provider-agnostic model registry + the planner and answer-writer prompts.

Same design as the registry in our DL project (src/llm/registry.py): a declarative
table of models across providers, each reporting whether it is usable *right now*
and why not. MOFChat treats the LLM as an interchangeable component:

  provider    models (verified against the live model lists on 2026-10-08)       key in .env
  ----------  ------------------------------------------------------------------  ------------------
  Ollama      Llama 3 8B, Llama 3.1 8B, Qwen 2.5 7B, Nemotron Mini (local)          none
  Google      Gemini 3.5 Flash, 3.8 Flash, 3.1 Flash-Lite, Flash-Lite latest       GOOGLE_API_KEY
  Groq        GPT-OSS 120B, GPT-OSS 20B, Qwen 3.8 27B                              GROQ_API_KEY
  OpenRouter  Nemotron 3 Super 120B, Nemotron 3 Ultra 550B, Gemma 4 31B (:free)    OPENROUTER_API_KEY

Free tiers rate-limit and occasionally return 503/429, so every call goes through
`chat()`, which throttles per model and falls back along a chain
(selected model -> MOFCHAT_FALLBACK models -> local Llama 3). If every model fails,
the agent falls back to the rule-based planner and template answers.

    python -m mofchat.llm --list          # availability table
    python -m mofchat.llm --probe         # one real call to every available model
"""

from __future__ import annotations

import json
import os
import re
import threading
import time
from collections import deque
from dataclasses import dataclass
from enum import Enum
from functools import lru_cache

import httpx

from .config import APPLICATIONS, COLUMNS, PROJECT_ROOT


# --------------------------------------------------------------------------
# Environment (.env in the project root; real environment variables win)
# --------------------------------------------------------------------------
def load_env() -> None:
    try:
        from dotenv import load_dotenv
        load_dotenv(PROJECT_ROOT / ".env", override=False)
    except ImportError:  # python-dotenv missing: rely on the real environment
        pass


load_env()
OLLAMA_URL = os.environ.get("OLLAMA_BASE_URL", os.environ.get("OLLAMA_HOST", "http://localhost:11434"))
if not OLLAMA_URL.startswith("http"):
    OLLAMA_URL = "http://" + OLLAMA_URL


# --------------------------------------------------------------------------
# Registry
# --------------------------------------------------------------------------
class Provider(str, Enum):
    OLLAMA = "ollama"
    GOOGLE = "google"
    GROQ = "groq"
    OPENROUTER = "openrouter"


PROVIDER_LABEL = {
    Provider.OLLAMA: "Ollama (local, offline)",
    Provider.GOOGLE: "Google Gemini (free tier)",
    Provider.GROQ: "Groq (free tier)",
    Provider.OPENROUTER: "OpenRouter (free models)",
}
PROVIDER_PACKAGE = {
    Provider.OLLAMA: "langchain_ollama",
    Provider.GOOGLE: "langchain_google_genai",
    Provider.GROQ: "langchain_groq",
    Provider.OPENROUTER: "langchain_openai",      # OpenAI-compatible endpoint
}
PROVIDER_KEY_URL = {
    Provider.GOOGLE: "https://aistudio.google.com/apikey",
    Provider.GROQ: "https://console.groq.com/keys",
    Provider.OPENROUTER: "https://openrouter.ai/keys",
}


@dataclass(frozen=True)
class ModelSpec:
    model_id: str              # short handle used in .env, the app and the evaluation
    provider: Provider
    model_name: str            # the provider's identifier
    label: str
    needs_key: str | None = None
    rpm: int = 0               # free-tier requests per minute (0 = no limit)
    tpm: int = 0               # free-tier tokens per minute (0 = no limit); Groq's binding limit is 8,000
    notes: str = ""
    options: tuple = ()        # extra client options, e.g. (("thinking_budget", 0),)

    @property
    def is_local(self) -> bool:
        return self.provider is Provider.OLLAMA


MODELS: list[ModelSpec] = [
    # local
    ModelSpec("llama3-local", Provider.OLLAMA, "llama3:latest", "Llama 3 8B (local)",
              notes="Offline; nothing leaves the machine. The review-1/2 baseline."),
    ModelSpec("llama3.1-local", Provider.OLLAMA, "llama3.1:latest", "Llama 3.1 8B (local)"),
    ModelSpec("qwen2.5-local", Provider.OLLAMA, "qwen2.5:latest", "Qwen 2.5 7B (local)",
              notes="Good at structured output."),
    ModelSpec("nemotron-mini-local", Provider.OLLAMA, "nemotron-mini:latest", "Nemotron Mini 4B (local)"),
    # Google Gemini (AI Studio free tier). There is no "Gemini 2.1 Flash"; gemini-2.5-flash
    # returns 404 on this key and gemini-flash-latest was overloaded (503) when tested.
    # Planning is structured extraction, so "thinking" is switched off/low: 1.7 s instead of up to 25 s
    # for 3.5 Flash. 3.8 Flash rejects thinking_level="minimal" and ignores thinking_budget=0.
    ModelSpec("gemini-3.5-flash", Provider.GOOGLE, "gemini-3.5-flash", "Gemini 3.5 Flash",
              "GOOGLE_API_KEY", rpm=10, notes="Fast and capable; recommended Gemini model.",
              options=(("thinking_budget", 0),)),
    ModelSpec("gemini-3.8-flash", Provider.GOOGLE, "gemini-3.8-flash", "Gemini 3.8 Flash (newest)",
              "GOOGLE_API_KEY", rpm=10, notes="Newest Flash; often overloaded (503) on the free tier.",
              options=(("thinking_level", "low"),)),
    ModelSpec("gemini-3.1-flash-lite", Provider.GOOGLE, "gemini-3.1-flash-lite", "Gemini 3.1 Flash-Lite",
              "GOOGLE_API_KEY", rpm=15, notes="Fastest Gemini, higher free limits.",
              options=(("thinking_budget", 0),)),
    ModelSpec("gemini-flash-lite-latest", Provider.GOOGLE, "gemini-flash-lite-latest", "Gemini Flash-Lite (latest)",
              "GOOGLE_API_KEY", rpm=15, options=(("thinking_budget", 0),)),
    # Groq (free tier). Groq retired its Llama 3.x endpoints in 2026.
    ModelSpec("gpt-oss-120b", Provider.GROQ, "openai/gpt-oss-120b", "GPT-OSS 120B (Groq)",
              "GROQ_API_KEY", rpm=30, tpm=8000, notes="Largest Groq model; very fast."),
    ModelSpec("gpt-oss-20b", Provider.GROQ, "openai/gpt-oss-20b", "GPT-OSS 20B (Groq)",
              "GROQ_API_KEY", rpm=30, tpm=8000),
    ModelSpec("qwen3.8-27b", Provider.GROQ, "qwen/qwen3.8-27b", "Qwen 3.8 27B (Groq)",
              "GROQ_API_KEY", rpm=30, tpm=8000),
    # OpenRouter free models (free accounts: about 50 free requests per day in total)
    ModelSpec("nemotron-super-free", Provider.OPENROUTER, "nvidia/nemotron-3-super-120b-a12b:free",
              "Nemotron 3 Super 120B (OpenRouter free)", "OPENROUTER_API_KEY", rpm=20),
    ModelSpec("nemotron-ultra-free", Provider.OPENROUTER, "nvidia/nemotron-3-ultra-550b-a55b:free",
              "Nemotron 3 Ultra 550B (OpenRouter free)", "OPENROUTER_API_KEY", rpm=20),
    ModelSpec("gemma4-31b-free", Provider.OPENROUTER, "google/gemma-4-31b-it:free",
              "Gemma 4 31B (OpenRouter free)", "OPENROUTER_API_KEY", rpm=20,
              notes="Often rate-limited upstream (429)."),
]
BY_ID: dict[str, ModelSpec] = {m.model_id: m for m in MODELS}

# Used when MOFCHAT_MODEL is unset; from the model comparison (docs/RESULTS.md §1b): the best model on the
# held-out set, then the most reliable one on another provider (0 provider errors), then local Llama 3.
DEFAULT_ORDER = ["gemini-3.1-flash-lite", "gpt-oss-120b", "qwen3.8-27b", "llama3-local"]


@lru_cache(maxsize=1)
def _ollama_tags_cached(stamp: int) -> tuple[str, ...]:
    try:
        r = httpx.get(f"{OLLAMA_URL}/api/tags", timeout=2.0)
        return tuple(m["name"] for m in r.json().get("models", []))
    except Exception:
        return ()


def _ollama_tags() -> tuple[str, ...]:
    return _ollama_tags_cached(int(time.time() // 30))     # re-check every 30 s


def _package_installed(provider: Provider) -> bool:
    import importlib.util
    return importlib.util.find_spec(PROVIDER_PACKAGE[provider]) is not None


def availability(model_id: str) -> tuple[bool, str]:
    spec = BY_ID.get(model_id)
    if spec is None:
        return False, f"unknown model '{model_id}'"
    if not _package_installed(spec.provider):
        return False, f"package missing - pip install {PROVIDER_PACKAGE[spec.provider].replace('_', '-')}"
    if spec.is_local:
        tags = _ollama_tags()
        if not tags:
            return False, "Ollama is not running - start it with `ollama serve`"
        if spec.model_name not in tags:
            return False, f"not pulled - run `ollama pull {spec.model_name.split(':')[0]}`"
        return True, "ready (local)"
    if not os.environ.get(spec.needs_key or "", "").strip():
        return False, f"{spec.needs_key} not set in .env - get one at {PROVIDER_KEY_URL[spec.provider]}"
    return True, "ready"


def list_models() -> list[tuple[ModelSpec, bool, str]]:
    return [(m, *availability(m.model_id)) for m in MODELS]


def available_ids() -> list[str]:
    return [m.model_id for m, ok, _ in list_models() if ok]


def default_model_id() -> str | None:
    ok = available_ids()
    wanted = os.environ.get("MOFCHAT_MODEL", "").strip()
    for mid in ([wanted] if wanted else []) + DEFAULT_ORDER + ok:
        if mid in ok:
            return mid
    return None


FALLBACK_ENABLED = True   # the evaluation switches this off so every answer is attributed to one model


def fallback_chain(model_id: str | None) -> list[str]:
    """Selected model first, then MOFCHAT_FALLBACK (comma list), then the default order; available only."""
    ok = set(available_ids())
    if not FALLBACK_ENABLED:
        return [model_id] if model_id in ok else []
    extra = [m.strip() for m in os.environ.get("MOFCHAT_FALLBACK", "").split(",") if m.strip()]
    chain = []
    for mid in ([model_id] if model_id else []) + extra + DEFAULT_ORDER:
        if mid in ok and mid not in chain:
            chain.append(mid)
    return chain


def status(model_id: str | None = None) -> tuple[bool, str]:
    """(usable, message) for the given or default model - used by the app and the agent."""
    mid = model_id or default_model_id()
    if mid is None:
        return False, "No language model available: start Ollama (`ollama serve`) or add an API key to .env."
    ok, why = availability(mid)
    return (True, BY_ID[mid].label) if ok else (False, f"{BY_ID[mid].label}: {why}")


# --------------------------------------------------------------------------
# Calling a model
# --------------------------------------------------------------------------
class LLMError(RuntimeError):
    pass


class RateLimited(LLMError):
    """The free-tier budget of a model is used up for the next MAX_WAIT_S seconds."""


MAX_WAIT_S = 10.0     # app: rather fall back to the next model than make the user wait; the evaluation raises it
_windows: dict[str, deque] = {}
_lock = threading.Lock()


def _estimate_tokens(messages) -> int:
    chars = sum(len(str(getattr(m, "content", m[1] if isinstance(m, tuple) else m))) for m in messages)
    return int(chars / 3.5) + 400                     # prompt + a typical reply


def _throttle(spec: ModelSpec, est_tokens: int = 0) -> None:
    """Sliding 60-second window of (time, tokens) per model, so requests stay inside the free-tier
    requests-per-minute and tokens-per-minute limits. Raises RateLimited if that needs a wait
    longer than MAX_WAIT_S."""
    if not (spec.rpm or spec.tpm):
        return
    with _lock:
        win = _windows.setdefault(spec.model_id, deque())
        while True:
            now = time.time()
            while win and now - win[0][0] >= 60:
                win.popleft()
            over_rpm = spec.rpm and len(win) >= spec.rpm
            over_tpm = spec.tpm and win and sum(t for _, t in win) + est_tokens > spec.tpm
            if not (over_rpm or over_tpm):
                win.append((now, est_tokens))
                return
            wait = 60 - (now - win[0][0]) + 0.05
            if wait > MAX_WAIT_S:
                raise RateLimited(f"{spec.model_id}: free-tier budget used up for {wait:.0f}s")
            time.sleep(wait)


@lru_cache(maxsize=32)
def _client(model_id: str, json_mode: bool):
    spec = BY_ID[model_id]
    if spec.provider is Provider.OLLAMA:
        from langchain_ollama import ChatOllama
        kw = dict(model=spec.model_name, temperature=0, base_url=OLLAMA_URL, num_ctx=8192)
        if json_mode:
            kw["format"] = "json"
        return ChatOllama(**kw)
    if spec.provider is Provider.GOOGLE:
        from langchain_google_genai import ChatGoogleGenerativeAI
        kw = dict(model=spec.model_name, temperature=0, google_api_key=os.environ["GOOGLE_API_KEY"],
                  max_retries=1, timeout=60)
        if json_mode:
            kw["response_mime_type"] = "application/json"
        return ChatGoogleGenerativeAI(**kw, **dict(spec.options))
    if spec.provider is Provider.GROQ:
        from langchain_groq import ChatGroq
        kw = dict(model=spec.model_name, temperature=0, api_key=os.environ["GROQ_API_KEY"], max_retries=1, timeout=60)
        if json_mode:
            kw["model_kwargs"] = {"response_format": {"type": "json_object"}}
        return ChatGroq(**kw)
    from langchain_openai import ChatOpenAI          # OpenRouter (OpenAI-compatible)
    return ChatOpenAI(model=spec.model_name, temperature=0, api_key=os.environ["OPENROUTER_API_KEY"],
                      base_url="https://openrouter.ai/api/v1", max_retries=1, timeout=90)


def extract_text(response) -> str:
    """Plain text from any provider's response: Gemini returns content blocks, and some
    reasoning models put <think>...</think> before the answer."""
    content = getattr(response, "content", response)
    if isinstance(content, list):
        parts = []
        for block in content:
            if isinstance(block, str):
                parts.append(block)
            elif isinstance(block, dict) and block.get("type") in (None, "text"):
                parts.append(block.get("text", ""))
        content = "\n".join(p for p in parts if p)
    text = re.sub(r"<think>.*?</think>", "", str(content), flags=re.S)
    return text.strip()


def extract_json(text: str) -> dict | None:
    """First JSON object in a model reply (handles ```json fences and text around it)."""
    t = re.sub(r"^```(?:json)?\s*|\s*```$", "", text.strip(), flags=re.M)
    try:
        obj = json.loads(t)
        return obj if isinstance(obj, dict) else None
    except json.JSONDecodeError:
        pass
    start = t.find("{")
    while start != -1:
        depth = 0
        for i in range(start, len(t)):
            depth += {"{": 1, "}": -1}.get(t[i], 0)
            if depth == 0:
                try:
                    obj = json.loads(t[start:i + 1])
                    return obj if isinstance(obj, dict) else None
                except json.JSONDecodeError:
                    break
        start = t.find("{", start + 1)
    return None


def chat(messages, model_id: str | None = None, json_mode: bool = False,
         chain: list[str] | None = None) -> tuple[str, str]:
    """Send `messages` to the first model in the fallback chain that answers.
    Returns (text, model_id_used). Raises LLMError if every model fails."""
    chain = chain if chain is not None else fallback_chain(model_id)
    if not chain:
        raise LLMError("no language model available")
    errors = []
    est = _estimate_tokens(messages)
    for mid in chain:
        spec = BY_ID[mid]
        for use_json in ([True, False] if json_mode else [False]):
            try:
                _throttle(spec, est)
                text = extract_text(_client(mid, use_json).invoke(messages))
                if text:
                    return text, mid
                errors.append(f"{mid}: empty reply")
                break
            except Exception as e:                    # rate limit, outage, retired model, JSON mode refused
                msg = f"{type(e).__name__}: {str(e)[:160]}"
                errors.append(f"{mid}{' (json mode)' if use_json else ''}: {msg}")
                if use_json and re.search(r"response_format|json|400|invalid", str(e), re.I):
                    continue                          # retry this model without JSON mode
                break
    raise LLMError("all models failed - " + " | ".join(errors))


# --------------------------------------------------------------------------
# Prompts
# --------------------------------------------------------------------------
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
- If there is a PREDICTION, lead with its value and 90% interval (it is a surrogate-model estimate for the
  descriptors given, not a database record), then name the descriptors that drive it most (shap).
"""


def _columns_text() -> str:
    return "\n".join(f"  {c.name}: {c.unit} - {c.description}" for c in COLUMNS if c.kind == "numeric")


def planner_prompt() -> str:
    apps = ", ".join(f'"{k}"' for k in APPLICATIONS)
    return PLANNER_SYSTEM.replace("COLUMNS", _columns_text()).replace("APPLICATIONS", apps)


def plan_messages(question: str, feedback=()) -> list:
    from langchain_core.messages import AIMessage, HumanMessage, SystemMessage
    msgs = [SystemMessage(planner_prompt())]
    for q, plan in EXAMPLES:
        msgs += [HumanMessage(q), AIMessage(json.dumps(plan))]
    msgs.append(HumanMessage(question))
    for bad_json, errors in feedback:
        msgs += [AIMessage(bad_json), HumanMessage(
            "That plan is invalid:\n- " + errors + "\nReturn the corrected JSON plan for the same question.")]
    return msgs


def llm_plan(question: str, feedback=(), model_id: str | None = None) -> tuple[dict | None, str, str]:
    """(plan object or None, raw reply, model that answered)."""
    raw, used = chat(plan_messages(question, feedback), model_id, json_mode=True)
    return extract_json(raw), raw, used


def write_answer(context: str, model_id: str | None = None) -> tuple[str, str]:
    """(answer text, model that answered)."""
    from langchain_core.messages import HumanMessage, SystemMessage
    return chat([SystemMessage(ANSWER_SYSTEM), HumanMessage(context)], model_id)


# --------------------------------------------------------------------------
# CLI
# --------------------------------------------------------------------------
def _table() -> str:
    lines, current = [], None
    for spec, ok, why in list_models():
        if spec.provider != current:
            current = spec.provider
            lines += ["", f"  {PROVIDER_LABEL[current]}", "  " + "-" * 78]
        lines.append(f"  {'[OK]' if ok else '[--]'}  {spec.model_id:<26} {spec.label:<40} {why}")
    lines += ["", f"  default: {default_model_id()}   fallback chain: {fallback_chain(default_model_id())}", ""]
    return "\n".join(lines)


def main() -> int:
    import argparse
    ap = argparse.ArgumentParser(description="MOFChat model registry")
    ap.add_argument("--list", action="store_true")
    ap.add_argument("--probe", action="store_true", help="send one real request to every available model")
    args = ap.parse_args()
    if args.probe:
        for spec, ok, why in list_models():
            if not ok:
                print(f"skip   {spec.model_id:<26} {why}")
                continue
            t = time.time()
            try:
                text, _ = chat([("human", "Reply with exactly: OK")], chain=[spec.model_id])
                print(f"WORKS  {spec.model_id:<26} {time.time() - t:5.1f}s  {text[:30]!r}")
            except LLMError as e:
                print(f"FAILS  {spec.model_id:<26} {time.time() - t:5.1f}s  {str(e)[:90]}")
        return 0
    print(_table())
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
