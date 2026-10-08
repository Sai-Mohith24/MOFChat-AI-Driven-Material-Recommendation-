"""
Multi-objective ranking with the NSGA-II selection operator
(Deb, Pratap, Agarwal & Meyarivan, IEEE Trans. Evol. Comput. 6(2), 182-197, 2002).

MOFChat ranks a *finite* candidate set (MOFs that already exist in the
database), so the part of NSGA-II that applies is its selection step:

  1. non-dominated sorting  -> Pareto fronts F1, F2, ... (F1 = no candidate is better in every objective)
  2. crowding distance       -> inside a front, prefer candidates in sparsely populated regions,
                                giving a diverse set of trade-offs instead of near-duplicates

Top-k selection fills front by front; the last front that does not fit
completely is truncated by descending crowding distance - exactly how
NSGA-II builds the next parent population.
"""

from __future__ import annotations

import numpy as np
import pandas as pd


def _to_minimisation(values: np.ndarray, directions: list[str]) -> np.ndarray:
    F = np.asarray(values, dtype=float).copy()
    for j, d in enumerate(directions):
        if d == "max":
            F[:, j] = -F[:, j]
        elif d != "min":
            raise ValueError(f"direction must be 'max' or 'min', got {d!r}")
    return F


def _dominated_mask(F: np.ndarray, active: np.ndarray, chunk: int = 512) -> np.ndarray:
    """For each active point, is it dominated by any other active point? (minimisation)"""
    idx = np.flatnonzero(active)
    P = F[idx]
    dominated = np.zeros(len(idx), dtype=bool)
    for s in range(0, len(idx), chunk):
        block = P[s:s + chunk]                                   # (b, m)
        le = (P[None, :, :] <= block[:, None, :]).all(axis=2)   # other <= me in all objectives
        lt = (P[None, :, :] < block[:, None, :]).any(axis=2)    # other <  me in at least one
        dominated[s:s + chunk] = (le & lt).any(axis=1)
    out = np.zeros(len(F), dtype=bool)
    out[idx] = dominated
    return out


def _front_2d(F: np.ndarray, active: np.ndarray) -> np.ndarray:
    """First front of the active points for two objectives in O(n log n):
    sort by f1 (then f2) and keep points that improve the running minimum of f2."""
    idx = np.flatnonzero(active)
    f1, f2 = F[idx, 0], F[idx, 1]
    order = np.lexsort((f2, f1))
    front, best, last = [], np.inf, None
    for i in order:
        pt = (f1[i], f2[i])
        if f2[i] < best:
            front.append(idx[i])
            best, last = f2[i], pt
        elif pt == last:                       # exact duplicate of a front point: not dominated
            front.append(idx[i])
    return np.array(front, dtype=int)


def non_dominated_fronts(F: np.ndarray, max_points: int | None = None) -> list[np.ndarray]:
    """Peel Pareto fronts (minimisation). Stops once `max_points` points are covered."""
    n = len(F)
    if F.shape[1] == 2:
        active = np.ones(n, dtype=bool)
        fronts, covered = [], 0
        while active.any():
            front = _front_2d(F, active)
            fronts.append(front)
            active[front] = False
            covered += len(front)
            if max_points is not None and covered >= max_points:
                break
        return fronts
    active = np.ones(n, dtype=bool)
    fronts, covered = [], 0
    while active.any():
        dominated = _dominated_mask(F, active)
        front = np.flatnonzero(active & ~dominated)
        fronts.append(front)
        active[front] = False
        covered += len(front)
        if max_points is not None and covered >= max_points:
            break
    return fronts


def crowding_distance(F: np.ndarray) -> np.ndarray:
    """Crowding distance of each row of F (one front). Boundary points get +inf."""
    n, m = F.shape
    if n <= 2:
        return np.full(n, np.inf)
    dist = np.zeros(n)
    for j in range(m):
        order = np.argsort(F[:, j], kind="mergesort")
        col = F[order, j]
        span = col[-1] - col[0]
        dist[order[0]] = dist[order[-1]] = np.inf
        if span > 0:
            dist[order[1:-1]] += (col[2:] - col[:-2]) / span
    return dist


def nsga2_rank(df: pd.DataFrame, objectives: list[tuple[str, str]], k: int,
               floor_quantile: float = 0.25) -> pd.DataFrame:
    """
    Return the top-k rows of `df` chosen by NSGA-II selection, with columns
    `pareto_front` (1 = best) and `crowding` added. Rows with missing objective
    values are ignored.

    floor_quantile: before sorting, drop candidates that fall in the worst
    `floor_quantile` of the candidates for ANY objective (if at least k remain).
    NSGA-II deliberately keeps extreme trade-offs (infinite crowding distance at
    the ends of a front); for recommendations an extreme such as "smallest pores
    but almost no surface area" is useless, so this satisficing screen removes
    degenerate extremes while keeping the Pareto logic.
    """
    cols = [c for c, _ in objectives]
    dirs = [d for _, d in objectives]
    work = df.dropna(subset=cols).reset_index(drop=True)
    if floor_quantile and len(work) > k:
        keep = np.ones(len(work), dtype=bool)
        for c, d in objectives:
            q = work[c].quantile(floor_quantile if d == "max" else 1 - floor_quantile)
            keep &= (work[c] >= q).to_numpy() if d == "max" else (work[c] <= q).to_numpy()
        if keep.sum() >= k:
            work = work[keep].reset_index(drop=True)
    if work.empty:
        return work.assign(pareto_front=pd.Series(dtype=int), crowding=pd.Series(dtype=float))
    F = _to_minimisation(work[cols].to_numpy(), dirs)
    # Normalise so crowding distance is scale-free across objectives.
    rng = F.max(axis=0) - F.min(axis=0)
    Fn = (F - F.min(axis=0)) / np.where(rng > 0, rng, 1.0)

    picked, front_no, crowd = [], [], []
    for r, front in enumerate(non_dominated_fronts(Fn, max_points=k), start=1):
        cd = crowding_distance(Fn[front])
        order = np.argsort(-cd, kind="mergesort")
        take = front[order][: max(0, k - len(picked))]
        picked.extend(take.tolist())
        front_no.extend([r] * len(take))
        crowd.extend(cd[order][: len(take)].tolist())
        if len(picked) >= k:
            break
    out = work.iloc[picked].copy()
    out["pareto_front"] = front_no
    out["crowding"] = crowd
    return out.reset_index(drop=True)


def pareto_front_mask(df: pd.DataFrame, objectives: list[tuple[str, str]]) -> np.ndarray:
    """Boolean mask of rows on the first Pareto front (for plotting)."""
    cols = [c for c, _ in objectives]
    F = _to_minimisation(df[cols].to_numpy(), [d for _, d in objectives])
    return ~_dominated_mask(F, np.ones(len(F), dtype=bool))
