"""
Deterministic, rule-based query parser.

Used (1) as the fallback planner when the LLM is unavailable or produces an
invalid plan, (2) to fill numeric constraints the LLM missed (hybrid mode) and
(3) as a reproducible baseline in the evaluation.
"""

from __future__ import annotations

import re

from . import db
from .config import APPLICATIONS, DEFAULT_LIMIT, GAS_ALIASES, alias_table
from .plan import Constraint, Objective, QueryPlan

NUM_WORDS = {"one": 1, "two": 2, "three": 3, "four": 4, "five": 5, "six": 6, "seven": 7, "eight": 8,
             "nine": 9, "ten": 10, "eleven": 11, "twelve": 12, "fifteen": 15, "twenty": 20,
             "a couple of": 2, "a few": 3, "several": 5, "single": 1}

_ALIASES = alias_table()
PROP = r"(?<![a-z])(?P<prop>" + "|".join(re.escape(a) for a, _ in _ALIASES) + r")(?![a-z])"
PROP2 = PROP.replace("?P<prop>", "?P<prop2>")
NUM = r"(?P<num>-?\d+(?:\.\d+)?|\.\d+)\s*(?P<k>k\b)?\s*(?P<pct>%|percent)?"
NUM2 = NUM.replace("?P<num>", "?P<num2>").replace("?P<k>", "?P<k2>").replace("?P<pct>", "?P<pct2>")
UNIT = (r"(?:\s*(?:m\^?2\s*/\s*g|m²\s*/\s*g|m\^?2\s*/\s*cm\^?3|m²\s*/\s*cm³|g\s*/\s*cm\^?3|g\s*/\s*cm³|g\s*/\s*cc|"
        r"cm\^?3\s*/\s*g|cm³\s*/\s*g|cc\s*/\s*g|å|angstroms?|angstrom|a\b|nm\b))?")

CMP_PATTERNS = [
    (r"greater than or equal to|more than or equal to|at least|no less than|not less than|minimum of|"
     r"a minimum|min\.? of|>=|≥|=>", ">="),
    (r"less than or equal to|at most|no more than|not more than|maximum of|a maximum|max\.? of|up to|"
     r"not exceeding|<=|≤|=<", "<="),
    (r"greater than|more than|larger than|higher than|bigger than|in excess of|above|over|exceeding|exceeds|"
     r"exceed|>", ">"),
    (r"less than|lower than|smaller than|fewer than|below|under|beneath|<", "<"),
]
CMP = r"(?<![a-z])(?P<cmp>" + "|".join(p for p, _ in CMP_PATTERNS) + ")"
POSTFIX = (r"(?P<post>or more|or higher|or above|or greater|and above|and up|or larger|or bigger|\+|"
           r"or less|or lower|or below|or smaller|and below|and under)")
APPROX = r"(?P<approx>around|about|approximately|approx\.?|roughly|close to|near|nearly|~|≈)"
FILL = r"(?P<fill>[^.;?!]{0,32}?)"

MAX_WORDS = (r"highest|largest|greatest|biggest|maximum|maximal|maximi[sz]e[sd]?|max|most|top|best|high|higher|"
             r"large|larger|big|bigger|huge|great|good|lots of|plenty of|increased|maximal")
MIN_WORDS = (r"lowest|smallest|minimum|minimal|minimi[sz]e[sd]?|min|least|low|lower|small|smaller|tiny|little|"
             r"reduced|minimal")

AMBIGUOUS_SYMBOLS = {"In", "As", "Be", "Co", "La", "Re", "Ba", "Ca", "Al", "Na", "Ho", "Th", "Te", "Pu",
                     "U", "W", "Y", "K", "V", "Sc", "Ga", "Ti", "Ce", "Er", "Pr", "Np", "Hf", "Sb", "Si"}
SIMILAR_RE = re.compile(r"\b(similar to|similar|like|resembl\w*|comparable to|analog\w* (?:of|to)|neighbo\w*|"
                        r"closest to|close to)\b")
PREDICT_RE = re.compile(r"\b(predict\w*|estimat\w*|forecast\w*|what would (?:the|its|be)|guess)\b")
COUNT_RE = re.compile(r"\b(how many|number of|count of|count the|count)\b")
AVG_RE = re.compile(r"\b(average|mean|typical)\b")
OMS_RE = re.compile(r"(open[- ]metal[- ]sites?|\boms\b|coordinatively unsaturated|unsaturated metal)")
NEG_RE = re.compile(r"(\bno\b|\bwithout\b|\bnot\b|\blacking\b|\bfree of\b|\bnon\b|\bexclud\w*)\W*(\w+\W+){0,2}$")


def _to_float(m, num="num", k="k") -> float:
    v = float(m.group(num))
    if m.group(k):
        v *= 1000
    return v


def _scale_percent(col: str, v: float, is_pct: bool, notes: list[str]) -> float:
    if col == "Void_Fraction" and (is_pct or v > 1.0):
        notes.append(f"Interpreted {v:g}{'%' if is_pct else ''} void fraction as {v / 100:g}.")
        return v / 100
    return v


def _scan(pattern: str, text: str):
    """Like re.finditer but tries a match at every start position, so a rejected long
    match cannot hide a shorter valid one that starts inside it."""
    rx = re.compile(pattern)
    for start in range(len(text)):
        m = rx.match(text, start)
        if m:
            yield m


def _overlaps(span, used) -> bool:
    return any(span[0] < u[1] and u[0] < span[1] for u in used)


def _blank(text: str, spans) -> str:
    chars = list(text)
    for a, b in spans:
        for i in range(a, b):
            chars[i] = " "
    return "".join(chars)


def _normalise(q: str) -> str:
    t = q.lower()
    t = re.sub(r"(\d),(\d{3})", r"\1\2", t)          # 4,000 -> 4000
    t = t.replace("–", "-").replace("—", "-")
    t = re.sub(r"\s+", " ", t)
    return t


def _col(prop_text: str) -> str:
    p = prop_text.lower()
    for alias, col in _ALIASES:
        if p == alias:
            return col
    raise KeyError(prop_text)


def _extract_constraints(t: str, plan: QueryPlan, used: list) -> list[tuple[str, float]]:
    """Fill plan.constraints; return plain 'property value' mentions (for predict)."""
    notes = plan.notes
    cons: list[Constraint] = []

    def add(col, op, v, span):
        cons.append(Constraint(col, op, v))
        used.append(span)

    # between / range
    for pat in (PROP + FILL + r"\bbetween\s*" + NUM + UNIT + r"\s*(?:and|-|to)\s*" + NUM2 + UNIT,
                PROP + FILL + r"\b(?:from|in the range(?: of)?|range of|within)\s*" + NUM + UNIT
                + r"\s*(?:to|-|and)\s*" + NUM2 + UNIT,
                r"\bbetween\s*" + NUM + UNIT + r"\s*(?:and|-|to)\s*" + NUM2 + UNIT + r"\s*(?:of\s*)?(?:the\s*)?" + PROP):
        for m in _scan(pat, t):
            if _overlaps(m.span(), used):
                continue
            col = _col(m.group("prop"))
            lo = _scale_percent(col, _to_float(m), bool(m.group("pct")), notes)
            hi = _scale_percent(col, _to_float(m, "num2", "k2"), bool(m.group("pct2")), notes)
            lo, hi = min(lo, hi), max(lo, hi)
            add(col, ">=", lo, m.span())
            cons.append(Constraint(col, "<=", hi))

    # approximately X  -> +-10 %
    for m in _scan(PROP + FILL + APPROX + r"\s*" + NUM + UNIT, t):
        if _overlaps(m.span(), used):
            continue
        col = _col(m.group("prop"))
        v = _scale_percent(col, _to_float(m), bool(m.group("pct")), notes)
        add(col, ">=", round(v * 0.9, 6), m.span())
        cons.append(Constraint(col, "<=", round(v * 1.1, 6)))
        notes.append(f"Interpreted 'around {v:g}' for {col} as {v * 0.9:g}-{v * 1.1:g} (±10%).")

    # postfix: "4000 m2/g or more"
    for m in _scan(PROP + FILL + NUM + UNIT + r"\s*" + POSTFIX, t):
        if _overlaps(m.span(), used) or re.search(CMP, m.group("fill") or ""):
            continue
        col = _col(m.group("prop"))
        post = m.group("post")
        op = ">=" if post in ("or more", "or higher", "or above", "or greater", "and above", "and up",
                              "or larger", "or bigger", "+") else "<="
        add(col, op, _scale_percent(col, _to_float(m), bool(m.group("pct")), notes), m.span())

    # property ... comparator number
    for m in _scan(PROP + FILL + CMP + r"\s*(?:a|an|the)?\s*(?:value of\s*)?" + NUM + UNIT, t):
        if _overlaps(m.span(), used):
            continue
        fill = m.group("fill") or ""
        if re.search(PROP, fill):
            continue
        col = _col(m.group("prop"))
        op = next(o for p, o in CMP_PATTERNS if re.fullmatch(p, m.group("cmp")))
        add(col, op, _scale_percent(col, _to_float(m), bool(m.group("pct")), notes), m.span())
        # continuation without repeating the property: "... larger than 3.3 but smaller than 3.64"
        end = m.end()
        while True:
            c = re.compile(r"\s*,?\s*(?:but|and|yet)?\s*(?:also\s*)?" + CMP + r"\s*" + NUM + UNIT).match(t, end)
            if not c or _overlaps(c.span(), used):
                break
            op2 = next(o for p, o in CMP_PATTERNS if re.fullmatch(p, c.group("cmp")))
            add(col, op2, _scale_percent(col, _to_float(c), bool(c.group("pct")), notes), c.span())
            end = c.end()

    # comparator number ... property  ("more than 4000 m2/g surface area")
    for m in _scan(CMP + r"\s*" + NUM + UNIT + r"\s*(?:of\s*)?(?:the\s*)?(?:in\s*)?" + PROP, t):
        if _overlaps(m.span(), used):
            continue
        col = _col(m.group("prop"))
        op = next(o for p, o in CMP_PATTERNS if re.fullmatch(p, m.group("cmp")))
        add(col, op, _scale_percent(col, _to_float(m), bool(m.group("pct")), notes), m.span())

    # plain mentions "density 0.5", "density of 0.5", "density = 0.5"
    plain: list[tuple[str, float]] = []
    for m in _scan(PROP + r"\s*(?:of|is|=|:|equal to|equals|value of|value)?\s*(?:about\s*)?" + NUM + UNIT, t):
        if _overlaps(m.span(), used):
            continue
        col = _col(m.group("prop"))
        plain.append((col, _scale_percent(col, _to_float(m), bool(m.group("pct")), notes)))
        used.append(m.span())

    plan.constraints.extend(cons)
    return plain


def _extract_objectives(t: str, plan: QueryPlan, used: list) -> None:
    free = _blank(t, used)
    seen = set()
    patterns = [
        (r"\b(?P<w>" + MAX_WORDS + r")\b(?:\s+(?!and\b|or\b|with\b)\w+){0,2}?\s+" + PROP, "max"),
        (r"\b(?P<w>" + MIN_WORDS + r")\b(?:\s+(?!and\b|or\b|with\b)\w+){0,2}?\s+" + PROP, "min"),
        (PROP + r"\s+(?:as\s+)?(?:high|large|big)\s+as\s+possible", "max"),
        (PROP + r"\s+(?:as\s+)?(?:low|small)\s+as\s+possible", "min"),
        (PROP + r"\s+(?:is\s+|being\s+)?(?:maximi[sz]ed|high|large)\b", "max"),
        (PROP + r"\s+(?:is\s+|being\s+)?(?:minimi[sz]ed|low|small)\b", "min"),
        (r"\b(?P<w>top|best|highest|leading)\b[^.?!]{0,30}?\b(?:by|in terms of|ranked by|sorted by|according to)\s+"
         r"(?:their\s+|the\s+)?" + PROP, "max"),
        (r"\b(?P<w>bottom|lowest|worst)\b[^.?!]{0,30}?\b(?:by|in terms of|ranked by|sorted by|according to)\s+"
         r"(?:their\s+|the\s+)?" + PROP, "min"),
        (r"\b(?:ranked|sorted|ordered)\s+by\s+(?:their\s+|the\s+)?" + PROP, "max"),
    ]
    found = []
    for pat, d in patterns:
        for m in re.finditer(pat, free):
            col = _col(m.group("prop"))
            if col not in seen:
                found.append((m.start(), Objective(col, d)))
                seen.add(col)
    special = [(r"\b(lightest|light-?weight|light|low-density)\b", "Density", "min"),
               (r"\b(heaviest|densest)\b", "Density", "max"),
               (r"\b(most porous|highly porous|very porous|porous)\b", "Void_Fraction", "max"),
               (r"\b(large|big|wide|larger|bigger|wider|largest|biggest|widest) (?:open )?pores?\b(?!\s*(?:volume|size|diameter|limiting|aperture|window))", "LCD", "max"),
               (r"\b(small|narrow|tiny|smaller|narrower|smallest|narrowest) pores?\b(?!\s*(?:volume|size|diameter|limiting|aperture|window))", "LCD", "min")]
    for pat, col, d in special:
        m = re.search(pat, free)
        if m and col not in seen and col not in {c.column for c in plan.constraints}:
            found.append((m.start(), Objective(col, d)))
            seen.add(col)
    plan.objectives.extend(o for _, o in sorted(found, key=lambda x: x[0]))


def _extract_limit(t: str, plan: QueryPlan) -> None:
    words = "|".join(sorted(NUM_WORDS, key=len, reverse=True))
    nouns = r"(?:mofs?|materials?|frameworks?|candidates?|structures?|options?|examples?|results?|ones?|metal[- ]organic frameworks?)"
    m = re.search(r"\b(?:top|best|first)\s+(\d+|" + words + r")\b", t) or \
        re.search(r"\b(\d+|" + words + r")\s+(?:\w+\s+){0,2}?" + nouns + r"\b", t)
    if m:
        tok = m.group(1)
        n = int(tok) if tok.isdigit() else NUM_WORDS.get(tok, DEFAULT_LIMIT)
        if 0 < n <= 1000:
            plan.limit, plan.limit_explicit = n, True
            return
    superlative = re.search(r"\b(highest|lowest|largest|smallest|maximum|minimum|most|least|best|densest|lightest)\b", t)
    if superlative and re.search(r"\bwhich (?:one )?(?:has|is)\b", t):
        plan.limit = 1
        return
    if re.search(r"\b(which|what)\s+(?:\w+\s+){0,2}?(?:mof|material|framework|structure)\b(?!s)", t) and superlative or \
       re.search(r"\b(the|a|one|single) (?:single )?(?:mof|material|framework)\b(?!s)", t) and \
       re.search(r"\b(highest|lowest|largest|smallest|maximum|minimum|most|least|best|densest|lightest)\b", t):
        plan.limit = 1


def _extract_ids(query: str, plan: QueryPlan) -> None:
    tokens = re.findall(r"[A-Za-z0-9][A-Za-z0-9_.\-]*[A-Za-z0-9]|[A-Za-z0-9]", query)
    found = []
    for tok in tokens:
        if len(tok) < 4 and tok.lower() not in ("mof-5",):
            continue
        ids = db.resolve_mof_id(tok)
        # bare 6-letter words like "SAMPLE" only count as IDs when upper-case in the query
        if ids and re.fullmatch(r"[A-Za-z]{6}", tok) and not tok.isupper():
            continue
        if ids:
            for i in ids:
                if i not in found:
                    found.append(i)
        elif re.fullmatch(r"[A-Z]{6}\d{0,2}", tok):
            plan.notes.append(f"'{tok}' looks like a CSD refcode but is not in the CoRE-MOF table.")
        elif tok.lower() in ("mof-5", "irmof-1"):
            plan.notes.append(f"{tok} (refcode SAHYIK) is not in this CoRE-MOF table.")
    plan.mof_ids = found


def _extract_metals(query: str, t: str, plan: QueryPlan) -> None:
    metals = []
    for m in re.finditer(r"\b([A-Z][a-z]?)\b(?P<after>[- ]?(?:based|containing|mofs?|metal|nodes?|centers?|centres?|clusters?|sites?|frameworks?))?",
                         query):
        sym, after = m.group(1), m.group("after")
        before = query[max(0, m.start() - 12):m.start()].lower()
        if db.resolve_metal(sym) != sym:
            continue
        if sym in AMBIGUOUS_SYMBOLS and not (after or re.search(r"(containing|with|metal|of|from|and|or)\s*$", before)):
            continue
        if re.match(r"[A-Z][a-z]?\d", query[m.start():m.end() + 1]):   # e.g. part of a formula
            continue
        metals.append(sym)
    for name_m in re.finditer(r"\b([a-z]+)\b", t):
        sym = db.resolve_metal(name_m.group(1)) if len(name_m.group(1)) > 3 else None
        if sym:
            metals.append(sym)
    out = []
    for s in metals:
        if s not in out:
            out.append(s)
    plan.metals = out


def _extract_oms(t: str, plan: QueryPlan) -> None:
    m = OMS_RE.search(t)
    if m:
        plan.open_metal_site = not bool(NEG_RE.search(t[:m.start()]))


def _extract_application(query: str, t: str, plan: QueryPlan) -> None:
    gases = []
    for m in re.finditer(r"\b(carbon dioxide|carbon monoxide|natural gas|co2|ch4|h2o|n2|o2|h2|xe|kr|"
                         r"methane|hydrogen|nitrogen|oxygen|xenon|krypton|argon|water)\b", t):
        g = GAS_ALIASES.get(m.group(1))
        if g and g not in gases:
            gases.append(g)
    if re.search(r"\bCO\b", query) and "CO" not in gases:
        gases.append("CO")
    sep = re.search(r"\b(separat\w*|sieving|sieve|selectiv\w*|purif\w*)\b", t)
    if sep and len(gases) >= 2:
        plan.application, plan.gases = "gas_separation", gases[:2]
        return
    for key, preset in APPLICATIONS.items():
        if key == "gas_separation":
            continue
        if any(k in t for k in preset.keywords):
            plan.application = key
            return
    if sep:
        plan.application, plan.gases = "gas_separation", gases[:2]


CONCEPT_RE = re.compile(r"^\s*(why|what is|what are|what's|what does|what do|explain|define|describe|how does|how do|"
                        r"how is|how are|how accurate|tell me what|what makes)\b")
REQUEST_RE = re.compile(r"\b(which|find|list|show|recommend|suggest|give me|top|rank|search|get me)\b")


def _intent(query: str, t: str, plan: QueryPlan, plain: list[tuple[str, float]]) -> None:
    if CONCEPT_RE.search(t) and not plan.constraints and not plan.mof_ids and not plain \
            and not REQUEST_RE.search(t) and not COUNT_RE.search(t) and not AVG_RE.search(t) \
            and not re.search(r"\b(mofs?|materials?|frameworks?|structures?|candidates?)\b", t):
        plan.intent = "knowledge"
        plan.objectives, plan.metals, plan.open_metal_site, plan.application = [], [], None, None
        return
    has_filters = bool(plan.constraints or plan.objectives or plan.metals or plan.application
                       or plan.open_metal_site is not None)
    if PREDICT_RE.search(t):
        plan.intent = "predict"
        m = re.search(r"\b(?:predict\w*|estimat\w*|forecast\w*)\b\s+(?:the\s+|its\s+)?" + PROP, t)
        plan.target_property = _col(m.group("prop")) if m else "Surface_Area"
        plan.feature_values = {c: v for c, v in plain if c != plan.target_property}
        for c in plan.constraints:  # "density of 0.5" etc. become inputs, not filters
            if c.op == "==":
                plan.feature_values[c.column] = c.value
        plan.constraints = [c for c in plan.constraints if c.op != "=="]
        return
    if plan.mof_ids and SIMILAR_RE.search(t):
        plan.intent = "similar"
        return
    if COUNT_RE.search(t):
        plan.intent, plan.aggregate = "count", {"func": "count", "column": None}
        return
    m = AVG_RE.search(t)
    if m and plan.objectives == [] and re.search(r"\b(?:average|mean|typical)\s+" + PROP, t):
        col = _col(re.search(r"\b(?:average|mean|typical)\s+" + PROP, t).group("prop"))
        plan.intent, plan.aggregate = "count", {"func": "avg", "column": col}
        return
    if plan.mof_ids and not plan.constraints:
        plan.intent = "lookup"
        return
    if plain and not has_filters:
        # "MOFs with density 0.5" -> approximately equal (+-5 %)
        for col, v in plain:
            plan.constraints += [Constraint(col, ">=", round(v * 0.95, 6)), Constraint(col, "<=", round(v * 1.05, 6))]
            plan.notes.append(f"Interpreted '{col} {v:g}' as {v * 0.95:g}-{v * 1.05:g} (±5%).")
        plan.intent = "search"
        return
    plan.intent = "search" if has_filters else "knowledge"


def parse(query: str) -> QueryPlan:
    plan = QueryPlan(source="rules")
    t = _normalise(query)
    used: list[tuple[int, int]] = []
    _extract_ids(query, plan)
    plain = _extract_constraints(t, plan, used)
    _extract_objectives(t, plan, used)
    _extract_limit(t, plan)
    _extract_oms(t, plan)
    _extract_application(query, t, plan)
    _extract_metals(query, t, plan)
    _intent(query, t, plan, plain)
    if plan.intent in ("lookup", "similar", "predict"):
        # Metal letters that are really part of an ID or a common name should not filter.
        plan.metals = [] if plan.intent != "similar" else plan.metals
    return plan
