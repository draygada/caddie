"""Part 03: expected putts as a function of distance to the pin.

A Shot Scope make-rate table (one row per distance bin, feet) is turned into
``E[putts](d)`` by iterating the one-step recursion

    E[putts](d) = make(d) + (1 - make(d)) * (1 + E[putts](leave(d)))

to a fixed point on a 0.25 m grid. Green cells use ``-E[putts]`` as their
terminal value in the MDP.
"""

from __future__ import annotations

import csv
import logging
from dataclasses import dataclass
from pathlib import Path

import numpy as np

log = logging.getLogger(__name__)

FT_TO_M = 0.3048
MAKE_COLUMNS = ("distance_ft_lo", "distance_ft_hi", "make_pct")
GRID_STEP_M = 0.25
GRID_MAX_M = 40.0
LEAVE_FRAC = 0.12
LEAVE_MIN_M = 0.6
FIXED_POINT_TOL = 1e-9
FIXED_POINT_MAX_ITER = 1000
CONTRACT_DISTANCES_M = (1, 2, 3, 4, 6, 8, 10, 15, 25)


def load_make_table(path: Path) -> tuple[np.ndarray, np.ndarray]:
    """Read ``putting.csv``; return bin midpoints in meters and make probabilities.

    Rows are sorted by midpoint. Percentages in the file become probabilities.
    """
    with Path(path).open(newline="") as fh:
        reader = csv.reader(fh)
        header = tuple(h.strip() for h in next(reader))
        if header != MAKE_COLUMNS:
            raise ValueError(f"putting.csv header must be {MAKE_COLUMNS}, got {header}")
        rows = [tuple(float(v) for v in row) for row in reader if row]
    if not rows:
        raise ValueError(f"putting.csv at {path} has no data rows")
    arr = np.asarray(rows, dtype=float)
    lo_ft, hi_ft, pct = arr[:, 0], arr[:, 1], arr[:, 2]
    if np.any(hi_ft <= lo_ft):
        raise ValueError("each putting bin needs distance_ft_hi > distance_ft_lo")
    mids_m = 0.5 * (lo_ft + hi_ft) * FT_TO_M
    probs = pct / 100.0
    order = np.argsort(mids_m)
    log.info("loaded %d putting bins from %s", len(rows), path)
    return mids_m[order], probs[order]


def make_prob(d_m: float | np.ndarray, mids_m: np.ndarray, probs: np.ndarray) -> np.ndarray:
    """Make probability at distance ``d_m`` (meters).

    Linear interpolation through (0, 1.0) and the bin midpoints; clamped at
    the last bin's probability beyond the last midpoint. Negative distances
    are treated as 0.
    """
    xs = np.concatenate(([0.0], np.asarray(mids_m, dtype=float)))
    ys = np.concatenate(([1.0], np.asarray(probs, dtype=float)))
    d = np.maximum(np.asarray(d_m, dtype=float), 0.0)
    return np.interp(d, xs, ys)


def leave_distance(d_m: np.ndarray, leave_frac: float, leave_min_m: float) -> np.ndarray:
    """Expected leave after a missed putt from ``d_m``: max(leave_min_m, leave_frac * d)."""
    return np.maximum(leave_min_m, leave_frac * np.asarray(d_m, dtype=float))


def solve_expected_putts(
    grid_m: np.ndarray,
    mids_m: np.ndarray,
    probs: np.ndarray,
    leave_frac: float = LEAVE_FRAC,
    leave_min_m: float = LEAVE_MIN_M,
    tol: float = FIXED_POINT_TOL,
    max_iter: int = FIXED_POINT_MAX_ITER,
) -> tuple[np.ndarray, int]:
    """Iterate E(d) = make(d) + (1 - make(d)) (1 + E(leave(d))) on ``grid_m`` to a fixed point.

    E(leave(d)) is read off the current iterate by linear interpolation on the
    grid. Returns the converged array and the number of sweeps used.
    """
    make = make_prob(grid_m, mids_m, probs)
    leave = leave_distance(grid_m, leave_frac, leave_min_m)
    expected = np.ones_like(grid_m)
    n_iter = 0
    delta = np.inf
    while n_iter < max_iter and delta >= tol:
        n_iter += 1
        e_leave = np.interp(leave, grid_m, expected)
        updated = make + (1.0 - make) * (1.0 + e_leave)
        delta = float(np.max(np.abs(updated - expected)))
        expected = updated
    if delta >= tol:
        log.warning("putting recursion did not converge in %d sweeps (delta %.2e)", max_iter, delta)
    log.info("putting recursion converged in %d sweeps", n_iter)
    return expected, n_iter


@dataclass
class PuttingTable:
    """Expected putts on a regular distance grid, linearly interpolated between nodes."""

    distance_m: np.ndarray
    expected_putts: np.ndarray

    def __call__(self, d_m: float | np.ndarray) -> np.ndarray:
        """E[putts] at ``d_m``.

        Linear interpolation on the grid; clamped at 0 below the grid and
        extrapolated linearly with the final slope beyond it.
        """
        d = np.asarray(d_m, dtype=float)
        inside = np.interp(d, self.distance_m, self.expected_putts)
        slope = (self.expected_putts[-1] - self.expected_putts[-2]) / (
            self.distance_m[-1] - self.distance_m[-2]
        )
        beyond = self.expected_putts[-1] + slope * (d - self.distance_m[-1])
        return np.where(d > self.distance_m[-1], beyond, inside)

    def to_json(self) -> dict:
        """The ``putting`` block of ``player.json`` at the contract's nine distances."""
        values = self(np.asarray(CONTRACT_DISTANCES_M, dtype=float))
        return {
            "distance_m": [int(d) for d in CONTRACT_DISTANCES_M],
            "expected_putts": [round(float(v), 3) for v in values],
        }


def build_putting_table(
    path: Path, leave_frac: float = LEAVE_FRAC, leave_min_m: float = LEAVE_MIN_M
) -> PuttingTable:
    """Load the make table at ``path`` and solve E[putts] on the 0.25 m grid to 40 m."""
    mids_m, probs = load_make_table(path)
    grid = np.arange(0.0, GRID_MAX_M + GRID_STEP_M / 2, GRID_STEP_M)
    expected, _ = solve_expected_putts(grid, mids_m, probs, leave_frac, leave_min_m)
    return PuttingTable(distance_m=grid, expected_putts=expected)


def write_putting_png(table: PuttingTable, path: Path) -> None:
    """Plot E[putts] against distance (the part's Done-when check)."""
    import matplotlib

    matplotlib.use("Agg")
    import matplotlib.pyplot as plt

    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    fig, ax = plt.subplots(figsize=(7, 4))
    ax.plot(table.distance_m, table.expected_putts, lw=2)
    block = table.to_json()
    ax.plot(block["distance_m"], block["expected_putts"], "o", label="player.json points")
    ax.set_xlabel("distance to pin (m)")
    ax.set_ylabel("expected putts")
    ax.set_title("Expected putts from the Shot Scope make-rate table")
    ax.grid(alpha=0.3)
    ax.legend()
    fig.tight_layout()
    fig.savefig(path, dpi=120)
    plt.close(fig)
    log.info("wrote %s", path)
