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
    locate,
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


# --- sparse sampling at depth 2 (Ch 9.4) --------------------------------------------------------

SPARSE_M1 = 20
SPARSE_M2 = 10


def _leaf_value(solution: Solution, hole: Hole, player: Player, x: np.ndarray, y: np.ndarray):
    """Strokes to go at landing points: E[putts] on the green, else the bilinear grid value."""
    from caddie.online import bilinear

    _, lie, _ = locate(hole, x, y)
    value = bilinear(solution.U, hole.rows, hole.cols, hole.cell_m, x, y)
    green = lie == int(Lie.GREEN)
    if np.any(green):
        d = np.hypot(x[green] - hole.pin_xy[0], y[green] - hole.pin_xy[1])
        value = np.array(value, dtype=float)
        value[green] = np.asarray(player.putting(d), dtype=float)
    return value, lie


def sparse2_point_policy(
    solution: Solution | None,
    hole: Hole,
    player: Player,
    mode: PenaltyMode,
    m1: int = SPARSE_M1,
    m2: int = SPARSE_M2,
    seed: int = 0,
) -> PointPolicy:
    """Two shots of lookahead: ``m1`` landings per first action from the exact point, then
    the grid policy's action from each landing's cell with ``m2`` draws, then the grid value.

    The second shot steps from the landing cell centre through :func:`caddie.mdp.step_batch`
    (vectorised over the landings that share a grid action) and its leaf is the solved value
    of the next cell, which on the green is E[putts]. A landing on the green ends there with
    E[putts] from the exact point.
    """
    from caddie.online import shots_from_point

    sol = _need(solution, "sparse2")
    draws1 = make_draws(m1, seed)
    tables2 = build_offset_tables(player, make_draws(m2, seed + 1))
    playable = {int(Lie.TEE), int(Lie.FAIRWAY), int(Lie.ROUGH), int(Lie.BUNKER)}

    def second_level(cells: np.ndarray, lies: np.ndarray) -> np.ndarray:
        """Strokes to go after the grid action from each landing cell, (n,)."""
        out = np.empty(cells.size)
        clubs, dirs = sol.club[cells], sol.dir[cells]
        plain = ~np.isin(lies, list(playable)) | (clubs == NO_ACTION)
        out[plain] = sol.U[cells[plain]]
        todo = np.flatnonzero(~plain)
        for ci, di in {(int(c), int(d)) for c, d in zip(clubs[todo], dirs[todo], strict=True)}:
            grp = todo[(clubs[todo] == ci) & (dirs[todo] == di)]
            nxt, r = step_batch(hole, player, cells[grp], lies[grp], ci, di, tables2, mode)
            out[grp] = np.mean(-r + sol.U[nxt], axis=1)
        return out

    def point(x: float, y: float, lie: Lie) -> tuple[str, float]:
        best, best_q = ("", 0.0), np.inf
        for ci, di in candidate_actions(hole, player, (x, y)):
            club = player.clubs[player.club_order[ci]]
            deg = float(DIRECTIONS_DEG[di])
            nx, ny, cost = shots_from_point(hole, player, x, y, lie, club, deg, draws1, mode)
            cells, land_lie, _ = locate(hole, nx, ny)
            value = second_level(cells, land_lie)
            green = land_lie == int(Lie.GREEN)
            if np.any(green):
                d = np.hypot(nx[green] - hole.pin_xy[0], ny[green] - hole.pin_xy[1])
                value[green] = np.asarray(player.putting(d), dtype=float)
            q = float(np.mean(cost + value))
            if q < best_q:
                best, best_q = (player.club_order[ci], deg), q
        return best

    return point


def build_sparse2(
    hole: Hole,
    player: Player,
    solution: Solution | None,
    mode: PenaltyMode,
    m1: int = SPARSE_M1,
    m2: int = SPARSE_M2,
    seed: int = 0,
) -> Policy:
    return policy_from_point(
        player, sparse2_point_policy(solution, hole, player, mode, m1=m1, m2=m2, seed=seed)
    )


# --- MCTS with progressive widening (Ch 9.6) ----------------------------------------------------

MCTS_ITERS = 300
MCTS_C = 1.0
MCTS_K = 2.0
MCTS_ALPHA = 0.5
MCTS_MIN_VISITS = 5
MCTS_AIM_SD_DEG = 20.0  # new aims are drawn around the pin line, clipped to [-90, 90]


def mcts_point_policy(
    solution: Solution | None,
    hole: Hole,
    player: Player,
    mode: PenaltyMode,
    iters: int = MCTS_ITERS,
    c: float = MCTS_C,
    k: float = MCTS_K,
    alpha: float = MCTS_ALPHA,
    seed: int = 0,
) -> PointPolicy:
    """One-ply Monte Carlo tree search from the point with the grid value at the leaves.

    UCB1 over the candidate clubs; under each club, progressive widening over a continuous
    aim (a new aim is drawn from N(0, ``MCTS_AIM_SD_DEG``) clipped to [-90, 90] while the
    club has fewer than ``k x n^alpha`` of them, otherwise UCB1 picks among the existing
    ones). Each iteration plays one shot with a fresh draw and scores it as cost plus the
    leaf value. A club is valued by its best visited aim, not its average, so exploratory
    aims do not drag a good club down. The answer is the aim with the lowest mean among
    those visited at least ``MCTS_MIN_VISITS`` times.
    """
    from caddie.mdp import Draws
    from caddie.online import shots_from_point

    sol = _need(solution, "mcts")
    rng = np.random.default_rng(seed)

    def one_shot(x, y, lie, club, deg) -> float:
        draws = Draws(
            theta=rng.standard_normal(1),
            z=rng.standard_normal(1),
            u=rng.random(1),
            roll=rng.standard_normal(1),
        )
        nx, ny, cost = shots_from_point(hole, player, x, y, lie, club, deg, draws, mode)
        v, _ = _leaf_value(sol, hole, player, nx, ny)
        return float(cost[0] + v[0])

    def point(x: float, y: float, lie: Lie) -> tuple[str, float]:
        clubs = sorted({int(ci) for ci, _ in candidate_actions(hole, player, (x, y))})
        # per club: visit count, sum of returns, and a list of [aim_deg, n, total]
        n_club = np.zeros(len(clubs))
        s_club = np.zeros(len(clubs))
        aims: list[list[list[float]]] = [[] for _ in clubs]
        total = 0

        def club_value(a: int) -> float:
            best = min((e[2] / e[1] for e in aims[a] if e[1] >= 2), default=np.inf)
            return best if np.isfinite(best) else s_club[a] / max(n_club[a], 1)

        for _ in range(iters):
            total += 1
            # UCB1 over clubs (lower strokes are better, so negate the value)
            if np.any(n_club == 0):
                a = int(np.flatnonzero(n_club == 0)[0])
            else:
                values = np.array([club_value(a) for a in range(len(clubs))])
                a = int(np.argmax(-values + c * np.sqrt(np.log(total) / n_club)))
            club = player.clubs[player.club_order[clubs[a]]]
            # progressive widening over the aim
            if len(aims[a]) < k * (n_club[a] + 1) ** alpha:
                deg = float(np.clip(rng.normal(0.0, MCTS_AIM_SD_DEG), -90.0, 90.0))
                aim = [deg, 0.0, 0.0]
                aims[a].append(aim)
            else:
                ns = np.array([e[1] for e in aims[a]])
                ms = np.array([e[2] for e in aims[a]]) / np.maximum(ns, 1)
                aim = aims[a][int(np.argmax(-ms + c * np.sqrt(np.log(n_club[a] + 1) / ns)))]
            ret = one_shot(x, y, lie, club, aim[0])
            aim[1] += 1
            aim[2] += ret
            n_club[a] += 1
            s_club[a] += ret
        best_club, best_aim, best_mean = clubs[0], 0.0, np.inf
        for a, entries in enumerate(aims):
            for deg, n, tot in entries:
                if n >= MCTS_MIN_VISITS and tot / n < best_mean:
                    best_club, best_aim, best_mean = clubs[a], deg, tot / n
        if not np.isfinite(best_mean):  # too few iterations for any aim to qualify
            a = int(np.argmax(n_club))
            deg, n, tot = max(aims[a], key=lambda e: e[1])
            best_club, best_aim = clubs[a], deg
        return player.club_order[best_club], float(best_aim)

    return point


def build_mcts(
    hole: Hole,
    player: Player,
    solution: Solution | None,
    mode: PenaltyMode,
    iters: int = MCTS_ITERS,
    c: float = MCTS_C,
    k: float = MCTS_K,
    alpha: float = MCTS_ALPHA,
    seed: int = 0,
) -> Policy:
    return policy_from_point(
        player,
        mcts_point_policy(
            solution, hole, player, mode, iters=iters, c=c, k=k, alpha=alpha, seed=seed
        ),
    )


def sparse2_point_policy_builder(hole, player, solution, mode, **settings) -> PointPolicy:
    return sparse2_point_policy(solution, hole, player, mode, **settings)


def mcts_point_policy_builder(hole, player, solution, mode, **settings) -> PointPolicy:
    return mcts_point_policy(solution, hole, player, mode, **settings)


APPROACHES: dict[str, Approach] = {
    "grid": Approach("grid", build_grid, point_grid, needs_solution=True),
    "rollout": Approach("rollout", build_rollout, point_rollout, needs_solution=True, memoise=True),
    "pin": Approach("pin", build_pin, None, needs_solution=False),
    "centre": Approach("centre", build_centre, None, needs_solution=False),
    "greedy": Approach("greedy", build_greedy, None, needs_solution=False, memoise=True),
    "risk": Approach("risk", build_risk, None, needs_solution=True),
    "sparse2": Approach(
        "sparse2", build_sparse2, sparse2_point_policy_builder, needs_solution=True, memoise=True
    ),
    "mcts": Approach(
        "mcts", build_mcts, mcts_point_policy_builder, needs_solution=True, memoise=True
    ),
}
