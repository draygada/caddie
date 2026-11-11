"""Part 07: evaluate the policy against baselines (Ch 14.1) and its robustness to the
dispersion fit (Ch 14.3). Produces the tables and figures for the report.

Simulation reuses :func:`caddie.mdp.step_batch`, the solver's own transition, so a gap
between the simulated mean and the value grid is a bug and not a modelling difference.
"""

from __future__ import annotations

import csv
import logging
import tempfile
from collections.abc import Callable
from pathlib import Path

import numpy as np

from caddie.dispersion import SHOTS_COLUMNS, Player, build_player, load_shots
from caddie.geometry import Hole
from caddie.mdp import (
    DIRECTIONS_DEG,
    Lie,
    PenaltyMode,
    build_offset_tables,
    make_draws,
    pin_bearing_deg,
    step_batch,
    terminal_values,
)
from caddie.putting import build_putting_table
from caddie.value_iteration import NO_ACTION, Solution

log = logging.getLogger(__name__)

# --- slice 1: policies -------------------------------------------------------------------------

Policy = Callable[[float, float, Lie], tuple[int, int]]
"""``policy(x, y, lie) -> (club_idx, dir_idx)`` at a continuous point."""

DIR0 = int(np.flatnonzero(DIRECTIONS_DEG == 0)[0])


def _cell_index(hole: Hole, x: float, y: float) -> int:
    r = min(max(int(np.floor(y / hole.cell_m)), 0), hole.rows - 1)
    c = min(max(int(np.floor(x / hole.cell_m)), 0), hole.cols - 1)
    return r * hole.cols + c


def _nearest_dir_index(rel_deg: float) -> int:
    return int(np.argmin(np.abs(DIRECTIONS_DEG - rel_deg)))


def optimal_policy(solution: Solution, hole: Hole) -> Policy:
    """Nearest-cell lookup in the solved club and direction grids."""

    def policy(x: float, y: float, lie: Lie) -> tuple[int, int]:
        idx = _cell_index(hole, x, y)
        club, direction = int(solution.club[idx]), int(solution.dir[idx])
        if club == NO_ACTION or direction == NO_ACTION:
            raise ValueError(f"no action at ({x:.1f}, {y:.1f}): terminal or off the hole")
        return club, direction

    return policy


def pin_policy(hole: Hole, player: Player) -> Policy:
    """Aim at the pin with the longest club whose mean carry is at most the distance.

    When every club carries farther than the pin, the shortest club is used (the part
    file says "the longest club" here, which would hit a driver from ten metres; flagged).
    """
    mu = np.array([player.clubs[name].mu_c for name in player.club_order])

    def policy(x: float, y: float, lie: Lie) -> tuple[int, int]:
        dist = float(np.hypot(hole.pin_xy[0] - x, hole.pin_xy[1] - y))
        reach = np.flatnonzero(mu <= dist)
        club = int(reach[np.argmax(mu[reach])]) if reach.size else int(np.argmin(mu))
        return club, DIR0

    return policy


def green_centroid(hole: Hole) -> tuple[float, float]:
    r, c = np.nonzero(hole.lie == int(Lie.GREEN))
    if r.size == 0:
        raise ValueError("hole has no green cells")
    return float(np.mean((c + 0.5) * hole.cell_m)), float(np.mean((r + 0.5) * hole.cell_m))


def centre_policy(hole: Hole, player: Player) -> Policy:
    """Aim at the green centroid with the club whose mean carry is closest to that distance."""
    mu = np.array([player.clubs[name].mu_c for name in player.club_order])
    gx, gy = green_centroid(hole)

    def policy(x: float, y: float, lie: Lie) -> tuple[int, int]:
        dist = float(np.hypot(gx - x, gy - y))
        club = int(np.argmin(np.abs(mu - dist)))
        bearing_centroid = float(np.degrees(np.arctan2(gx - x, gy - y)))
        bearing_pin = float(pin_bearing_deg(hole, np.array([x]), np.array([y]))[0])
        rel = (bearing_centroid - bearing_pin + 180.0) % 360.0 - 180.0
        return club, _nearest_dir_index(rel)

    return policy


# --- slice 2: simulate ------------------------------------------------------------------------

SIM_DRAWS = 200
MAX_SIM_SHOTS = 40


def simulate(
    hole: Hole,
    player: Player,
    policy: Policy,
    mode: PenaltyMode,
    n: int,
    seed: int,
) -> np.ndarray:
    """Strokes to hole out for ``n`` plays from the Black tee under ``policy``.

    Cell-to-cell play with :func:`caddie.mdp.step_batch` on ``SIM_DRAWS`` Halton draws
    built from ``seed``; each play picks one draw column per shot from a generator also
    seeded by ``seed``, so two policies simulated with the same seed and ``n`` see the
    same draws (paired comparison). A play ends on a green cell, adding the expected
    putts from the cell centre, or after ``MAX_SIM_SHOTS`` shots.
    """
    rng = np.random.default_rng(seed)
    draws = make_draws(SIM_DRAWS, seed)
    tables = build_offset_tables(player, draws)
    flat = hole.lie.reshape(-1)
    tee = _cell_index(hole, *hole.tee_xy)
    idx = np.full(n, tee, dtype=np.int64)
    strokes = np.zeros(n)
    active = np.ones(n, dtype=bool)
    terminal = terminal_values(hole, player.putting)  # -E[putts] on green, NaN elsewhere
    # draw columns are sampled up front so the sequence does not depend on the policy
    columns = rng.integers(0, SIM_DRAWS, size=(MAX_SIM_SHOTS, n))
    for shot in range(MAX_SIM_SHOTS):
        if not active.any():
            break
        alive = np.flatnonzero(active)
        cells = idx[alive]
        lies = flat[cells]
        actions = np.empty((alive.size, 2), dtype=np.int64)
        for k, cell in enumerate(cells):
            r, c = divmod(int(cell), hole.cols)
            x, y = (c + 0.5) * hole.cell_m, (r + 0.5) * hole.cell_m
            actions[k] = policy(x, y, Lie(int(lies[k])))
        for club_idx, dir_idx in {tuple(a) for a in actions.tolist()}:
            group = np.flatnonzero((actions[:, 0] == club_idx) & (actions[:, 1] == dir_idx))
            plays = alive[group]
            nxt, reward = step_batch(
                hole, player, cells[group], lies[group], int(club_idx), int(dir_idx), tables, mode
            )
            col = columns[shot, plays]
            rows = np.arange(group.size)
            idx[plays] = nxt[rows, col]
            strokes[plays] += -reward[rows, col]
        landed_green = active & (flat[idx] == int(Lie.GREEN))
        strokes[landed_green] += -terminal[idx[landed_green]]
        active &= ~landed_green
    if active.any():
        log.warning(
            "%d of %d plays did not hole out in %d shots", int(active.sum()), n, MAX_SIM_SHOTS
        )
    return strokes


# --- slice 3: evaluate_hole ----------------------------------------------------------------------

BLOWUP_OVER_PAR = 3
STROKES_SAVED_LABEL = (
    "extrapolation: 18 x (baseline mean - optimal mean) on this hole, as if every hole "
    "of a round were this one"
)


def disagreement(hole: Hole, solution: Solution, policy: Policy) -> float:
    """Fraction of non-terminal playable cells where ``policy`` differs from the solution."""
    flat = hole.lie.reshape(-1)
    cells = np.flatnonzero(
        np.isin(flat, [int(Lie.TEE), int(Lie.FAIRWAY), int(Lie.ROUGH), int(Lie.BUNKER)])
        & (solution.club != NO_ACTION)
    )
    if cells.size == 0:
        return float("nan")
    differ = 0
    for cell in cells:
        r, c = divmod(int(cell), hole.cols)
        x, y = (c + 0.5) * hole.cell_m, (r + 0.5) * hole.cell_m
        club, direction = policy(x, y, Lie(int(flat[cell])))
        differ += club != int(solution.club[cell]) or direction != int(solution.dir[cell])
    return differ / cells.size


def _metrics(strokes: np.ndarray, par: int) -> dict:
    rounded = np.rint(strokes).astype(int)
    values, counts = np.unique(rounded, return_counts=True)
    return {
        "mean_strokes": float(strokes.mean()),
        "std_strokes": float(strokes.std(ddof=1)) if strokes.size > 1 else 0.0,
        "histogram": {int(v): int(k) for v, k in zip(values, counts, strict=True)},
        "p_blowup": float(np.mean(strokes >= par + BLOWUP_OVER_PAR)),
    }


def evaluate_hole(
    hole: Hole,
    player: Player,
    solution: Solution,
    mode: PenaltyMode,
    n: int = 2000,
    seed: int = 0,
) -> dict:
    """Metrics for the optimal, pin and centre policies on one hole and mode.

    The histogram bins scores rounded to the nearest whole stroke (the simulation adds
    expected putts, which are fractional). ``strokes_saved_per_round`` is labelled as an
    extrapolation in ``strokes_saved_label``.
    """
    policies = {
        "optimal": optimal_policy(solution, hole),
        "pin": pin_policy(hole, player),
        "centre": centre_policy(hole, player),
    }
    out: dict[str, dict] = {}
    for name, policy in policies.items():
        strokes = simulate(hole, player, policy, mode, n=n, seed=seed)
        m = _metrics(strokes, hole.par)
        m["disagreement"] = 0.0 if name == "optimal" else disagreement(hole, solution, policy)
        out[name] = m
        log.info(
            "hole %s %s %s: mean %.3f sd %.3f blowup %.3f disagreement %.3f",
            hole.number,
            mode,
            name,
            m["mean_strokes"],
            m["std_strokes"],
            m["p_blowup"],
            m["disagreement"],
        )
    optimal_mean = out["optimal"]["mean_strokes"]
    for m in out.values():
        m["strokes_saved_per_round"] = 18.0 * (m["mean_strokes"] - optimal_mean)
    return {
        "hole": hole.number,
        "mode": mode,
        "par": hole.par,
        "n": n,
        "seed": seed,
        "policies": out,
        "strokes_saved_label": STROKES_SAVED_LABEL,
    }


# --- slice 4: bootstrap the fit (Ch 14.3) --------------------------------------------------------

SOLVER_DIR = Path(__file__).resolve().parents[1]
DEFAULT_PUTTING = SOLVER_DIR / "data" / "raw" / "putting.csv"
DEFAULT_HANDICAP = 15  # root CLAUDE.md


def bootstrap_fit(
    shots_path: Path,
    n_boot: int = 50,
    seed: int = 0,
    putting_path: Path = DEFAULT_PUTTING,
    handicap: int = DEFAULT_HANDICAP,
) -> list[Player]:
    """Refit the player ``n_boot`` times on shots resampled per club with replacement.

    Each resample is written as a canonical CSV to a temporary file and fitted with
    part 02's ``build_player``, so the bootstrap sees exactly the production fit.
    """
    shots = load_shots(shots_path)
    putting = build_putting_table(Path(putting_path))
    rng = np.random.default_rng(seed)
    players: list[Player] = []
    with tempfile.TemporaryDirectory() as tmp:
        for b in range(n_boot):
            path = Path(tmp) / f"boot_{b}.csv"
            with path.open("w", newline="") as f:
                writer = csv.writer(f)
                writer.writerow(SHOTS_COLUMNS)
                for club, rows in shots.items():
                    pick = rng.integers(0, len(rows), size=len(rows))
                    for row in rows[pick]:
                        writer.writerow(
                            [
                                club,
                                f"{row['carry_m']:.3f}",
                                f"{row['total_m']:.3f}",
                                f"{row['lateral_m']:.3f}",
                                row["lie"],
                                row["date"],
                            ]
                        )
            players.append(build_player(path, putting, handicap))
    log.info("bootstrapped %d players from %s", n_boot, shots_path)
    return players
