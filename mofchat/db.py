"""Read-only access to the CoRE-MOF SQLite database."""

from __future__ import annotations

import re
import sqlite3
from functools import lru_cache
from pathlib import Path

import pandas as pd

from .config import COMMON_NAMES, DB_PATH

ELEMENT_NAMES = {
    "Ag": "silver", "Al": "aluminium", "As": "arsenic", "Au": "gold", "Ba": "barium", "Be": "beryllium",
    "Bi": "bismuth", "Ca": "calcium", "Cd": "cadmium", "Ce": "cerium", "Co": "cobalt", "Cr": "chromium",
    "Cs": "caesium", "Cu": "copper", "Dy": "dysprosium", "Er": "erbium", "Eu": "europium", "Fe": "iron",
    "Ga": "gallium", "Gd": "gadolinium", "Ge": "germanium", "Hf": "hafnium", "Hg": "mercury",
    "Ho": "holmium", "In": "indium", "Ir": "iridium", "K": "potassium", "La": "lanthanum", "Li": "lithium",
    "Lu": "lutetium", "Mg": "magnesium", "Mn": "manganese", "Mo": "molybdenum", "Na": "sodium",
    "Nb": "niobium", "Nd": "neodymium", "Ni": "nickel", "Np": "neptunium", "Pb": "lead", "Pd": "palladium",
    "Pr": "praseodymium", "Pt": "platinum", "Pu": "plutonium", "Rb": "rubidium", "Re": "rhenium",
    "Rh": "rhodium", "Ru": "ruthenium", "Sb": "antimony", "Sc": "scandium", "Si": "silicon", "Sm": "samarium",
    "Sn": "tin", "Sr": "strontium", "Tb": "terbium", "Te": "tellurium", "Th": "thorium", "Ti": "titanium",
    "Tm": "thulium", "U": "uranium", "V": "vanadium", "W": "tungsten", "Y": "yttrium", "Yb": "ytterbium",
    "Zn": "zinc", "Zr": "zirconium",
}
EXTRA_ELEMENT_ALIASES = {"aluminum": "Al", "cesium": "Cs"}


def connect(db_path: Path | str = DB_PATH) -> sqlite3.Connection:
    """Open the database read-only, so nothing the agent runs can modify it."""
    path = Path(db_path)
    if not path.exists():
        raise FileNotFoundError(f"{path} not found - run `python setup_db.py` first.")
    return sqlite3.connect(f"file:{path}?mode=ro", uri=True, check_same_thread=False)


def query_df(sql: str, params: tuple | list = (), db_path: Path | str = DB_PATH) -> pd.DataFrame:
    conn = connect(db_path)
    try:
        return pd.read_sql_query(sql, conn, params=list(params))
    finally:
        conn.close()


@lru_cache(maxsize=4)
def load_materials(db_path: str = str(DB_PATH)) -> pd.DataFrame:
    return query_df("SELECT * FROM materials", db_path=db_path)


@lru_cache(maxsize=4)
def id_index(db_path: str = str(DB_PATH)) -> dict[str, str]:
    """Upper-cased MOF ID -> exact MOF ID."""
    ids = load_materials(db_path)["MOF_ID"]
    return {i.upper(): i for i in ids}


@lru_cache(maxsize=4)
def metal_list(db_path: str = str(DB_PATH)) -> list[str]:
    return query_df("SELECT DISTINCT Metal FROM mof_metals ORDER BY Metal", db_path=db_path)["Metal"].tolist()


def resolve_metal(token: str, db_path: str = str(DB_PATH)) -> str | None:
    t = token.strip()
    metals = set(metal_list(db_path))
    if t in metals:
        return t
    if t.capitalize() in metals and len(t) <= 2:
        return t.capitalize()
    name_map = {v: k for k, v in ELEMENT_NAMES.items()} | EXTRA_ELEMENT_ALIASES
    sym = name_map.get(t.lower())
    return sym if sym in metals else None


def resolve_mof_id(token: str, db_path: str = str(DB_PATH)) -> list[str]:
    """Exact ID (case-insensitive), common name (HKUST-1 -> FIQCEN), or refcode family
    (RUBTAK -> RUBTAK01..09). Returns [] when nothing matches."""
    idx = id_index(db_path)
    t = token.strip().strip(".,;:!?\"'()[]")
    if not t:
        return []
    if t.upper() in idx:
        return [idx[t.upper()]]
    code = COMMON_NAMES.get(t.lower())
    if code:
        t = code
        if code in idx:
            return [idx[code]]
    if re.fullmatch(r"[A-Za-z]{6}", t):
        fam = sorted(v for k, v in idx.items() if re.fullmatch(re.escape(t.upper()) + r"\d{2}", k))
        return fam
    return []


def get_rows(ids: list[str], db_path: Path | str = DB_PATH) -> pd.DataFrame:
    if not ids:
        return load_materials(str(db_path)).iloc[0:0]
    marks = ",".join("?" * len(ids))
    df = query_df(f"SELECT * FROM materials WHERE MOF_ID IN ({marks})", ids, db_path)
    order = {m: i for i, m in enumerate(ids)}
    return df.sort_values("MOF_ID", key=lambda s: s.map(order)).reset_index(drop=True)
