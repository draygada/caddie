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
import math
from dataclasses import dataclass
from enum import IntEnum
from functools import cached_property
from typing import Literal, Protocol

import numpy as np
from scipy.ndimage import distance_transform_edt
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
    TREES = 8  # part 17: terrain, not a state; a ball cannot enter or pass through


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

    @cached_property
    def carry_len(self) -> np.ndarray:
        """Carry length of every draw, same shape as ``dx`` (part 17 tree rule)."""
        return np.hypot(self.dx, self.dy)

    @cached_property
    def low_len(self) -> np.ndarray:
        """``low_flight_m`` of every draw's carry, same shape as ``dx``."""
        return low_flight_m(self.carry_len)

    @cached_property
    def carry_angle_deg(self) -> np.ndarray:
        """Angle of every draw's carry vector from the table's +y axis, degrees."""
        return np.degrees(np.arctan2(self.dx, self.dy))


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
    """(9,) roll multiplier indexed by landing lie code (0 for water, OB and trees)."""
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


# --- part 17: trees block the ball ---------------------------------------------------

TREE_STEP_BACK_M = 2.5  # a blocked ball rests this far before the first tree point
# Flight height (part 17, amended): three estimates of ours, not measurements.
TREE_HEIGHT_M = 15.0
APEX_MAX_M = 24.0
APEX_PER_CARRY = 0.30
DESCENT_STEP_M = 5.0
RAY_STEP_M = 1.0
RAY_MAX_M = 320.0
RAY_BIN_DEG = 0.5


def low_flight_m(carry: np.ndarray) -> np.ndarray:
    """Meters of a carry spent below the canopy at each end.

    The carry is a parabola with apex ``min(APEX_MAX_M, APEX_PER_CARRY * carry)``. A
    shot whose apex does not clear ``TREE_HEIGHT_M`` is low for its whole carry.
    """
    carry = np.asarray(carry, dtype=float)
    apex = np.minimum(APEX_MAX_M, APEX_PER_CARRY * carry)
    clears = apex > TREE_HEIGHT_M
    ratio = np.where(clears, TREE_HEIGHT_M / np.where(clears, apex, 1.0), 1.0)
    return np.where(clears, carry * (1.0 - np.sqrt(1.0 - ratio)) / 2.0, np.maximum(carry, 0.0))


def _is_tree(hole: Hole, x: np.ndarray, y: np.ndarray) -> np.ndarray:
    """True where (x, y) is inside a tree cell; points off the grid are not trees."""
    r = np.floor(y / hole.cell_m).astype(np.int64)
    c = np.floor(x / hole.cell_m).astype(np.int64)
    inside = (r >= 0) & (r < hole.rows) & (c >= 0) & (c < hole.cols)
    idx = np.clip(r, 0, hole.rows - 1) * hole.cols + np.clip(c, 0, hole.cols - 1)
    return inside & (hole.lie.reshape(-1)[idx] == Lie.TREES)


def tree_march(
    hole: Hole, x: np.ndarray, y: np.ndarray, bearing_deg: np.ndarray, max_m: float = RAY_MAX_M
) -> np.ndarray:
    """Distance to the first tree point along each ray, ``inf`` where there is none.

    The ray is sampled every ``RAY_STEP_M`` from ``RAY_STEP_M`` to ``max_m``. Bearings
    are absolute, degrees clockwise from +y. A ray that starts inside a tree cell (only
    the app can put a ball there) ignores trees until it has left that clump, so the
    player can chip out. ``x``, ``y`` and ``bearing_deg`` broadcast together.
    """
    x, y, b = np.broadcast_arrays(
        np.asarray(x, dtype=float), np.asarray(y, dtype=float), np.asarray(bearing_deg, dtype=float)
    )
    rad = np.radians(b)
    sx, sy = np.sin(rad), np.cos(rad)
    dist = np.full(x.shape, np.inf)
    in_start_clump = _is_tree(hole, x, y)
    for k in range(1, int(math.floor(max_m / RAY_STEP_M)) + 1):
        d = k * RAY_STEP_M
        tree = _is_tree(hole, x + d * sx, y + d * sy)
        in_start_clump &= tree
        hit = tree & ~in_start_clump & np.isinf(dist)
        dist[hit] = d
    return dist


def first_tree_distance(
    hole: Hole, x: float, y: float, bearing_deg: float, max_m: float = RAY_MAX_M
) -> float:
    """Scalar :func:`tree_march`: the reference both halves are tested against."""
    return float(tree_march(hole, np.array([x]), np.array([y]), np.array([bearing_deg]), max_m)[0])


@dataclass
class TreeData:
    """Per-hole lookups for the tree rule, built once and cached."""

    lie: np.ndarray  # the lie grid these were built from
    ray: np.ndarray  # (rows*cols, 720) float32, see tree_ray_table
    is_tree: np.ndarray  # (rows*cols,) bool
    descent: np.ndarray  # (rows*cols, 720) uint8, see descent_table
    dist_m: np.ndarray  # (rows*cols,) distance from each cell centre to the nearest tree centre


_TREE_CACHE: dict[int, tuple[Hole, TreeData | None]] = {}


def tree_data(hole: Hole) -> TreeData | None:
    """Tree lookups for ``hole``, or None when it has no tree cells.

    Cached per hole and rebuilt if the hole's lie grid has changed.
    """
    hit = _TREE_CACHE.get(id(hole))
    if hit is not None and hit[0] is hole:
        if hit[1] is None:
            if not np.any(hole.lie == Lie.TREES):
                return None
        elif np.array_equal(hit[1].lie, hole.lie):
            return hit[1]
    flat = hole.lie.reshape(-1)
    is_tree = flat == Lie.TREES
    if not np.any(is_tree):
        _TREE_CACHE[id(hole)] = (hole, None)
        return None
    n_bins = int(round(360.0 / RAY_BIN_DEG))
    ray = np.full((flat.size, n_bins), np.inf, dtype=np.float32)
    cells = np.flatnonzero(np.isin(flat, [int(v) for v in PLAYABLE_LIES]))
    x, y = cell_xy(hole, cells)
    bearings = np.arange(n_bins) * RAY_BIN_DEG
    ray[cells] = tree_march(hole, x[:, None], y[:, None], bearings[None, :])
    dist = distance_transform_edt(hole.lie != Lie.TREES) * hole.cell_m
    data = TreeData(
        lie=hole.lie.copy(),
        ray=ray,
        is_tree=is_tree,
        descent=descent_table(hole, n_bins),
        dist_m=dist.reshape(-1),
    )
    _TREE_CACHE[id(hole)] = (hole, data)
    log.info("built tree ray table %s for hole %s", ray.shape, hole.number)
    return data


def descent_table(hole: Hole, n_bins: int) -> np.ndarray:
    """(rows*cols, n_bins) uint8 bit mask of tree points on the way down into each cell.

    For a ball arriving at a cell along absolute bearing ``k * RAY_BIN_DEG``, bit ``j``
    is set when the point ``j * DESCENT_STEP_M`` short of the cell centre on that line
    is in a tree cell (bit 0 is the cell itself). The landing point is taken at its
    cell centre, which is the solver's own resolution.
    """
    all_cells = np.arange(hole.rows * hole.cols)
    x, y = cell_xy(hole, all_cells)
    rad = np.radians(np.arange(n_bins) * RAY_BIN_DEG)
    sx, sy = np.sin(rad)[None, :], np.cos(rad)[None, :]
    mask = np.zeros((all_cells.size, n_bins), dtype=np.uint8)
    for j in range(3):
        back = j * DESCENT_STEP_M
        mask |= _is_tree(hole, x[:, None] - back * sx, y[:, None] - back * sy).astype(np.uint8) << j
    return mask


def tree_ray_table(hole: Hole) -> np.ndarray:
    """(rows*cols, 720) float32: :func:`tree_march` from every playable cell centre.

    Column ``k`` is the absolute bearing ``k * RAY_BIN_DEG``. Rows of cells no shot is
    played from are ``inf``; a hole without tree cells gets an all-``inf`` table.
    """
    data = tree_data(hole)
    if data is None:
        n_bins = int(round(360.0 / RAY_BIN_DEG))
        return np.full((hole.rows * hole.cols, n_bins), np.inf, dtype=np.float32)
    return data.ray


def _walk_back(
    hole: Hole, sx: np.ndarray, sy: np.ndarray, ux: np.ndarray, uy: np.ndarray, d: np.ndarray
) -> tuple[np.ndarray, np.ndarray]:
    """Points ``d`` along (ux, uy) from (sx, sy), pulled back until none is in a tree cell."""
    px, py = sx + ux * d, sy + uy * d
    todo = np.flatnonzero(_is_tree(hole, px, py))
    d = d.copy()
    while todo.size:  # only the stragglers; ends at d = 0, the segment start, which is not trees
        d[todo] = np.maximum(d[todo] - TREE_STEP_BACK_M, 0.0)
        px[todo], py[todo] = sx[todo] + ux[todo] * d[todo], sy[todo] + uy[todo] * d[todo]
        todo = todo[_is_tree(hole, px[todo], py[todo]) & (d[todo] > 0)]
    return px, py


def _block_at_trees(
    hole: Hole,
    trees: TreeData,
    x0: np.ndarray,
    y0: np.ndarray,
    from_idx: np.ndarray,
    carry: np.ndarray,
    low: np.ndarray,
    carry_bearing_deg: np.ndarray,
    roll_bearing_deg: np.ndarray,
    lx: np.ndarray,
    ly: np.ndarray,
    land_idx: np.ndarray,
    land_lie: np.ndarray,
    run: np.ndarray,
    fx: np.ndarray,
    fy: np.ndarray,
) -> tuple[np.ndarray, np.ndarray]:
    """Final resting points after the tree rule. (N, K) arrays; starts and roll bearing (N,).

    Climb: the ray-table distance for the shot's bearing bin is within the low part of
    the carry (``low``). Descent: the landing cell, or the points one and two
    ``DESCENT_STEP_M`` short of its centre when they are past the low part, is in a
    tree cell (:func:`descent_table`). Roll: an exact march from the landing
    point, again only near trees. A stopped ball rests ``TREE_STEP_BACK_M`` before the
    tree point that stopped it, walked back while that spot is itself in a tree cell.
    """
    bins = np.rint(carry_bearing_deg / RAY_BIN_DEG).astype(np.int64) % trees.ray.shape[1]
    ray = trees.ray[from_idx[:, None], bins]
    stop = np.where(ray <= low, ray, np.inf)  # distance along the carry line; inf = not stopped

    # Descent: the last 2 x DESCENT_STEP_M of the carry, from the per-cell lookup.
    bits = trees.descent[land_idx, bins]
    if bits.any():
        down = np.where(bits & 1, carry, np.inf)
        for j in (1, 2):  # points further back are earlier on the line, so they win
            s = carry - j * DESCENT_STEP_M
            down = np.where(((bits >> j) & 1 == 1) & (s > low) & (s > 0), s, down)
        stop = np.minimum(stop, down)

    # Whole-array arithmetic from here: indexing out the stopped draws costs more than it saves.
    stopped = np.isfinite(stop)
    if stopped.any():
        safe = np.where(carry > 0, carry, 1.0)
        frac = np.where(stopped, np.maximum(stop - TREE_STEP_BACK_M, 0.0) / safe, 1.0)
        px = x0[:, None] + (lx - x0[:, None]) * frac
        py = y0[:, None] + (ly - y0[:, None]) * frac
        fx, fy = np.where(stopped, px, fx), np.where(stopped, py, fy)
        n, k = np.nonzero(stopped & _is_tree(hole, fx, fy))  # the few still inside a tree cell
        if n.size:
            b = np.radians(carry_bearing_deg[n, k])
            rest = np.maximum(stop[n, k] - 2 * TREE_STEP_BACK_M, 0.0)
            fx[n, k], fy[n, k] = _walk_back(hole, x0[n], y0[n], np.sin(b), np.cos(b), rest)
    else:
        fx, fy = fx.copy(), fy.copy()

    near_tree = trees.dist_m[land_idx]
    n, k = np.nonzero(~stopped & (run != 0) & (near_tree <= np.abs(run) + 1.5 * hole.cell_m))
    if n.size:
        r = run[n, k]
        b = roll_bearing_deg[n] + np.where(r < 0, 180.0, 0.0)  # a negative roll runs backwards
        r = np.abs(r)
        sx, sy = lx[n, k], ly[n, k]
        hit = tree_march(hole, sx, sy, b, max_m=float(r.max()) + RAY_STEP_M)
        stop = np.where(hit <= r, np.maximum(hit - TREE_STEP_BACK_M, 0.0), r)
        rad = np.radians(b)
        fx[n, k], fy[n, k] = _walk_back(hole, sx, sy, np.sin(rad), np.cos(rad), stop)
    return fx, fy


def stop_at_trees_exact(
    hole: Hole,
    x0: float | np.ndarray,
    y0: float | np.ndarray,
    carry_bearing_deg: np.ndarray,
    carry: np.ndarray,
    lx: np.ndarray,
    ly: np.ndarray,
    roll_bearing_deg: float | np.ndarray,
    run: np.ndarray,
    fx: np.ndarray,
    fy: np.ndarray,
) -> tuple[np.ndarray, np.ndarray]:
    """The tree rule for shots from continuous points, marched exactly (no tables).

    The reference version: :func:`step_batch` approximates it with per-cell tables, and
    ``sampleShot`` in the app's shot.ts is the same procedure one shot at a time. All
    arguments broadcast to the shape of ``carry``. Returns the final resting points.
    """
    if not np.any(hole.lie == Lie.TREES):
        return fx, fy
    shape = np.shape(carry)
    x0, y0 = np.broadcast_to(x0, shape).astype(float), np.broadcast_to(y0, shape).astype(float)
    cb = np.broadcast_to(carry_bearing_deg, shape).astype(float)
    rb = np.broadcast_to(roll_bearing_deg, shape).astype(float)
    fx, fy = np.array(fx, dtype=float), np.array(fy, dtype=float)
    low = low_flight_m(carry)
    sx, sy = np.sin(np.radians(cb)), np.cos(np.radians(cb))

    flying = carry > 0
    climb = tree_march(hole, x0, y0, cb, max_m=max(float(low.max()), RAY_STEP_M))
    stop = np.where(flying & (climb <= low), climb, np.inf)
    down = np.full(shape, np.inf)
    for j in range(3):  # points further back are earlier on the line, so they win
        s = carry - j * DESCENT_STEP_M
        ok = flying & (s > 0) & ((s > low) if j else True)
        down = np.where(ok & _is_tree(hole, x0 + sx * s, y0 + sy * s), s, down)
    stop = np.minimum(stop, down)
    stopped = np.isfinite(stop)
    if stopped.any():
        rest = np.maximum(stop[stopped] - TREE_STEP_BACK_M, 0.0)
        fx[stopped], fy[stopped] = _walk_back(
            hole, x0[stopped], y0[stopped], sx[stopped], sy[stopped], rest
        )

    rolling = ~stopped & (run != 0)
    if rolling.any():
        r = np.abs(run[rolling])
        b = rb[rolling] + np.where(run[rolling] < 0, 180.0, 0.0)
        ux, uy = np.sin(np.radians(b)), np.cos(np.radians(b))
        px, py = np.asarray(lx, dtype=float)[rolling], np.asarray(ly, dtype=float)[rolling]
        hit = tree_march(hole, px, py, b, max_m=float(r.max()) + RAY_STEP_M)
        hit = np.where(hit <= r, hit, np.inf)
        end_in_trees = np.isinf(hit) & _is_tree(hole, px + ux * r, py + uy * r)
        hit = np.where(end_in_trees, r, hit)
        blocked = np.isfinite(hit)
        if blocked.any():
            idx = np.flatnonzero(rolling.reshape(-1))[blocked]
            rest = np.maximum(hit[blocked] - TREE_STEP_BACK_M, 0.0)
            qx, qy = _walk_back(hole, px[blocked], py[blocked], ux[blocked], uy[blocked], rest)
            fx.reshape(-1)[idx], fy.reshape(-1)[idx] = qx, qy
    return fx, fy


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
    vector by an amount scaled by the landing lie, stop the ball short of any
    tree cell on the way (part 17), then apply the terrain rule for ``mode``
    on the final cell.
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
    land_idx, land_lie, _ = locate(hole, lx, ly)
    aim_deg = np.degrees(bearing) + DIRECTIONS_DEG[dir_idx]  # (N, 1)
    ux, uy = aim_unit(aim_deg)
    run = apply_roll(land_lie, roll, player)
    fx, fy = lx + ux * run, ly + uy * run
    trees = tree_data(hole)
    if trees is not None:  # part 17: a ball cannot pass through trees
        fx, fy = _block_at_trees(
            hole,
            trees,
            x0,
            y0,
            from_idx,
            tables.carry_len[club_idx, from_li, dir_idx],
            tables.low_len[club_idx, from_li, dir_idx],
            np.degrees(bearing) + tables.carry_angle_deg[club_idx, from_li, dir_idx],
            aim_deg[:, 0],
            lx,
            ly,
            land_idx,
            land_lie,
            run,
            fx,
            fy,
        )
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


# Part 17: clubs that are only hit off a tee.
TEE_ONLY_CLUBS: tuple[str, ...] = ("driver",)


def allowed_clubs(player: Player, lie: Lie | int) -> np.ndarray:
    """Bool per club in ``player.club_order``: False for a tee-only club off the tee.

    A bag made only of tee-only clubs is allowed everywhere, so no lie is left without a club.
    """
    tee_only = np.array([name in TEE_ONLY_CLUBS for name in player.club_order])
    if int(lie) == Lie.TEE or tee_only.all():
        return np.ones(tee_only.shape, dtype=bool)
    return ~tee_only


def candidate_actions(
    hole: Hole, player: Player, from_xy: tuple[float, float], lie: Lie | int | None = None
) -> np.ndarray:
    """(n, 2) array of (club_idx, dir_idx) worth evaluating from ``from_xy``.

    Keeps clubs with ``mu_c <= 1.3 * distance to pin`` and every direction, minus the
    tee-only clubs unless the lie is the tee (``lie`` defaults to the lie of the cell
    under ``from_xy``). The shortest allowed club is always kept so the set is never empty.
    """
    dist = float(np.hypot(from_xy[0] - hole.pin_xy[0], from_xy[1] - hole.pin_xy[1]))
    mu = np.array([player.clubs[name].mu_c for name in player.club_order])
    if lie is None:
        lie = int(locate(hole, np.array([from_xy[0]]), np.array([from_xy[1]]))[1][0])
    ok = allowed_clubs(player, lie)
    keep = np.flatnonzero(ok & (mu <= CANDIDATE_CARRY_FACTOR * dist))
    if keep.size == 0:
        keep = np.array([int(np.flatnonzero(ok)[np.argmin(mu[ok])])])
    clubs, dirs = np.meshgrid(keep, np.arange(len(DIRECTIONS_DEG)), indexing="ij")
    return np.column_stack((clubs.ravel(), dirs.ravel()))
