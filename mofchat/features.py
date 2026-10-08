"""Feature preprocessing shared by training, inference and evaluation."""

from __future__ import annotations

import json
from dataclasses import dataclass, field
from pathlib import Path

import numpy as np
import pandas as pd

# Descriptors used for the self-supervised MOF embedding (duplicates already removed in the DB).
SSL_NUMERIC = ["LCD", "PLD", "LFPD", "Density", "Surface_Area", "ASA_vol", "Void_Fraction",
               "Pore_Volume", "NASA_grav", "NAV"]
SSL_CATEGORICAL = ["Metal_Group", "Has_OMS"]

# Supervised surrogate models: target -> input features.
#  * Surface_Area: excludes ASA_vol (= ASA * density) and the non-accessible areas/volumes
#    computed in the same Zeo++ run, so the model only sees cheap geometric descriptors.
#  * Void_Fraction: excludes Pore_Volume (= VF / density, would leak the target).
PROPERTY_TARGETS = {
    "Surface_Area": {"features": ["Density", "LCD", "PLD", "LFPD", "Void_Fraction", "Pore_Volume"],
                     "hurdle": True},
    "Void_Fraction": {"features": ["Density", "LCD", "PLD", "LFPD"], "hurdle": False},
}

MIN_METAL_COUNT = 30


def primary_metal(metal_type: str) -> str:
    return str(metal_type).split(",")[0] if metal_type else "none"


@dataclass
class Preprocessor:
    numeric: list[str]
    categorical: list[str] = field(default_factory=list)
    log_cols: list[str] = field(default_factory=list)
    mean: dict[str, float] = field(default_factory=dict)
    std: dict[str, float] = field(default_factory=dict)
    vocab: dict[str, list[str]] = field(default_factory=dict)

    @staticmethod
    def default_log_cols(cols: list[str]) -> list[str]:
        return [c for c in cols if c != "Void_Fraction"]

    def _num_frame(self, df: pd.DataFrame) -> pd.DataFrame:
        X = df[self.numeric].astype(float).copy()
        for c in self.log_cols:
            X[c] = np.log1p(X[c].clip(lower=0))
        return X

    def _cat_frame(self, df: pd.DataFrame) -> pd.DataFrame:
        out = pd.DataFrame(index=df.index)
        for c in self.categorical:
            if c == "Metal_Group":
                out[c] = df["Metal_Type"].map(primary_metal)
            else:
                out[c] = df[c].astype(str)
        return out

    def fit(self, df: pd.DataFrame) -> "Preprocessor":
        X = self._num_frame(df)
        self.mean = X.mean().to_dict()
        self.std = X.std().replace(0, 1).to_dict()
        C = self._cat_frame(df)
        for c in self.categorical:
            counts = C[c].value_counts()
            keep = sorted(counts[counts >= MIN_METAL_COUNT].index) if c == "Metal_Group" else sorted(counts.index)
            self.vocab[c] = ["<other>"] + list(keep)
        return self

    def transform_num(self, df: pd.DataFrame) -> np.ndarray:
        X = self._num_frame(df)
        return ((X - pd.Series(self.mean)) / pd.Series(self.std))[self.numeric].to_numpy(np.float32)

    def inverse_num(self, Z: np.ndarray) -> pd.DataFrame:
        X = pd.DataFrame(Z, columns=self.numeric) * pd.Series(self.std) + pd.Series(self.mean)
        for c in self.log_cols:
            X[c] = np.expm1(X[c])
        return X

    def transform_cat(self, df: pd.DataFrame) -> np.ndarray:
        if not self.categorical:
            return np.zeros((len(df), 0), dtype=np.int64)
        C = self._cat_frame(df)
        cols = []
        for c in self.categorical:
            lookup = {v: i for i, v in enumerate(self.vocab[c])}
            cols.append(C[c].map(lambda v: lookup.get(v, 0)).to_numpy(np.int64))
        return np.stack(cols, axis=1)

    def cardinalities(self) -> tuple[int, ...]:
        return tuple(len(self.vocab[c]) for c in self.categorical)

    def save(self, path: Path) -> None:
        Path(path).write_text(json.dumps(self.__dict__, indent=2))

    @staticmethod
    def load(path: Path) -> "Preprocessor":
        return Preprocessor(**json.loads(Path(path).read_text()))
