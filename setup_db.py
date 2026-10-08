"""
setup_db.py - ETL: CoRE-MOF spreadsheet -> SQLite (data/coremof.db)

  python setup_db.py

Tables created
  materials    one row per MOF, all useful descriptors with clean column names
  mof_metals   (MOF_ID, Metal) - one row per metal, so multi-metal MOFs can be queried exactly
  columns_doc  column name, label, unit, description (used by the app and the LLM prompts)

Data-quality checks (asserted, printed in the log):
  * 'Accessible volume volume fraction' == 'void fraction'           -> duplicate, dropped
  * 'Accessible volume (cm^3/g)' == 'Accessible pore volume (cm^3/g)' -> duplicate, dropped
  * Pore_Volume == Void_Fraction / Density                           -> derived, kept for convenience
  * ASA_vol == Surface_Area * Density                                 -> derived, kept for convenience
  * Surface_Area == 0  <=>  PLD < 3.31 A (probe cannot enter)         -> physical, documented
"""

import sqlite3
import sys
import unicodedata

import numpy as np
import pandas as pd

from mofchat.config import COLUMNS, DATASET_PATH, DB_PATH, DUPLICATE_SOURCE_COLUMNS, PROBE_DIAMETER_A


def _norm(s: str) -> str:
    # The spreadsheet uses U+212B (ANGSTROM SIGN); NFKC maps it to U+00C5.
    return unicodedata.normalize("NFKC", str(s)).strip()


def load_raw(path=DATASET_PATH) -> pd.DataFrame:
    df = pd.read_excel(path, engine="openpyxl")
    df.columns = [_norm(c) for c in df.columns]
    return df


def check_quality(raw: pd.DataFrame) -> list[str]:
    report = [f"rows={len(raw)}, columns={raw.shape[1]}",
              f"missing values={int(raw.isna().sum().sum())}",
              f"duplicate rows={int(raw.duplicated().sum())}",
              f"duplicate MOF names={int(raw['name'].duplicated().sum())}"]
    for dup, kept in DUPLICATE_SOURCE_COLUMNS.items():
        same = np.allclose(raw[dup], raw[kept])
        assert same, f"{dup} is no longer identical to {kept}"
        report.append(f"'{dup}' identical to '{kept}' -> dropped")
    vf, rho = raw["void fraction"], raw["Density (cm^3/g)"]
    pv = raw["Accessible pore volume (cm^3/g)"]
    rel = np.max(np.abs(pv - vf / rho) / np.maximum(pv, 1e-9))
    report.append(f"Pore volume == void fraction / density (max rel. error {rel:.1e})")
    asa_g, asa_v = raw["Accessible Surface Area (m^2/g)"], raw["Accessible Surface Area (m^2/cm^3)"]
    report.append(f"ASA_vol == ASA_grav * density (max abs. error {np.max(np.abs(asa_v - asa_g * rho)):.3f} m2/cm3)")
    pld = raw[_norm("Pore limiting diameter (Å)")]
    zero = asa_g == 0
    report.append(f"Surface area == 0 for {int(zero.sum())} MOFs; all have PLD < {PROBE_DIAMETER_A} A: "
                  f"{bool((pld[zero] < PROBE_DIAMETER_A + 0.01).all())}; "
                  f"all MOFs with PLD >= {PROBE_DIAMETER_A + 0.01} A have ASA > 0: "
                  f"{bool((asa_g[pld >= PROBE_DIAMETER_A + 0.01] > 0).all())}")
    return report


def transform(raw: pd.DataFrame) -> tuple[pd.DataFrame, pd.DataFrame]:
    mapping = {_norm(c.source): c.name for c in COLUMNS if c.source}
    df = raw[list(mapping)].rename(columns=mapping).copy()
    df["MOF_ID"] = df["MOF_ID"].astype(str).str.strip()
    df["Metal_Type"] = df["Metal_Type"].fillna("").astype(str).str.replace(" ", "")
    df["OMS_Type"] = df["OMS_Type"].fillna("").astype(str).str.strip().str.replace(" ", "")
    df["Has_OMS"] = (df["Has_OMS"].astype(str).str.strip().str.lower() == "yes").astype(int)
    for c in [c.name for c in COLUMNS if c.kind == "numeric"]:
        df[c] = pd.to_numeric(df[c], errors="raise").astype(float)

    metals = (df[["MOF_ID", "Metal_Type"]]
              .assign(Metal=df["Metal_Type"].str.split(","))
              .explode("Metal")[["MOF_ID", "Metal"]])
    metals = metals[metals["Metal"].str.len() > 0].drop_duplicates()
    return df, metals


def write_db(df: pd.DataFrame, metals: pd.DataFrame, db_path=DB_PATH) -> None:
    db_path.parent.mkdir(parents=True, exist_ok=True)
    if db_path.exists():
        db_path.unlink()
    conn = sqlite3.connect(db_path)
    df.to_sql("materials", conn, index=False)
    metals.to_sql("mof_metals", conn, index=False)
    doc = pd.DataFrame([{"name": c.name, "label": c.label, "unit": c.unit, "description": c.description,
                         "kind": c.kind} for c in COLUMNS])
    doc.to_sql("columns_doc", conn, index=False)
    cur = conn.cursor()
    cur.execute("CREATE UNIQUE INDEX idx_materials_id ON materials(MOF_ID)")
    cur.execute("CREATE INDEX idx_metals_metal ON mof_metals(Metal)")
    for col in ["Surface_Area", "Density", "Void_Fraction", "Pore_Volume", "LCD", "PLD"]:
        cur.execute(f"CREATE INDEX idx_materials_{col.lower()} ON materials({col})")
    conn.commit()
    conn.close()


def main() -> int:
    if not DATASET_PATH.exists():
        print(f"Dataset not found: {DATASET_PATH}")
        return 1
    print(f"Loading {DATASET_PATH} ...")
    raw = load_raw()
    for line in check_quality(raw):
        print("  [check]", line)
    df, metals = transform(raw)
    write_db(df, metals)
    print(f"\nWrote {DB_PATH}: materials={len(df)} rows x {df.shape[1]} cols, "
          f"mof_metals={len(metals)} rows, {metals['Metal'].nunique()} distinct metals")
    print(df.head(3).to_string())
    return 0


if __name__ == "__main__":
    sys.exit(main())
