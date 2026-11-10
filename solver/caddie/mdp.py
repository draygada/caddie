"""Part 04: the hole MDP (Ch 7.1).

State is ``(cell, lie)`` with the lie taken from the hole grid; action is
``(club, direction)``. The transition is generative in two stages: the ball
lands at a sampled carry and lateral offset, then rolls along the aim
direction by an amount scaled by the landing lie. Water and OB are terrain
rules applied to the final cell according to ``penalty_mode``.

Every sampler takes a precomputed :class:`Draws` (fixed Halton draws shared
by every cell and sweep) so value iteration is deterministic.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass
from enum import IntEnum
from typing import Literal, Protocol

import numpy as np
from scipy.spatial import cKDTree
from scipy.stats import norm, qmc

from caddie.dispersion import MISHIT_MEAN, ClubParams, Player
from caddie.geometry import Hole
from caddie.putting import PuttingTable

log = logging.getLogger(__name__)


class Lie(IntEnum):
    OUT = 0
    TEE = 1
    FAIRWAY = 2
    ROUGH = 3
    BUNKER = 4
    GREEN = 5
    WATER = 6
    OB = 7


class PuttingCurve(Protocol):
    """Anything callable on distance in meters, like :class:`PuttingTable`."""

    def __call__(self, d_m: float | np.ndarray) -> np.ndarray: ...


PenaltyMode = Literal["mulligan", "drop", "replay"]
PENALTY_MODES: tuple[PenaltyMode, ...] = ("mulligan", "drop", "replay")

DIRECTIONS_DEG: np.ndarray = np.arange(-90, 91, 2, dtype=float)

# Lies a shot can be played from, in offset-table order. Shots from the green
# are never chosen (green cells are terminal) but the table keeps the slot so
# the online step can use it; the green row uses the fairway multipliers.
FROM_LIES: tuple[Lie, ...] = (Lie.TEE, Lie.FAIRWAY, Lie.ROUGH, Lie.BUNKER, Lie.GREEN)
FROM_LIE_NAME: dict[Lie, str] = {
    Lie.TEE: "tee",
    Lie.FAIRWAY: "fairway",
    Lie.ROUGH: "rough",
    Lie.BUNKER: "bunker",
    Lie.GREEN: "fairway",
}


@dataclass
class Draws:
    """Fixed quasi-random draws shared by every cell and sweep.

    ``theta`` and ``roll`` are standard normals. The carry mixture
    ``X ~ (1 - p) N(0, 1) + p N(-2, 1)`` depends on each club's ``p``, so the
    standard normal ``z`` and the component uniform ``u`` are stored and
    :meth:`x` applies ``p`` when the offset tables are built.
    """

    theta: np.ndarray
    z: np.ndarray
    u: np.ndarray
    roll: np.ndarray

    def x(self, p: float) -> np.ndarray:
        """Mixture draw X for mishit probability ``p``."""
        return np.where(self.u < p, self.z + MISHIT_MEAN, self.z)


def make_draws(K: int, seed: int = 0) -> Draws:
    """K scrambled Halton points in 4 dimensions mapped to the draws above."""
    pts = qmc.Halton(d=4, scramble=True, seed=seed).random(K)
    normals = norm.ppf(pts[:, :3])
    return Draws(theta=normals[:, 0], z=normals[:, 1], u=pts[:, 3], roll=normals[:, 2])


def aim_unit(dir_deg: float | np.ndarray) -> tuple[np.ndarray, np.ndarray]:
    """Unit aim vector (sin d, cos d) for a direction relative to the pin bearing (+y)."""
    b = np.radians(dir_deg)
    return np.sin(b), np.cos(b)


def landing_offsets(
    club: ClubParams, lie_mult: dict[str, float], draws: Draws, dir_deg: float
) -> tuple[np.ndarray, np.ndarray, np.ndarray]:
    """(dx, dy, roll_m), each (K,), for one club, from-lie and aim direction.

    Carry and direction spread use the from-lie multipliers. The roll here
    is scaled by the from-lie roll multiplier only; :func:`apply_roll` scales
    it again by the landing lie.
    """
    carry = (
        club.mu_c * lie_mult["carry"] * (1.0 + club.sigma_d * lie_mult["sigma"] * draws.x(club.p))
    )
    theta_deg = club.sigma_theta_deg * lie_mult["sigma"] * draws.theta
    sx, cy = aim_unit(dir_deg + theta_deg)
    roll_m = (club.mu_r + club.sigma_r * draws.roll) * lie_mult["roll"]
    return carry * sx, carry * cy, roll_m


@dataclass
class OffsetTables:
    """Landing offsets for every (club, from-lie, direction), K as the trailing axis."""

    dx: np.ndarray  # (n_clubs, n_lies, n_dirs, K)
    dy: np.ndarray
    roll: np.ndarray


def build_offset_tables(player: Player, draws: Draws) -> OffsetTables:
    """Precompute landing offsets for every club in ``player.club_order``."""
    n_clubs, n_lies, n_dirs, K = (
        len(player.club_order),
        len(FROM_LIES),
        len(DIRECTIONS_DEG),
        len(draws.theta),
    )
    dx = np.empty((n_clubs, n_lies, n_dirs, K))
    dy = np.empty_like(dx)
    roll = np.empty_like(dx)
    for ci, name in enumerate(player.club_order):
        club = player.clubs[name]
        for li, lie in enumerate(FROM_LIES):
            mult = player.lie[FROM_LIE_NAME[lie]]
            for di, d in enumerate(DIRECTIONS_DEG):
                dx[ci, li, di], dy[ci, li, di], roll[ci, li, di] = landing_offsets(
                    club, mult, draws, d
                )
    log.info("built offset tables %s", dx.shape)
    return OffsetTables(dx=dx, dy=dy, roll=roll)


# roll multiplier by landing lie; the player's lie table covers tee, fairway,
# rough and bunker, the ball runs on the green, and water/OB/out stop it.
def roll_multipliers(player: Player) -> np.ndarray:
    """(8,) roll multiplier indexed by landing lie code."""
    m = np.zeros(len(Lie))
    m[Lie.TEE] = player.lie["tee"]["roll"]
    m[Lie.FAIRWAY] = player.lie["fairway"]["roll"]
    m[Lie.ROUGH] = player.lie["rough"]["roll"]
    m[Lie.BUNKER] = player.lie["bunker"]["roll"]
    m[Lie.GREEN] = 1.0
    return m


def apply_roll(landing_lie: np.ndarray, roll_m: np.ndarray, player: Player) -> np.ndarray:
    """Roll distance scaled by the landing lie's roll multiplier."""
    return roll_m * roll_multipliers(player)[landing_lie]


PLAYABLE_LIES = (Lie.TEE, Lie.FAIRWAY, Lie.ROUGH, Lie.BUNKER, Lie.GREEN)
_OB_DROP_CACHE: dict[int, tuple[Hole, np.ndarray]] = {}


def ob_drop_lookup(hole: Hole) -> np.ndarray:
    """(rows*cols,) flat index of the nearest in-grid non-water, non-OB cell to each cell.

    Computed once per hole with a KD-tree over the playable cell centres and
    cached, so step_batch answers OB drops with a gather. Points off the grid
    are first clipped to the edge cell by :func:`locate`.
    """
    hit = _OB_DROP_CACHE.get(id(hole))
    if hit is not None and hit[0] is hole:
        return hit[1]
    flat = hole.lie.reshape(-1)
    playable = np.flatnonzero(np.isin(flat, [int(v) for v in PLAYABLE_LIES]))
    r, c = np.divmod(playable, hole.cols)
    tree = cKDTree(np.column_stack(((c + 0.5) * hole.cell_m, (r + 0.5) * hole.cell_m)))
    all_idx = np.arange(flat.size)
    ar, ac = np.divmod(all_idx, hole.cols)
    _, nearest = tree.query(np.column_stack(((ac + 0.5) * hole.cell_m, (ar + 0.5) * hole.cell_m)))
    look = playable[nearest].astype(np.int64)
    _OB_DROP_CACHE[id(hole)] = (hole, look)
    return look


def cell_xy(hole: Hole, idx: np.ndarray) -> tuple[np.ndarray, np.ndarray]:
    r, c = np.divmod(np.asarray(idx), hole.cols)
    return (c + 0.5) * hole.cell_m, (r + 0.5) * hole.cell_m


def locate(hole: Hole, x: np.ndarray, y: np.ndarray) -> tuple[np.ndarray, np.ndarray, np.ndarray]:
    """Flat cell index, lie and an outside mask for continuous points.

    Points outside the grid are clipped to the nearest edge cell and reported
    as OB; so are in-grid cells whose lie is OUT (the corridor edge).
    """
    r = np.floor(y / hole.cell_m).astype(np.int64)
    c = np.floor(x / hole.cell_m).astype(np.int64)
    outside = (r < 0) | (r >= hole.rows) | (c < 0) | (c >= hole.cols)
    r = np.clip(r, 0, hole.rows - 1)
    c = np.clip(c, 0, hole.cols - 1)
    idx = r * hole.cols + c
    lie = hole.lie.reshape(-1)[idx].astype(np.int64)
    outside = outside | (lie == Lie.OUT)
    lie = np.where(outside, int(Lie.OB), lie)
    return idx, lie, outside


def pin_bearing_deg(hole: Hole, x: np.ndarray, y: np.ndarray) -> np.ndarray:
    """Bearing from (x, y) to the pin, degrees clockwise from +y, in (-180, 180]."""
    return np.degrees(np.arctan2(hole.pin_xy[0] - x, hole.pin_xy[1] - y))


def step_batch(
    hole: Hole,
    player: Player,
    from_idx: np.ndarray,
    from_lie: np.ndarray,
    club_idx: int,
    dir_idx: int,
    tables: OffsetTables,
    mode: PenaltyMode,
) -> tuple[np.ndarray, np.ndarray]:
    """Next cell index and reward, each (N, K), for every from cell and draw.

    Directions are relative to each cell's bearing to the pin: the table
    offsets (sampled for an aim of ``dir_deg`` from +y) are rotated by the
    cell's pin bearing. Land at the sampled offset, roll along the aim unit
    vector by an amount scaled by the landing lie, then apply the terrain
    rule for ``mode`` on the final cell.
    """
    if mode not in PENALTY_MODES:
        raise ValueError(f"unknown penalty_mode {mode!r}")
    from_idx = np.asarray(from_idx, dtype=np.int64)
    from_li = np.asarray(from_lie, dtype=np.int64) - 1  # table slot: TEE=0 ... GREEN=4
    if np.any((from_li < 0) | (from_li >= len(FROM_LIES))):
        raise ValueError("from_lie must be one of the playable lies")
    x0, y0 = cell_xy(hole, from_idx)
    dx = tables.dx[club_idx, from_li, dir_idx]  # (N, K)
    dy = tables.dy[club_idx, from_li, dir_idx]
    roll = tables.roll[club_idx, from_li, dir_idx]

    bearing = np.radians(pin_bearing_deg(hole, x0, y0))[:, None]  # (N, 1)
    cb, sb = np.cos(bearing), np.sin(bearing)
    rdx = dx * cb + dy * sb
    rdy = -dx * sb + dy * cb
    lx, ly = x0[:, None] + rdx, y0[:, None] + rdy
    _, land_lie, _ = locate(hole, lx, ly)
    ux, uy = aim_unit(np.degrees(bearing) + DIRECTIONS_DEG[dir_idx])
    run = apply_roll(land_lie, roll, player)
    fx, fy = lx + ux * run, ly + uy * run
    final_idx, final_lie, outside = locate(hole, fx, fy)

    water = final_lie == Lie.WATER
    ob = (final_lie == Lie.OB) | outside
    penalty = -1.0 if mode == "mulligan" else -2.0
    reward = np.where(water | ob, penalty, -1.0)

    origin = np.broadcast_to(from_idx[:, None], final_idx.shape)
    if mode in ("mulligan", "replay"):
        next_idx = np.where(water | ob, origin, final_idx)
    else:
        next_idx = final_idx.copy()
        if np.any(water):
            next_idx[water] = hole.drop_index.reshape(-1)[final_idx[water]]
        if np.any(ob):
            next_idx[ob] = ob_drop_lookup(hole)[final_idx[ob]]
    return next_idx.astype(np.int64), reward


def terminal_values(hole: Hole, putting: PuttingTable | PuttingCurve) -> np.ndarray:
    """(rows*cols,) value -E[putts](distance to pin) on green cells, NaN elsewhere."""
    flat = hole.lie.reshape(-1)
    u = np.full(flat.shape, np.nan)
    green = np.flatnonzero(flat == Lie.GREEN)
    x, y = cell_xy(hole, green)
    dist = np.hypot(x - hole.pin_xy[0], y - hole.pin_xy[1])
    u[green] = -np.asarray(putting(dist), dtype=float)
    return u


CANDIDATE_CARRY_FACTOR = 1.3


def candidate_actions(hole: Hole, player: Player, from_xy: tuple[float, float]) -> np.ndarray:
    """(n, 2) array of (club_idx, dir_idx) worth evaluating from ``from_xy``.

    Keeps clubs with ``mu_c <= 1.3 * distance to pin`` and every direction;
    the shortest club is always kept so the set is never empty.
    """
    dist = float(np.hypot(from_xy[0] - hole.pin_xy[0], from_xy[1] - hole.pin_xy[1]))
    mu = np.array([player.clubs[name].mu_c for name in player.club_order])
    keep = np.flatnonzero(mu <= CANDIDATE_CARRY_FACTOR * dist)
    if keep.size == 0:
        keep = np.array([int(np.argmin(mu))])
    clubs, dirs = np.meshgrid(keep, np.arange(len(DIRECTIONS_DEG)), indexing="ij")
    return np.column_stack((clubs.ravel(), dirs.ravel()))
