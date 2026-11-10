"""Part 02: per-club shot distributions from simulator data, and player.json.

Model per club, independent components:
  direction  theta ~ N(0, sigma_theta^2) degrees, positive = golfer's right
  carry      c = mu_c (1 + sigma_d X),  X ~ (1 - p) N(0, 1) + p N(-2, 1)
  roll       r = total - carry ~ N(mu_r, sigma_r^2)

Carry, direction and roll are fit by conjugate Bayesian updating from a skill-band
prior (textbook Ch 4.2); the mishit rate p by maximum likelihood (Ch 4.1) with the
other carry parameters held at their posterior means.
"""

from __future__ import annotations

import csv
import logging
from dataclasses import dataclass
from pathlib import Path

import numpy as np

log = logging.getLogger(__name__)

SHOTS_COLUMNS: tuple[str, ...] = ("club", "carry_m", "total_m", "lateral_m", "lie", "date")
SHOT_DTYPE = np.dtype(
    [("carry_m", "f8"), ("total_m", "f8"), ("lateral_m", "f8"), ("lie", "U8"), ("date", "U10")]
)


# --- slice 1: loader -----------------------------------------------------------------


def load_shots(path: Path) -> dict[str, np.ndarray]:
    """Canonical shots CSV -> club -> structured array (carry_m, total_m, lateral_m, lie, date)."""
    rows: dict[str, list[tuple]] = {}
    with Path(path).open(newline="") as f:
        reader = csv.reader(f)
        header = next(reader, None)
        if header is None or tuple(h.strip() for h in header) != SHOTS_COLUMNS:
            raise ValueError(f"{path}: header must be {','.join(SHOTS_COLUMNS)}, got {header}")
        for line in reader:
            if not line or not any(line):
                continue
            club, carry, total, lateral, lie, date = (v.strip() for v in line)
            rows.setdefault(club, []).append(
                (float(carry), float(total), float(lateral), lie, date)
            )
    return {club: np.array(r, dtype=SHOT_DTYPE) for club, r in rows.items()}


# --- slice 2: conjugate updates (Ch 4.2) ----------------------------------------------


@dataclass
class NIG:
    """Normal-Inverse-Gamma state for a normal with unknown mean and variance."""

    m: float
    kappa: float
    alpha: float
    beta: float


@dataclass
class IG:
    """Inverse-Gamma state for the variance of a zero-mean normal."""

    alpha: float
    beta: float


@dataclass
class ClubStats:
    n: int
    carry: NIG
    theta: IG
    roll: NIG


def update_nig(s: NIG, x: float) -> NIG:
    kappa = s.kappa + 1.0
    m = (s.kappa * s.m + x) / kappa
    alpha = s.alpha + 0.5
    beta = s.beta + s.kappa * (x - s.m) ** 2 / (2.0 * kappa)
    return NIG(m=m, kappa=kappa, alpha=alpha, beta=beta)


def update_ig(s: IG, theta: float) -> IG:
    return IG(alpha=s.alpha + 0.5, beta=s.beta + theta**2 / 2.0)


def update_club_stats(stats: ClubStats, carry: float, total: float, lateral: float) -> ClubStats:
    """Fold one shot in. This exact function is what the on-course stretch goal calls."""
    theta = float(np.degrees(np.arctan2(lateral, carry)))
    return ClubStats(
        n=stats.n + 1,
        carry=update_nig(stats.carry, carry),
        theta=update_ig(stats.theta, theta),
        roll=update_nig(stats.roll, total - carry),
    )


def _nig_var(s: NIG) -> float:
    return s.beta / (s.alpha - 1.0)


def params_from_stats(stats: ClubStats) -> tuple[float, float, float, float, float]:
    """(mu_c, sigma_theta_deg, sigma_d, mu_r, sigma_r) as posterior means."""
    mu_c = stats.carry.m
    sigma_d = float(np.sqrt(_nig_var(stats.carry))) / mu_c
    sigma_theta = float(np.sqrt(stats.theta.beta / (stats.theta.alpha - 1.0)))
    mu_r = stats.roll.m
    sigma_r = float(np.sqrt(_nig_var(stats.roll)))
    return mu_c, sigma_theta, sigma_d, mu_r, sigma_r


# Prior strength: kappa = 5 pseudo-shots, alpha = 2.5 (part file).
PRIOR_KAPPA = 5.0
PRIOR_ALPHA = 2.5
PRIOR_SIGMA_D = 0.08
PRIOR_SIGMA_THETA_DEG = 7.0  # Broadie-Ko band for a 15 handicap
PRIOR_ROLL_FRACTION = 0.08
PRIOR_ROLL_SIGMA_M = 6.0

# Nominal carry of each SAMPLED club as a fraction of driver carry, used only to centre
# the prior (worth 5 pseudo-shots). NOT in the part file, which gives ratios only for
# unsampled clubs (NOMINAL_CARRY below); these are placeholders to be confirmed.
PRIOR_CARRY_FRACTION_OF_DRIVER: dict[str, float] = {
    "driver": 1.00,
    "5h": 0.80,
    "7i": 0.65,
    "9i": 0.55,
    "sw": 0.40,
}

NOMINAL_CARRY: dict[str, float | None] = {
    "driver": None,
    "3w": 0.92,
    "5h": None,
    "6i": 1.08,
    "7i": None,
    "8i": 0.92,
    "9i": None,
    "pw": 0.90,
    "sw": None,
    "sw70": 0.78,
    "sw50": 0.56,
    "sw30": 0.33,
}
# Reference sampled club for each NOMINAL_CARRY ratio.
NOMINAL_REF: dict[str, str] = {
    "3w": "driver",
    "6i": "7i",
    "8i": "7i",
    "pw": "9i",
    "sw70": "sw",
    "sw50": "sw",
    "sw30": "sw",
}
CLUB_ORDER: list[str] = list(NOMINAL_CARRY)


def nominal_carry(club: str, driver_mu_hint: float) -> float:
    """Nominal carry in meters for any club in the bag, scaled to the driver estimate."""
    if club in PRIOR_CARRY_FRACTION_OF_DRIVER:
        return PRIOR_CARRY_FRACTION_OF_DRIVER[club] * driver_mu_hint
    ratio = NOMINAL_CARRY.get(club)
    if ratio is None:
        raise ValueError(f"no nominal carry for club {club!r}")
    return ratio * nominal_carry(NOMINAL_REF[club], driver_mu_hint)


def prior_for(club: str, handicap: int, driver_mu_hint: float) -> ClubStats:
    """Skill-band prior worth PRIOR_KAPPA pseudo-shots.

    `handicap` is accepted for the interface; the part file gives one band (15 hcp),
    so it does not change the prior yet.
    """
    m = nominal_carry(club, driver_mu_hint)
    a1 = PRIOR_ALPHA - 1.0  # so that beta / (alpha - 1) equals the target variance
    carry = NIG(m=m, kappa=PRIOR_KAPPA, alpha=PRIOR_ALPHA, beta=(PRIOR_SIGMA_D * m) ** 2 * a1)
    theta = IG(alpha=PRIOR_ALPHA, beta=PRIOR_SIGMA_THETA_DEG**2 * a1)
    roll = NIG(
        m=PRIOR_ROLL_FRACTION * m,
        kappa=PRIOR_KAPPA,
        alpha=PRIOR_ALPHA,
        beta=PRIOR_ROLL_SIGMA_M**2 * a1,
    )
    return ClubStats(n=0, carry=carry, theta=theta, roll=roll)
