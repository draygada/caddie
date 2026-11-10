"""Part 06: online recommendation at a continuous point (Ch 9.2 rollout, Ch 8.4 leaf).

    Q(x, a) = (1/m) sum_j [ r_j + U_interp(x'_j) ]      a* = argmax_a Q(x, a)

One shot of lookahead from the continuous position, then the offline value grid at
the landing by bilinear interpolation. The reference that ``app/src/lib/rollout.ts``
must match on a fixed seed.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass

import numpy as np
from scipy.spatial import cKDTree

from caddie.dispersion import ClubParams, Player
from caddie.geometry import Hole
from caddie.mdp import (
    DIRECTIONS_DEG,
    FROM_LIE_NAME,
    PENALTY_MODES,
    Draws,
    Lie,
    PenaltyMode,
    aim_unit,
    apply_roll,
    candidate_actions,
    cell_xy,
    landing_offsets,
    locate,
    make_draws,
    ob_drop_lookup,
    pin_bearing_deg,
)
from caddie.value_iteration import Solution

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


# --- slice 2: recommend ---------------------------------------------------------------------


@dataclass
class Recommendation:
    club: str
    dir_deg: float
    expected_strokes: float
    q_by_action: np.ndarray  # (n_clubs, n_dirs) strokes-to-go per action, NaN where pruned
    baseline_pin_strokes: float  # aim at the pin with the longest club that reaches


def _lie_at(hole: Hole, x: float, y: float) -> Lie:
    _, lie, _ = locate(hole, np.array([x]), np.array([y]))
    return Lie(int(lie[0]))


def _grid_value(solution: Solution, hole: Hole, x: np.ndarray, y: np.ndarray) -> np.ndarray:
    return bilinear(solution.U, hole.rows, hole.cols, hole.cell_m, x, y)


def shots_from_point(
    hole: Hole,
    player: Player,
    x: float,
    y: float,
    lie: Lie,
    club: ClubParams,
    dir_deg: float,
    draws: Draws,
    mode: PenaltyMode,
) -> tuple[np.ndarray, np.ndarray, np.ndarray]:
    """Resting point and cost of one shot from the continuous point ``(x, y)``, per draw.

    Mirrors :func:`caddie.mdp.step_batch` from a point instead of a cell centre: the
    offsets are sampled for an aim relative to +y and rotated by the point's pin
    bearing. Returns ``(next_x, next_y, cost)``, cost 1 for a normal shot and 2 for a
    water or OB landing (1 under mulligan). Under mulligan and replay the ball returns to
    ``(x, y)``; under drop it goes to the drop cell's centre.
    """
    if mode not in PENALTY_MODES:
        raise ValueError(f"unknown penalty_mode {mode!r}")
    mult = player.lie[FROM_LIE_NAME[lie]]
    dx, dy, roll = landing_offsets(club, mult, draws, dir_deg)
    bearing = np.radians(pin_bearing_deg(hole, np.array([x]), np.array([y])))[0]
    cb, sb = np.cos(bearing), np.sin(bearing)
    lx = x + dx * cb + dy * sb
    ly = y - dx * sb + dy * cb
    _, land_lie, _ = locate(hole, lx, ly)
    ux, uy = aim_unit(np.degrees(bearing) + dir_deg)
    run = apply_roll(land_lie, roll, player)
    fx, fy = lx + ux * run, ly + uy * run
    final_idx, final_lie, outside = locate(hole, fx, fy)
    water = final_lie == Lie.WATER
    ob = (final_lie == Lie.OB) | outside
    bad = water | ob
    cost = np.where(bad, 1.0 if mode == "mulligan" else 2.0, 1.0)
    if mode in ("mulligan", "replay"):
        nx = np.where(bad, x, fx)
        ny = np.where(bad, y, fy)
    else:
        target = final_idx.copy()
        if np.any(water):
            target[water] = hole.drop_index.reshape(-1)[final_idx[water]]
        if np.any(ob):
            target[ob] = ob_drop_lookup(hole)[final_idx[ob]]
        tx, ty = cell_xy(hole, target)
        nx = np.where(bad, tx, fx)
        ny = np.where(bad, ty, fy)
    return nx, ny, cost


def recommend(
    solution: Solution,
    hole: Hole,
    player: Player,
    x: float,
    y: float,
    lie: Lie | None,
    mode: PenaltyMode,
    m: int = 100,
    seed: int = 0,
) -> Recommendation:
    """Best (club, direction) from ``(x, y)`` by one-shot lookahead onto the value grid.

    ``lie`` None reads the lie of the containing cell. Fresh seeded Halton draws, shared
    by every action and by the pin baseline so the comparison is paired.
    """
    from_lie = _lie_at(hole, x, y) if lie is None else Lie(lie)
    if from_lie not in FROM_LIE_NAME or from_lie == Lie.GREEN:
        raise ValueError(f"no shot from lie {from_lie.name} at ({x:.1f}, {y:.1f})")
    draws = make_draws(m, seed)
    n_clubs, n_dirs = len(player.club_order), len(DIRECTIONS_DEG)
    q = np.full((n_clubs, n_dirs), np.nan)
    actions = candidate_actions(hole, player, (x, y))
    for ci in np.unique(actions[:, 0]):
        club = player.clubs[player.club_order[ci]]
        for di in np.unique(actions[actions[:, 0] == ci, 1]):
            nx, ny, cost = shots_from_point(
                hole, player, x, y, from_lie, club, float(DIRECTIONS_DEG[di]), draws, mode
            )
            q[ci, di] = float(np.mean(cost + _grid_value(solution, hole, nx, ny)))
    best = int(np.nanargmin(q))
    bc, bd = divmod(best, n_dirs)

    dist = float(np.hypot(x - hole.pin_xy[0], y - hole.pin_xy[1]))
    mu = np.array([player.clubs[name].mu_c for name in player.club_order])
    reach = np.flatnonzero(mu <= dist)
    base_ci = int(reach[np.argmax(mu[reach])]) if reach.size else int(np.argmin(mu))
    zero = int(np.flatnonzero(DIRECTIONS_DEG == 0)[0])
    if np.isfinite(q[base_ci, zero]):
        baseline = float(q[base_ci, zero])
    else:
        nx, ny, cost = shots_from_point(
            hole, player, x, y, from_lie, player.clubs[player.club_order[base_ci]], 0.0, draws, mode
        )
        baseline = float(np.mean(cost + _grid_value(solution, hole, nx, ny)))
    return Recommendation(
        club=player.club_order[bc],
        dir_deg=float(DIRECTIONS_DEG[bd]),
        expected_strokes=float(q[bc, bd]),
        q_by_action=q,
        baseline_pin_strokes=baseline,
    )
