"""Part 05: value iteration (Ch 7.5, Alg 7.8) on the hole MDP.

Undiscounted. For each playable cell with its own lie,

    U_{k+1}(i) = max_{(club, dir)} (1/K) sum_j ( r_j + U_k(next_j) )

with ``(next_j, r_j)`` from :func:`caddie.mdp.step_batch` over the K fixed
draws. Terminal (green) cells keep ``terminal_values``. Values start at
``-par - 2`` everywhere so they rise monotonically.
"""

from __future__ import annotations

import logging
import time
from dataclasses import dataclass, field
from pathlib import Path

import numpy as np
from scipy.special import logsumexp

from caddie.dispersion import Player
from caddie.geometry import Hole
from caddie.mdp import (
    CANDIDATE_CARRY_FACTOR,
    DIRECTIONS_DEG,
    Lie,
    OffsetTables,
    PenaltyMode,
    build_offset_tables,
    make_draws,
    pin_bearing_deg,
    step_batch,
    terminal_values,
)

log = logging.getLogger(__name__)

NO_ACTION = 255
Objective = str | tuple[str, float]
"""``"strokes"`` (expected strokes, the default) or ``("exp", lam)``: exponential utility
``-exp(lam x strokes)`` (part 16). Under ``("exp", lam)`` the backup is the certainty
equivalent ``-(1/lam) log E[exp(-lam (r + U(next)))]``, which tends to the expectation as
``lam -> 0``; ``U`` then holds certainty-equivalent strokes, not expected strokes.
"""


def _lam(objective: Objective) -> float | None:
    if objective == "strokes":
        return None
    if isinstance(objective, tuple) and len(objective) == 2 and objective[0] == "exp":
        lam = float(objective[1])
        if lam <= 0:
            raise ValueError("exponential utility needs lam > 0")
        return lam
    raise ValueError(f"unknown objective {objective!r}")


LIE_PLOT = {"water": int(Lie.WATER), "ob": int(Lie.OB), "bunker": int(Lie.BUNKER)}
PLAYABLE_LIES = (Lie.TEE, Lie.FAIRWAY, Lie.ROUGH, Lie.BUNKER)


@dataclass
class Solution:
    hole: int
    mode: PenaltyMode
    U: np.ndarray  # float32 (rows*cols,), strokes-to-go as a positive number, NaN on OUT
    club: np.ndarray  # uint8, 255 on terminal/OUT
    dir: np.ndarray  # uint8, 255 on terminal/OUT
    sweeps: int
    residual_history: list[float] = field(default_factory=list)


def state_mask(hole: Hole) -> tuple[np.ndarray, np.ndarray]:
    """(playable, terminal) boolean masks over flat cells.

    Playable cells are tee, fairway, rough and bunker; terminal cells are
    green. Water, OB and OUT are neither (terrain rules, not states).
    """
    flat = hole.lie.reshape(-1)
    playable = np.isin(flat, [int(v) for v in PLAYABLE_LIES])
    terminal = flat == Lie.GREEN
    return playable, terminal


def initial_values(hole: Hole, player: Player) -> np.ndarray:
    """U_0: -par - 2 on playable cells, terminal values on the green, NaN elsewhere."""
    playable, _ = state_mask(hole)
    u = terminal_values(hole, player.putting)
    u[playable] = -(hole.par + 2)
    return u


def all_actions(player: Player) -> np.ndarray:
    """Every (club_idx, dir_idx) pair, shape (n_clubs * 91, 2)."""
    clubs, dirs = np.meshgrid(
        np.arange(len(player.club_order)), np.arange(len(DIRECTIONS_DEG)), indexing="ij"
    )
    return np.column_stack((clubs.ravel(), dirs.ravel())).astype(np.int64)


def club_cells(hole: Hole, player: Player, cells: np.ndarray, club_idx: int) -> np.ndarray:
    """Cells where ``club_idx`` is a candidate (Part 04 rule: mu_c <= 1.3 x distance to pin).

    The shortest club is kept everywhere so no cell is left without an action.
    """
    mu = np.array([player.clubs[name].mu_c for name in player.club_order])
    if club_idx == int(np.argmin(mu)):
        return cells
    r, c = np.divmod(cells, hole.cols)
    dist = np.hypot(
        (c + 0.5) * hole.cell_m - hole.pin_xy[0], (r + 0.5) * hole.cell_m - hole.pin_xy[1]
    )
    return cells[mu[club_idx] <= CANDIDATE_CARRY_FACTOR * dist]


def bellman_backup(
    U: np.ndarray,
    hole: Hole,
    player: Player,
    tables: OffsetTables,
    mode: PenaltyMode,
    candidates: np.ndarray,
    objective: Objective = "strokes",
) -> tuple[np.ndarray, np.ndarray, np.ndarray]:
    """One synchronous sweep over every playable cell.

    Actions are processed in a loop with the cells vectorized, so memory is
    (cells x K) per action, never (cells x actions x K). Returns
    ``(U_new, best_club, best_dir)``; ``U`` is not modified.
    """
    playable, _ = state_mask(hole)
    cells = np.flatnonzero(playable)
    from_lie = hole.lie.reshape(-1)[cells]
    best_q = np.full(cells.shape, -np.inf)
    best_club = np.full(U.shape, NO_ACTION, dtype=np.uint8)
    best_dir = np.full(U.shape, NO_ACTION, dtype=np.uint8)
    bc = np.zeros(cells.shape, dtype=np.uint8)
    bd = np.zeros(cells.shape, dtype=np.uint8)
    lam = _lam(objective)
    for club_idx, dir_idx in candidates:
        nxt, r = step_batch(
            hole, player, cells, from_lie, int(club_idx), int(dir_idx), tables, mode
        )
        total = r + U[nxt]
        if lam is None:
            q = total.mean(axis=1)
        else:
            q = -(logsumexp(-lam * total, axis=1) - np.log(total.shape[1])) / lam
        better = q > best_q
        best_q = np.where(better, q, best_q)
        bc[better] = club_idx
        bd[better] = dir_idx
    if not np.all(np.isfinite(best_q)):
        raise RuntimeError("a playable cell gathered NaN; step_batch returned a non-state cell")
    U_new = U.copy()
    U_new[cells] = best_q
    best_club[cells] = bc
    best_dir[cells] = bd
    return U_new, best_club, best_dir


def solve(
    hole: Hole,
    player: Player,
    mode: PenaltyMode,
    K: int = 200,
    tol: float = 0.01,
    max_sweeps: int = 100,
    seed: int = 0,
    log_every: int = 5,
    objective: Objective = "strokes",
) -> Solution:
    """Value iteration to residual < ``tol``; returns strokes-to-go and the greedy policy.

    ``objective`` other than ``"strokes"`` is part 16's risk-sensitive variant; see
    :data:`Objective`.
    """
    _lam(objective)  # validate up front
    draws = make_draws(K, seed)
    tables = build_offset_tables(player, draws)
    candidates = all_actions(player)
    playable, _ = state_mask(hole)
    U = initial_values(hole, player)
    club = np.full(U.shape, NO_ACTION, dtype=np.uint8)
    direction = np.full(U.shape, NO_ACTION, dtype=np.uint8)
    history: list[float] = []
    sweeps = 0
    for sweeps in range(1, max_sweeps + 1):
        t0 = time.perf_counter()
        U_new, club, direction = bellman_backup(
            U, hole, player, tables, mode, candidates, objective
        )
        residual = float(np.max(np.abs(U_new[playable] - U[playable])))
        history.append(residual)
        U = U_new
        if sweeps % log_every == 0 or residual < tol:
            log.info(
                "hole %s %s sweep %d residual %.4f (%.2f s)",
                hole.number,
                mode,
                sweeps,
                residual,
                time.perf_counter() - t0,
            )
        if residual < tol:
            break
    else:
        log.warning("hole %s %s: no convergence in %d sweeps", hole.number, mode, max_sweeps)
    return Solution(
        hole=hole.number,
        mode=mode,
        U=(-U).astype(np.float32),
        club=club,
        dir=direction,
        sweeps=sweeps,
        residual_history=history,
    )


def write_value_png(solution: Solution, hole: Hole, path: Path, arrow_every: int = 3) -> None:
    """Heatmap of strokes-to-go with greedy aim arrows every ``arrow_every`` cells.

    Arrows point along the absolute aim (pin bearing plus the relative direction) and
    are scaled by the chosen club's mean carry.
    """
    import matplotlib

    matplotlib.use("Agg")
    import matplotlib.pyplot as plt

    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    grid = solution.U.reshape(hole.rows, hole.cols)
    extent = (0.0, hole.cols * hole.cell_m, 0.0, hole.rows * hole.cell_m)
    fig, ax = plt.subplots(figsize=(6, 6 * hole.rows / hole.cols + 1))
    im = ax.imshow(grid, origin="lower", extent=extent, cmap="viridis_r")
    fig.colorbar(im, ax=ax, label="expected strokes to hole out")
    for kind, colour in (("water", "deepskyblue"), ("ob", "white"), ("bunker", "khaki")):
        mask = hole.lie == LIE_PLOT[kind]
        if mask.any():
            ax.contour(
                mask.astype(float),
                levels=[0.5],
                colors=colour,
                extent=extent,
                origin="lower",
                linewidths=0.8,
            )
    rr, cc = np.meshgrid(
        np.arange(0, hole.rows, arrow_every), np.arange(0, hole.cols, arrow_every), indexing="ij"
    )
    idx = (rr * hole.cols + cc).ravel()
    idx = idx[solution.dir[idx] != NO_ACTION]
    x, y = (idx % hole.cols + 0.5) * hole.cell_m, (idx // hole.cols + 0.5) * hole.cell_m
    bearing = pin_bearing_deg(hole, x, y) + DIRECTIONS_DEG[solution.dir[idx]]
    length = np.full(idx.shape, 2.0 * hole.cell_m)
    ax.quiver(
        x,
        y,
        length * np.sin(np.radians(bearing)),
        length * np.cos(np.radians(bearing)),
        angles="xy",
        scale_units="xy",
        scale=1,
        color="white",
        width=0.004,
    )
    ax.plot(*hole.tee_xy, "w^", ms=9)
    ax.plot(*hole.pin_xy, "r*", ms=11)
    ax.set_title(f"hole {solution.hole} {solution.mode}: strokes-to-go, {solution.sweeps} sweeps")
    ax.set_xlabel("x (m)")
    ax.set_ylabel("y (m)")
    fig.tight_layout()
    fig.savefig(path, dpi=110)
    plt.close(fig)
    log.info("wrote %s", path)
