"""Part 07: evaluate the policy against baselines (Ch 14.1) and its robustness to the
dispersion fit (Ch 14.3). Produces the tables and figures for the report.

Simulation reuses :func:`caddie.mdp.step_batch`, the solver's own transition, so a gap
between the simulated mean and the value grid is a bug and not a modelling difference.
"""

from __future__ import annotations

import logging
from collections.abc import Callable

import numpy as np

from caddie.dispersion import Player
from caddie.geometry import Hole
from caddie.mdp import DIRECTIONS_DEG, Lie, pin_bearing_deg
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
