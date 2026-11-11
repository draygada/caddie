"""Part 16: the shot-selection approaches the benchmark compares.

An :class:`Approach` builds a part 07 ``Policy`` (``(x, y, lie) -> (club_idx, dir_idx)``)
for a hole, a player, an optional value iteration solution and a penalty mode; the
approaches that can aim from a continuous point also build a ``PointPolicy`` returning a
club name and an aim in degrees. Settings (lambda, sample counts, search budgets) are the
benchmark's fixed values from docs/parts/16-benchmark.md.
"""

from __future__ import annotations

import logging
from collections.abc import Callable
from dataclasses import dataclass
from pathlib import Path

import numpy as np

from caddie.dispersion import Player
from caddie.evaluate import Policy, centre_policy, optimal_policy, pin_policy
from caddie.geometry import Hole
from caddie.mdp import (
    DIRECTIONS_DEG,
    Lie,
    PenaltyMode,
    build_offset_tables,
    candidate_actions,
    cell_xy,
    make_draws,
    step_batch,
)
from caddie.online import recommend
from caddie.value_iteration import NO_ACTION, PLAYABLE_LIES, Solution, solve

log = logging.getLogger(__name__)

PointPolicy = Callable[[float, float, Lie], tuple[str, float]]
"""``policy(x, y, lie) -> (club name, dir_deg)``; the aim need not be one of the 91 steps."""

Builder = Callable[..., Policy]
PointBuilder = Callable[..., PointPolicy]


@dataclass(frozen=True)
class Approach:
    id: str
    build: Builder  # (hole, player, solution | None, mode, **settings) -> Policy
    point: PointBuilder | None  # continuous variant, or None
    needs_solution: bool
    memoise: bool = False  # online approaches decide each (cell, lie) once on the cell simulator


# --- helpers -------------------------------------------------------------------------------------


def cell_index(hole: Hole, x: float, y: float) -> int:
    r = min(max(int(np.floor(y / hole.cell_m)), 0), hole.rows - 1)
    c = min(max(int(np.floor(x / hole.cell_m)), 0), hole.cols - 1)
    return r * hole.cols + c


def nearest_dir_index(dir_deg: float) -> int:
    return int(np.argmin(np.abs(DIRECTIONS_DEG - dir_deg)))


def playable_cells(hole: Hole, solution: Solution | None = None) -> np.ndarray:
    """Flat indices of tee, fairway, rough and bunker cells (with an action when given)."""
    flat = hole.lie.reshape(-1)
    mask = np.isin(flat, [int(v) for v in PLAYABLE_LIES])
    if solution is not None:
        mask &= solution.club != NO_ACTION
    return np.flatnonzero(mask)


def memoise_policy(hole: Hole, policy: Policy) -> Policy:
    """Decide each ``(cell, lie)`` once; the cell simulator only ever asks at cell centres."""
    cache: dict[tuple[int, int], tuple[int, int]] = {}

    def memo(x: float, y: float, lie: Lie) -> tuple[int, int]:
        key = (cell_index(hole, x, y), int(lie))
        hit = cache.get(key)
        if hit is None:
            hit = cache[key] = policy(x, y, lie)
        return hit

    return memo


def point_from_policy(player: Player, policy: Policy) -> PointPolicy:
    """Index policy as a point policy (club name, aim in degrees)."""

    def point(x: float, y: float, lie: Lie) -> tuple[str, float]:
        ci, di = policy(x, y, lie)
        return player.club_order[ci], float(DIRECTIONS_DEG[di])

    return point


def _need(solution: Solution | None, who: str) -> Solution:
    if solution is None:
        raise ValueError(f"{who} needs a value iteration solution")
    return solution


# --- the existing four ---------------------------------------------------------------------------


def build_grid(hole: Hole, player: Player, solution: Solution | None, mode: PenaltyMode) -> Policy:
    return optimal_policy(_need(solution, "grid"), hole)


def point_grid(
    hole: Hole, player: Player, solution: Solution | None, mode: PenaltyMode
) -> PointPolicy:
    return point_from_policy(player, build_grid(hole, player, solution, mode))


def point_rollout(
    hole: Hole,
    player: Player,
    solution: Solution | None,
    mode: PenaltyMode,
    m: int = 100,
    seed: int = 0,
) -> PointPolicy:
    sol = _need(solution, "rollout")

    def point(x: float, y: float, lie: Lie) -> tuple[str, float]:
        rec = recommend(sol, hole, player, x, y, lie, mode, m=m, seed=seed)
        return rec.club, rec.dir_deg

    return point


def policy_from_point(player: Player, point: PointPolicy) -> Policy:
    """Point policy as an index policy: the club's index and the nearest direction step."""
    order = {name: k for k, name in enumerate(player.club_order)}

    def policy(x: float, y: float, lie: Lie) -> tuple[int, int]:
        club, deg = point(x, y, lie)
        return order[club], nearest_dir_index(deg)

    return policy


def build_rollout(
    hole: Hole,
    player: Player,
    solution: Solution | None,
    mode: PenaltyMode,
    m: int = 100,
    seed: int = 0,
) -> Policy:
    return policy_from_point(player, point_rollout(hole, player, solution, mode, m=m, seed=seed))


def build_pin(hole: Hole, player: Player, solution: Solution | None, mode: PenaltyMode) -> Policy:
    return pin_policy(hole, player)


def build_centre(
    hole: Hole, player: Player, solution: Solution | None, mode: PenaltyMode
) -> Policy:
    return centre_policy(hole, player)


# --- greedy: minimise the expected distance to the pin after one shot ---------------------------

GREEDY_DRAWS = 200


def greedy_policy(
    hole: Hole, player: Player, mode: PenaltyMode, K: int = GREEDY_DRAWS, seed: int = 0
) -> Policy:
    """No lookahead: the (club, direction) whose landing is closest to the pin on average.

    Landings are taken through :func:`caddie.mdp.step_batch` from the containing cell, so
    water and OB count from where the ball plays next under ``mode`` (the drop cell, or
    the origin under replay and mulligan), not from where it splashed.
    """
    tables = build_offset_tables(player, make_draws(K, seed))
    px, py = hole.pin_xy

    def policy(x: float, y: float, lie: Lie) -> tuple[int, int]:
        idx = np.array([cell_index(hole, x, y)])
        from_lie = np.array([int(lie)])
        best, best_d = (0, nearest_dir_index(0.0)), np.inf
        for ci, di in candidate_actions(hole, player, (x, y)):
            nxt, _ = step_batch(hole, player, idx, from_lie, int(ci), int(di), tables, mode)
            nx, ny = cell_xy(hole, nxt[0])
            d = float(np.mean(np.hypot(nx - px, ny - py)))
            if d < best_d:
                best, best_d = (int(ci), int(di)), d
        return best

    return policy


def build_greedy(
    hole: Hole,
    player: Player,
    solution: Solution | None,
    mode: PenaltyMode,
    K: int = GREEDY_DRAWS,
    seed: int = 0,
) -> Policy:
    return greedy_policy(hole, player, mode, K=K, seed=seed)


# --- risk: the grid policy under exponential utility ----------------------------------------------

RISK_LAMBDA = 0.5  # per stroke; the benchmark's fixed setting, swept in the compute figure


def risk_solution(
    hole: Hole,
    player: Player,
    mode: PenaltyMode,
    lam: float = RISK_LAMBDA,
    K: int = 200,
    tol: float = 0.01,
    seed: int = 0,
    cache_path: Path | None = None,
) -> Solution:
    """Value iteration under ``-exp(lam x strokes)``; same draws and tolerance as ``grid``.

    ``cache_path`` (an ``.npz``) keeps the grids between runs, since a real hole takes as
    long as the plain solve.
    """
    if cache_path is not None and Path(cache_path).exists():
        z = np.load(cache_path)
        return Solution(
            hole=hole.number,
            mode=mode,
            U=z["U"],
            club=z["club"],
            dir=z["dir"],
            sweeps=int(z["sweeps"]),
        )
    sol = solve(hole, player, mode, K=K, tol=tol, seed=seed, objective=("exp", lam))
    if cache_path is not None:
        Path(cache_path).parent.mkdir(parents=True, exist_ok=True)
        np.savez(cache_path, U=sol.U, club=sol.club, dir=sol.dir, sweeps=sol.sweeps)
    return sol


def build_risk(
    hole: Hole,
    player: Player,
    solution: Solution | None,
    mode: PenaltyMode,
    lam: float = RISK_LAMBDA,
    K: int = 200,
    seed: int = 0,
    cache_path: Path | None = None,
) -> Policy:
    return optimal_policy(
        risk_solution(hole, player, mode, lam=lam, K=K, seed=seed, cache_path=cache_path), hole
    )


# --- the new four (filled in by later slices) ---------------------------------------------------


def _later(name: str, slice_no: int) -> Builder:
    def build(*args, **kwargs):
        raise NotImplementedError(f"{name} arrives in part 16 slice {slice_no}")

    return build


APPROACHES: dict[str, Approach] = {
    "grid": Approach("grid", build_grid, point_grid, needs_solution=True),
    "rollout": Approach("rollout", build_rollout, point_rollout, needs_solution=True, memoise=True),
    "pin": Approach("pin", build_pin, None, needs_solution=False),
    "centre": Approach("centre", build_centre, None, needs_solution=False),
    "greedy": Approach("greedy", build_greedy, None, needs_solution=False, memoise=True),
    "risk": Approach("risk", build_risk, None, needs_solution=True),
    "sparse2": Approach(
        "sparse2", _later("sparse2", 7), _later("sparse2", 7), needs_solution=True, memoise=True
    ),
    "mcts": Approach(
        "mcts", _later("mcts", 7), _later("mcts", 7), needs_solution=True, memoise=True
    ),
}
