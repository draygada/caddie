"""Part 06: online recommendation at a continuous point (Ch 9.2 rollout, Ch 8.4 leaf).

    Q(x, a) = (1/m) sum_j [ r_j + U_interp(x'_j) ]      a* = argmax_a Q(x, a)

One shot of lookahead from the continuous position, then the offline value grid at
the landing by bilinear interpolation. The reference that ``app/src/lib/rollout.ts``
must match on a fixed seed.
"""

from __future__ import annotations

import logging

import numpy as np
from scipy.spatial import cKDTree

log = logging.getLogger(__name__)

# --- slice 1: bilinear ------------------------------------------------------------------------

_BILINEAR_CACHE: dict[int, tuple[np.ndarray, cKDTree, np.ndarray]] = {}


def _nearest_finite(
    U: np.ndarray, rows: int, cols: int, cell_m: float
) -> tuple[cKDTree, np.ndarray]:
    """KD-tree over the centres of finite cells and their values, cached by array id."""
    key = id(U)
    hit = _BILINEAR_CACHE.get(key)
    if hit is not None and hit[0] is U:
        return hit[1], hit[2]
    finite = np.flatnonzero(np.isfinite(U))
    if finite.size == 0:
        raise ValueError("value grid has no finite cell")
    r, c = np.divmod(finite, cols)
    tree = cKDTree(np.column_stack(((c + 0.5) * cell_m, (r + 0.5) * cell_m)))
    _BILINEAR_CACHE[key] = (U, tree, U[finite])
    return tree, U[finite]


def bilinear(
    U: np.ndarray,
    rows: int,
    cols: int,
    cell_m: float,
    x: float | np.ndarray,
    y: float | np.ndarray,
) -> np.ndarray:
    """Alg 8.6 on the cell-centre lattice, clamped to the outer centres.

    A NaN neighbour takes the value of the nearest finite neighbour of the four. When
    all four are NaN (deep in OUT), the value is the nearest finite cell's value plus one
    stroke, the penalty for being off the hole.
    """
    U = np.asarray(U, dtype=float).reshape(-1)
    shape = np.broadcast(np.asarray(x), np.asarray(y)).shape
    x = np.broadcast_to(np.asarray(x, dtype=float), shape).reshape(-1)
    y = np.broadcast_to(np.asarray(y, dtype=float), shape).reshape(-1)
    u = np.clip(x / cell_m - 0.5, 0.0, cols - 1)
    v = np.clip(y / cell_m - 0.5, 0.0, rows - 1)
    c0 = np.minimum(np.floor(u).astype(int), cols - 2)
    r0 = np.minimum(np.floor(v).astype(int), rows - 2)
    a = u - c0
    g = v - r0
    i00 = r0 * cols + c0
    idx = np.stack([i00, i00 + 1, i00 + cols, i00 + cols + 1], 1)
    w = np.stack([(1 - a) * (1 - g), a * (1 - g), (1 - a) * g, a * g], 1)
    vals = U[idx]  # (n, 4)
    finite = np.isfinite(vals)
    # squared distance from the point to each of the four neighbours, in cell units
    dc = np.array([0.0, 1.0, 0.0, 1.0])[None, :] - a[:, None]
    dr = np.array([0.0, 0.0, 1.0, 1.0])[None, :] - g[:, None]
    d2 = np.where(finite, dc * dc + dr * dr, np.inf)
    nearest = vals[np.arange(len(vals)), np.argmin(d2, axis=1)]
    filled = np.where(finite, vals, nearest[:, None])
    out = np.sum(w * filled, axis=1)
    none = ~finite.any(axis=1)
    if np.any(none):
        tree, values = _nearest_finite(U, rows, cols, cell_m)
        _, j = tree.query(np.column_stack((x[none], y[none])))
        out[none] = values[j] + 1.0
    return out.reshape(shape)
