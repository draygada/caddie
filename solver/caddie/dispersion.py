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
import json
import logging
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Protocol

import numpy as np
from scipy.optimize import minimize_scalar
from scipy.stats import norm

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


# --- slice 4: mishit rate by MLE (Ch 4.1) and fit_club -------------------------------


@dataclass
class ClubParams:
    mu_c: float
    sigma_theta_deg: float
    sigma_d: float
    p: float
    mu_r: float
    sigma_r: float
    sampled: bool
    stats: ClubStats | None  # None for interpolated clubs


P_BOUNDS: tuple[float, float] = (0.02, 0.25)
MISHIT_MEAN = -2.0  # fixed; not identifiable from 50 shots


def _mixture_nll(p: float, z: np.ndarray) -> float:
    lik = (1.0 - p) * norm.pdf(z) + p * norm.pdf(z - MISHIT_MEAN)
    return float(-np.sum(np.log(np.maximum(lik, 1e-300))))


def fit_p(
    carry: np.ndarray, mu_c: float, sigma_d: float, p_bounds: tuple[float, float] = P_BOUNDS
) -> float:
    """Mishit rate by bounded scalar MLE with mu_c and sigma_d held fixed.

    z = (c / mu_c - 1) / sigma_d; the constant -log(sigma_d mu_c) per shot does not
    depend on p and is omitted.
    """
    z = (np.asarray(carry, dtype=float) / mu_c - 1.0) / sigma_d
    res = minimize_scalar(_mixture_nll, bounds=p_bounds, args=(z,), method="bounded")
    return float(res.x)


def fit_club(club: str, shots: np.ndarray, handicap: int, driver_mu_hint: float) -> ClubParams:
    """prior_for -> fold every shot through update_club_stats -> posterior means -> fit_p."""
    stats = prior_for(club, handicap, driver_mu_hint)
    for row in shots:
        stats = update_club_stats(
            stats, float(row["carry_m"]), float(row["total_m"]), float(row["lateral_m"])
        )
    mu_c, sigma_theta, sigma_d, mu_r, sigma_r = params_from_stats(stats)
    p = fit_p(shots["carry_m"], mu_c, sigma_d)
    return ClubParams(
        mu_c=mu_c,
        sigma_theta_deg=sigma_theta,
        sigma_d=sigma_d,
        p=p,
        mu_r=mu_r,
        sigma_r=sigma_r,
        sampled=True,
        stats=stats,
    )


# --- slice 5: rough multipliers ----------------------------------------------------------

# Root contract defaults, used when fewer than MIN_ROUGH_SHOTS rough rows exist.
ROUGH_DEFAULTS: dict[str, float] = {"carry": 0.9, "sigma": 1.3, "roll": 0.5}
BUNKER_MULTIPLIERS: dict[str, float] = {"carry": 0.8, "sigma": 1.6, "roll": 0.0}
MIN_ROUGH_SHOTS = 15


def fit_rough_multipliers(
    mat7i: ClubParams, rough_shots: np.ndarray, handicap: int = 15
) -> dict[str, float]:
    """Lie multipliers for rough from the 7i rough sample against the 7i mat fit.

    carry = mu_c_rough / mu_c_mat; sigma = mean of the sigma_theta and sigma_d ratios;
    roll = mu_r_rough / mu_r_mat clipped to [0, 1]. The rough fit's prior is centred
    on the mat fit scaled by the default multipliers, so a thin sample shrinks toward
    the contract defaults rather than toward the mat values.
    """
    if len(rough_shots) < MIN_ROUGH_SHOTS:
        log.warning(
            "only %d rough shots (< %d): using default rough multipliers",
            len(rough_shots),
            MIN_ROUGH_SHOTS,
        )
        return dict(ROUGH_DEFAULTS)
    stats = prior_for("7i", handicap, mat7i.mu_c / PRIOR_CARRY_FRACTION_OF_DRIVER["7i"])
    stats.carry.m *= ROUGH_DEFAULTS["carry"]
    stats.roll.m *= ROUGH_DEFAULTS["roll"]
    for row in rough_shots:
        stats = update_club_stats(
            stats, float(row["carry_m"]), float(row["total_m"]), float(row["lateral_m"])
        )
    mu_c, sigma_theta, sigma_d, mu_r, _ = params_from_stats(stats)
    carry = mu_c / mat7i.mu_c
    sigma = 0.5 * (sigma_theta / mat7i.sigma_theta_deg + sigma_d / mat7i.sigma_d)
    roll = float(np.clip(mu_r / mat7i.mu_r, 0.0, 1.0)) if mat7i.mu_r > 0 else 0.0
    return {"carry": carry, "sigma": sigma, "roll": roll}


# --- slice 6: interpolate unsampled clubs ----------------------------------------------

PARTIAL_WEDGES: tuple[str, ...] = ("sw70", "sw50", "sw30")
PARTIAL_SPREAD_FACTOR = 1.2


def interpolate_clubs(sampled: dict[str, ClubParams]) -> dict[str, ClubParams]:
    """Fill the 12-club bag from the sampled clubs, in CLUB_ORDER.

    Unsampled full-swing clubs take mu_c from NOMINAL_CARRY times their reference
    club, and every other parameter linear in mu_c between the two nearest sampled
    clubs (clamped at the ends). Partial wedges copy sw with mu_c scaled and the two
    spread parameters multiplied by PARTIAL_SPREAD_FACTOR.
    """
    missing = [c for c in PRIOR_CARRY_FRACTION_OF_DRIVER if c not in sampled]
    if missing:
        raise ValueError(f"sampled clubs missing: {missing}")
    order = sorted(sampled, key=lambda c: sampled[c].mu_c)
    xs = np.array([sampled[c].mu_c for c in order])
    fields = ("sigma_theta_deg", "sigma_d", "p", "mu_r", "sigma_r")
    table = {f: np.array([getattr(sampled[c], f) for c in order]) for f in fields}

    out: dict[str, ClubParams] = {}
    for club in CLUB_ORDER:
        if club in sampled:
            out[club] = sampled[club]
            continue
        ratio = NOMINAL_CARRY[club]
        assert ratio is not None
        ref = sampled[NOMINAL_REF[club]]
        mu_c = ratio * ref.mu_c
        if club in PARTIAL_WEDGES:
            out[club] = ClubParams(
                mu_c=mu_c,
                sigma_theta_deg=ref.sigma_theta_deg * PARTIAL_SPREAD_FACTOR,
                sigma_d=ref.sigma_d * PARTIAL_SPREAD_FACTOR,
                p=ref.p,
                mu_r=ref.mu_r,
                sigma_r=ref.sigma_r,
                sampled=False,
                stats=None,
            )
            continue
        interp = {f: float(np.interp(mu_c, xs, table[f])) for f in fields}
        out[club] = ClubParams(mu_c=mu_c, **interp, sampled=False, stats=None)
    return out


# --- slice 7: Player and player.json -----------------------------------------------------

SAMPLED_CLUBS: tuple[str, ...] = tuple(PRIOR_CARRY_FRACTION_OF_DRIVER)
SIGMA_THETA_SANE: tuple[float, float] = (3.0, 12.0)


class PuttingLike(Protocol):
    """What part 02 needs from part 03's PuttingTable (which it cannot import)."""

    def to_json(self) -> dict: ...


@dataclass
class Player:
    handicap: int
    clubs: dict[str, ClubParams]
    club_order: list[str]
    lie: dict[str, dict[str, float]]  # multipliers per lie: carry, sigma, roll
    putting: PuttingLike


def build_player(shots_path: Path, putting: PuttingLike, handicap: int) -> Player:
    shots = load_shots(shots_path)
    missing = [c for c in SAMPLED_CLUBS if c not in shots]
    if missing:
        raise ValueError(f"{shots_path}: no rows for sampled clubs {missing}")
    driver_mu_hint = float(np.mean(shots["driver"]["carry_m"]))
    sampled: dict[str, ClubParams] = {}
    for club in SAMPLED_CLUBS:
        rows = shots[club][shots[club]["lie"] != "rough"]
        cp = fit_club(club, rows, handicap, driver_mu_hint)
        lo, hi = SIGMA_THETA_SANE
        if not lo <= cp.sigma_theta_deg <= hi:
            log.warning(
                "%s: sigma_theta %.1f deg outside [%g, %g]", club, cp.sigma_theta_deg, lo, hi
            )
        if cp.p <= P_BOUNDS[0] + 1e-3 or cp.p >= P_BOUNDS[1] - 1e-3:  # bounded MLE stops short
            log.warning("%s: p = %.3f pinned at a bound of %s", club, cp.p, P_BOUNDS)
        sampled[club] = cp
    rough_rows = shots["7i"][shots["7i"]["lie"] == "rough"]
    rough = fit_rough_multipliers(sampled["7i"], rough_rows, handicap)
    lie = {
        "tee": {"carry": 1.0, "sigma": 1.0, "roll": 1.0},
        "fairway": {"carry": 1.0, "sigma": 1.0, "roll": 1.0},
        "rough": rough,
        "bunker": dict(BUNKER_MULTIPLIERS),
    }
    return Player(
        handicap=handicap,
        clubs=interpolate_clubs(sampled),
        club_order=list(CLUB_ORDER),
        lie=lie,
        putting=putting,
    )


def _stats_to_json(stats: ClubStats | None) -> dict | None:
    if stats is None:
        return None
    return {
        "n": stats.n,
        "carry": asdict(stats.carry),
        "theta": asdict(stats.theta),
        "roll": asdict(stats.roll),
    }


def player_to_json(player: Player) -> dict:
    clubs = {}
    for club in player.club_order:
        cp = player.clubs[club]
        clubs[club] = {
            "mu_c": cp.mu_c,
            "sigma_theta_deg": cp.sigma_theta_deg,
            "sigma_d": cp.sigma_d,
            "p": cp.p,
            "mu_r": cp.mu_r,
            "sigma_r": cp.sigma_r,
            "sampled": cp.sampled,
            "stats": _stats_to_json(cp.stats),
        }
    return {
        "handicap": player.handicap,
        "clubs": clubs,
        "club_order": list(player.club_order),
        "lie": {k: dict(v) for k, v in player.lie.items()},
        "putting": player.putting.to_json(),
    }


def write_player_json(player: Player, path: Path) -> None:
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(player_to_json(player), indent=2) + "\n")


# --- slice 8: fixture for the TS port ------------------------------------------------------

# Five driver observations (carry_m, total_m, lateral_m) used only by the fixture.
STATS_FIXTURE_OBS: tuple[tuple[float, float, float], ...] = (
    (212.4, 231.0, -8.2),
    (219.9, 236.5, 4.1),
    (198.3, 214.0, 15.6),
    (225.0, 240.3, -2.0),
    (170.0, 188.0, 20.0),
)


def write_stats_updates_fixture(path: Path, driver_mu_hint: float = 215.0) -> None:
    """docs/fixtures/stats_updates.json: driver prior, 5 observations, ClubStats after each.

    The stretch goal's learn.ts must reproduce the `after` states to 1e-9.
    """
    prior = prior_for("driver", 15, driver_mu_hint)
    after = []
    s = prior
    for carry, total, lateral in STATS_FIXTURE_OBS:
        s = update_club_stats(s, carry, total, lateral)
        after.append(_stats_to_json(s))
    doc = {
        "club": "driver",
        "handicap": 15,
        "driver_mu_hint": driver_mu_hint,
        "observation_columns": ["carry_m", "total_m", "lateral_m"],
        "theta_rule": "theta_deg = degrees(atan2(lateral_m, carry_m)); roll = total_m - carry_m",
        "prior": _stats_to_json(prior),
        "observations": [list(o) for o in STATS_FIXTURE_OBS],
        "after": after,
    }
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(doc, indent=2) + "\n")
