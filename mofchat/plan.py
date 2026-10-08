"""The structured query plan that the planner produces and the executor runs."""

from __future__ import annotations

from dataclasses import asdict, dataclass, field
from typing import Any

INTENTS = ("search", "similar", "lookup", "count", "predict", "knowledge", "out_of_scope")
OPS = (">", ">=", "<", "<=", "==")
AGG_FUNCS = ("count", "avg", "min", "max")


@dataclass
class Constraint:
    column: str
    op: str
    value: float

    def text(self) -> str:
        return f"{self.column} {self.op} {self.value:g}"


@dataclass
class Objective:
    column: str
    direction: str  # "max" | "min"

    def text(self) -> str:
        return f"{self.direction} {self.column}"


@dataclass
class QueryPlan:
    intent: str = "search"
    constraints: list[Constraint] = field(default_factory=list)
    objectives: list[Objective] = field(default_factory=list)
    metals: list[str] = field(default_factory=list)
    open_metal_site: bool | None = None
    application: str | None = None
    gases: list[str] = field(default_factory=list)          # for gas separation
    mof_ids: list[str] = field(default_factory=list)
    aggregate: dict[str, Any] | None = None                 # {"func": "count"|"avg"|"min"|"max", "column": str|None}
    target_property: str | None = None                      # for predict
    feature_values: dict[str, float] = field(default_factory=dict)  # for predict on user-given descriptors
    limit: int = 5
    limit_explicit: bool = False
    notes: list[str] = field(default_factory=list)          # assumptions / corrections shown to the user
    source: str = "rules"                                   # rules | llm | llm+rules

    def to_dict(self) -> dict:
        return asdict(self)

    @staticmethod
    def from_dict(d: dict) -> "QueryPlan":
        d = dict(d)
        d["constraints"] = [c if isinstance(c, Constraint) else Constraint(**c) for c in d.get("constraints", [])]
        d["objectives"] = [o if isinstance(o, Objective) else Objective(**o) for o in d.get("objectives", [])]
        allowed = set(QueryPlan.__dataclass_fields__)
        return QueryPlan(**{k: v for k, v in d.items() if k in allowed})

    def summary(self) -> str:
        parts = [f"intent={self.intent}"]
        if self.application:
            parts.append(f"application={self.application}")
        if self.constraints:
            parts.append("where " + " AND ".join(c.text() for c in self.constraints))
        if self.metals:
            parts.append("metal in " + "/".join(self.metals))
        if self.open_metal_site is not None:
            parts.append("open metal site=" + ("yes" if self.open_metal_site else "no"))
        if self.objectives:
            parts.append("optimise " + ", ".join(o.text() for o in self.objectives))
        if self.mof_ids:
            parts.append("MOFs " + ", ".join(self.mof_ids[:5]))
        if self.aggregate:
            parts.append(f"aggregate {self.aggregate.get('func')}({self.aggregate.get('column') or '*'})")
        if self.target_property:
            parts.append(f"predict {self.target_property}")
        parts.append(f"limit {self.limit}")
        return "; ".join(parts)
