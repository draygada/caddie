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

import numpy as np

from caddie.dispersion import Player
from caddie.geometry import Hole
from caddie.mdp import (
    DIRECTIONS_DEG,
    Lie,
    OffsetTables,
    PenaltyMode,
    build_offset_tables,
    make_draws,
    step_batch,
    terminal_values,
)

log = logging.getLogger(__name__)

NO_ACTION = 255
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


def bellman_backup(
    U: np.ndarray,
    hole: Hole,
    player: Player,
    tables: OffsetTables,
    mode: PenaltyMode,
    candidates: np.ndarray,
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
    for club_idx, dir_idx in candidates:
        nxt, r = step_batch(
            hole, player, cells, from_lie, int(club_idx), int(dir_idx), tables, mode
        )
        q = (r + U[nxt]).mean(axis=1)
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
) -> Solution:
    """Value iteration to residual < ``tol``; returns strokes-to-go and the greedy policy."""
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
        U_new, club, direction = bellman_backup(U, hole, player, tables, mode, candidates)
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
