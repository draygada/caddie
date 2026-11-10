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
from typing import Literal

import numpy as np
from scipy.stats import norm, qmc

from caddie.dispersion import MISHIT_MEAN, ClubParams

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


PenaltyMode = Literal["mulligan", "drop", "replay"]
PENALTY_MODES: tuple[PenaltyMode, ...] = ("mulligan", "drop", "replay")

DIRECTIONS_DEG: np.ndarray = np.arange(-90, 91, 2, dtype=float)


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
