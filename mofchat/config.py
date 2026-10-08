"""
Central configuration for MOFChat.

Every module (ETL, planner, validator, SQL builder, models, app, docs) reads
column names, units, aliases and physical ranges from here, so there is one
source of truth for the database schema.
"""

from __future__ import annotations

import os
from dataclasses import dataclass, field
from pathlib import Path

# --------------------------------------------------------------------------
# Paths (all relative to the project root, overridable with env variables)
# --------------------------------------------------------------------------
PROJECT_ROOT = Path(__file__).resolve().parent.parent
DATA_DIR = PROJECT_ROOT / "data"
ARTIFACTS_DIR = PROJECT_ROOT / "artifacts"
KNOWLEDGE_DIR = PROJECT_ROOT / "knowledge"

DATASET_PATH = Path(os.environ.get("MOFCHAT_DATASET", DATA_DIR / "coremof.xlsx"))
DB_PATH = Path(os.environ.get("MOFCHAT_DB", DATA_DIR / "coremof.db"))

FT_EMBED_DIR = ARTIFACTS_DIR / "ft_embeddings"        # SSL FT-Transformer + FAISS index
PROPERTY_MODEL_DIR = ARTIFACTS_DIR / "property_models"  # surrogate models + SHAP
KNOWLEDGE_INDEX_DIR = ARTIFACTS_DIR / "knowledge_index" # literature / domain RAG index
EVAL_DIR = ARTIFACTS_DIR / "eval"                       # benchmark + metrics + figures

PAPERS_DIRS = [KNOWLEDGE_DIR / "papers"]  # PDFs to ingest (ChatMOF.pdf)

# --------------------------------------------------------------------------
# Models
# --------------------------------------------------------------------------
# Language models: see mofchat/llm.py (model registry; keys and MOFCHAT_MODEL in .env)
TEXT_EMBEDDING_MODEL = "all-MiniLM-L6-v2"
RANDOM_SEED = 42

# Zeo++ probe used for the CoRE-MOF geometric descriptors in this table
# (ChatMOF Methods: "hard sphere model with a diameter of 3.31 Å (nitrogen)").
PROBE_DIAMETER_A = 3.31


# --------------------------------------------------------------------------
# Column registry
# --------------------------------------------------------------------------
@dataclass(frozen=True)
class Column:
    name: str                 # column name in SQLite
    source: str | None        # column name in coremof.xlsx (None = derived)
    label: str                # human readable label
    unit: str
    description: str
    kind: str = "numeric"     # numeric | categorical | id
    aliases: tuple[str, ...] = ()
    valid_range: tuple[float, float] | None = None  # physically plausible range for user values
    queryable: bool = True


COLUMNS: list[Column] = [
    Column("MOF_ID", "name", "MOF ID", "", "CSD refcode (or source-file name) of the structure.", kind="id"),
    Column("LCD", "Largest cavity diameter (Å)", "Largest cavity diameter", "Å",
           "Diameter of the largest sphere that fits anywhere inside the pores.",
           aliases=("largest cavity diameter", "lcd", "cavity diameter", "cavity size",
                    "pore size", "pore diameter", "largest pore"),
           valid_range=(0.0, 150.0)),
    Column("PLD", "Pore limiting diameter (Å)", "Pore limiting diameter", "Å",
           "Diameter of the largest sphere that can pass through the pore network (the narrowest window).",
           aliases=("pore limiting diameter", "pld", "pore aperture", "aperture", "window size",
                    "limiting diameter", "pore window"),
           valid_range=(0.0, 150.0)),
    Column("LFPD", "Largest free pore diameter (Å)", "Largest free pore diameter", "Å",
           "Diameter of the largest sphere that can travel along the free path of the pore network.",
           aliases=("largest free pore diameter", "lfpd", "free pore diameter", "largest free sphere"),
           valid_range=(0.0, 150.0)),
    Column("Density", "Density (cm^3/g)", "Density", "g/cm³",
           "Crystal density. (The source spreadsheet labels the unit as cm^3/g; the values are g/cm³.)",
           aliases=("density", "crystal density"),
           valid_range=(0.0, 25.0)),
    Column("ASA_vol", "Accessible Surface Area (m^2/cm^3)", "Volumetric accessible surface area", "m²/cm³",
           "Probe-accessible surface area per unit volume of crystal.",
           aliases=("volumetric surface area", "volumetric accessible surface area",
                    "surface area per volume", "volumetric asa"),
           valid_range=(0.0, 6000.0)),
    Column("Surface_Area", "Accessible Surface Area (m^2/g)", "Accessible surface area", "m²/g",
           "Probe-accessible (gravimetric) surface area per gram of material.",
           aliases=("accessible surface area", "gravimetric surface area", "surface area", "asa"),
           valid_range=(0.0, 12000.0)),
    Column("NASA_vol", "Nonaccessible Surface Area (m^2/cm^3)", "Non-accessible surface area (vol.)", "m²/cm³",
           "Surface area of pockets the probe cannot reach from the open network, per volume.",
           aliases=("volumetric nonaccessible surface area", "volumetric non-accessible surface area"),
           valid_range=(0.0, 6000.0)),
    Column("NASA_grav", "Nonaccessible surface area (m^2/g)", "Non-accessible surface area", "m²/g",
           "Surface area of pockets the probe cannot reach from the open network, per gram.",
           aliases=("nonaccessible surface area", "non-accessible surface area", "non accessible surface area"),
           valid_range=(0.0, 12000.0)),
    Column("Void_Fraction", "void fraction", "Void fraction", "",
           "Fraction of the crystal volume that is probe-accessible void (0-1).",
           aliases=("void fraction", "accessible volume fraction", "porosity", "vf"),
           valid_range=(0.0, 1.0)),
    Column("Pore_Volume", "Accessible pore volume (cm^3/g)", "Accessible pore volume", "cm³/g",
           "Probe-accessible pore volume per gram (equals void fraction / density).",
           aliases=("accessible pore volume", "pore volume", "pv"),
           valid_range=(0.0, 30.0)),
    Column("NAV", "Nonaccessible Volume (cm^3/g)", "Non-accessible volume", "cm³/g",
           "Pore volume in pockets the probe cannot reach, per gram.",
           aliases=("nonaccessible volume", "non-accessible volume", "non accessible volume"),
           valid_range=(0.0, 30.0)),
    Column("Metal_Type", "Metal type", "Metal(s)", "", "Metal element(s) in the framework, comma separated.",
           kind="categorical", aliases=("metal", "metal type", "metals")),
    Column("Has_OMS", "Has open metal site", "Open metal site", "", "1 if the framework has an open (coordinatively unsaturated) metal site.",
           kind="categorical", aliases=("open metal site", "open metal sites", "oms")),
    Column("OMS_Type", "Type of open metal", "Open-metal element(s)", "", "Element(s) that form the open metal sites.",
           kind="categorical", aliases=("type of open metal",)),
]

COLUMN_BY_NAME: dict[str, Column] = {c.name: c for c in COLUMNS}
NUMERIC_COLUMNS: list[str] = [c.name for c in COLUMNS if c.kind == "numeric"]

# Source columns that are exact duplicates of a kept column (verified in setup_db.py).
DUPLICATE_SOURCE_COLUMNS = {
    "Accessible volume volume fraction": "void fraction",
    "Accessible volume (cm^3/g)": "Accessible pore volume (cm^3/g)",
}

# Columns shown by default in result tables.
DISPLAY_COLUMNS = ["MOF_ID", "Surface_Area", "ASA_vol", "Density", "Void_Fraction",
                   "Pore_Volume", "LCD", "PLD", "Metal_Type", "Has_OMS"]


def alias_table() -> list[tuple[str, str]]:
    """(alias, column) pairs sorted longest-first so 'volumetric surface area'
    wins over 'surface area' during matching."""
    pairs = []
    for c in COLUMNS:
        if c.kind != "numeric":
            continue
        for a in (c.name.lower(),) + c.aliases:
            pairs.append((a.lower(), c.name))
    return sorted(set(pairs), key=lambda p: -len(p[0]))


def resolve_column(text: str) -> str | None:
    """Map a free-text property name or alias to a numeric column name."""
    t = " ".join(str(text).lower().replace("_", " ").split())
    for c in COLUMNS:
        if c.kind == "numeric" and t == c.name.lower().replace("_", " "):
            return c.name
    for alias, col in alias_table():
        if t == alias:
            return col
    return None


def unit_of(col: str) -> str:
    c = COLUMN_BY_NAME.get(col)
    return c.unit if c else ""


# --------------------------------------------------------------------------
# Gas kinetic diameters (Å). Values as commonly tabulated from
# D. W. Breck, "Zeolite Molecular Sieves" (Wiley, 1974); sources differ by
# ~0.1 Å for some gases (e.g. Xe is quoted as 3.96-4.1 Å).
# --------------------------------------------------------------------------
KINETIC_DIAMETERS_A = {
    "H2O": 2.65, "H2": 2.89, "CO2": 3.30, "Ar": 3.40, "O2": 3.46, "Kr": 3.60,
    "N2": 3.64, "CO": 3.76, "CH4": 3.80, "Xe": 4.10,
}
GAS_ALIASES = {
    "water": "H2O", "h2o": "H2O", "hydrogen": "H2", "h2": "H2", "co2": "CO2",
    "carbon dioxide": "CO2", "argon": "Ar", "ar": "Ar", "oxygen": "O2", "o2": "O2",
    "krypton": "Kr", "kr": "Kr", "nitrogen": "N2", "n2": "N2", "carbon monoxide": "CO",
    "co": "CO", "methane": "CH4", "ch4": "CH4", "natural gas": "CH4", "xenon": "Xe", "xe": "Xe",
}


# --------------------------------------------------------------------------
# Application presets: transparent screening heuristics (NOT adsorption
# simulations). Each preset is documented in knowledge/applications.md.
# --------------------------------------------------------------------------
@dataclass
class ApplicationPreset:
    key: str
    label: str
    keywords: tuple[str, ...]
    constraints: list[tuple[str, str, float]] = field(default_factory=list)
    objectives: list[tuple[str, str]] = field(default_factory=list)
    open_metal_site: bool | None = None
    rationale: str = ""


APPLICATIONS: dict[str, ApplicationPreset] = {
    "h2_storage": ApplicationPreset(
        "h2_storage", "Hydrogen storage",
        ("hydrogen storage", "h2 storage", "store hydrogen", "storing hydrogen", "hydrogen uptake"),
        constraints=[("PLD", ">=", KINETIC_DIAMETERS_A["H2"])],
        objectives=[("Surface_Area", "max"), ("Void_Fraction", "max")],
        rationale=("Cryogenic H2 uptake scales roughly with accessible surface area (Chahine's rule), "
                   "so maximise gravimetric surface area and void fraction; pores must admit H2 (2.89 Å)."),
    ),
    "ch4_storage": ApplicationPreset(
        "ch4_storage", "Methane storage",
        ("methane storage", "ch4 storage", "natural gas storage", "store methane", "storing methane", "methane uptake"),
        constraints=[("PLD", ">=", KINETIC_DIAMETERS_A["CH4"])],
        objectives=[("ASA_vol", "max"), ("Void_Fraction", "max")],
        rationale=("Volumetric storage favours a high surface area per unit volume together with enough "
                   "free volume; pores must admit CH4 (3.80 Å)."),
    ),
    "co2_capture": ApplicationPreset(
        "co2_capture", "CO2 capture",
        ("co2 capture", "carbon capture", "capture co2", "capturing co2", "co2 adsorption", "adsorb co2",
         "carbon dioxide capture", "co2 uptake"),
        constraints=[("PLD", ">=", KINETIC_DIAMETERS_A["CO2"])],
        objectives=[("ASA_vol", "max"), ("LCD", "min")],
        open_metal_site=True,
        rationale=("At low CO2 partial pressure, binding strength matters most: open metal sites and "
                   "narrow (but accessible, >3.30 Å) pores increase affinity, and a high volumetric surface "
                   "area gives more sites per volume."),
    ),
    "gas_separation": ApplicationPreset(
        "gas_separation", "Gas separation (size sieving)",
        ("separation", "separate", "separating", "sieving", "selective"),
        rationale=("Molecular sieving: a pore limiting diameter between the kinetic diameters of the two "
                   "gases lets the smaller molecule pass and blocks the larger one."),
    ),
    "catalysis": ApplicationPreset(
        "catalysis", "Heterogeneous catalysis",
        ("catalysis", "catalyst", "catalytic"),
        constraints=[("PLD", ">=", 5.0)],
        objectives=[("Surface_Area", "max"), ("PLD", "max")],
        open_metal_site=True,
        rationale=("Open metal sites can act as Lewis-acid sites, and wide windows (>5 Å) and large surface "
                   "area help reactants reach them."),
    ),
}


# Well-known MOFs and their CSD refcodes (only those verified to be in the table
# are used at runtime; see mofchat/db.py).
COMMON_NAMES = {
    "hkust-1": "FIQCEN", "cu-btc": "FIQCEN", "mof-199": "FIQCEN",
    "mof-5": "SAHYIK", "irmof-1": "SAHYIK",
    "zif-8": "OFERUN",
    "uio-66": "RUBTAK",
}

# Planner settings
DEFAULT_LIMIT = 5
MAX_LIMIT = 50
