"""Synthetic holes and the round-number player for part 16 (docs/parts/16-benchmark.md).

Every hole is 12 x 70 cells of 5 m (60 x 350 m), tee at (30, 2.5), a round green of
radius 12.5 m centred at y = 330 whose centroid is the pin, par 4. The builders differ
only in the hazards they add. Numbers here are benchmark settings, not the fitted player.
"""

from __future__ import annotations

import numpy as np

from caddie.dispersion import ClubParams, Player
from caddie.geometry import Hole, compute_drop_index
from caddie.mdp import Lie
from caddie.putting import PuttingTable

ROWS, COLS, CELL_M = 70, 12, 5.0
TEE_XY = (30.0, 2.5)
GREEN_CENTRE = (30.0, 330.0)
GREEN_RADIUS_M = 12.5
PAR = 4

# the root data contract's lie multipliers and putting table
LIE_MULT = {
    "tee": {"carry": 1.0, "sigma": 1.0, "roll": 1.0},
    "fairway": {"carry": 1.0, "sigma": 1.0, "roll": 1.0},
    "rough": {"carry": 0.9, "sigma": 1.3, "roll": 0.5},
    "bunker": {"carry": 0.8, "sigma": 1.6, "roll": 0.0},
}
PUTTING_DISTANCE_M = [1, 2, 3, 4, 6, 8, 10, 15, 25]
PUTTING_EXPECTED = [1.07, 1.41, 1.64, 1.78, 1.85, 1.93, 1.98, 2.15, 2.4]


def _cell_centres() -> tuple[np.ndarray, np.ndarray]:
    cx = (np.arange(COLS) + 0.5) * CELL_M
    cy = (np.arange(ROWS) + 0.5) * CELL_M
    return np.meshgrid(cx, cy)


def _finish(lie: np.ndarray, number: int) -> Hole:
    xx, yy = _cell_centres()
    green = np.hypot(xx - GREEN_CENTRE[0], yy - GREEN_CENTRE[1]) <= GREEN_RADIUS_M
    lie[green] = int(Lie.GREEN)
    pin_xy = (float(xx[green].mean()), float(yy[green].mean()))
    return Hole(
        number=number,
        par=PAR,
        cell_m=CELL_M,
        rows=ROWS,
        cols=COLS,
        origin_lat=0.0,
        origin_lon=0.0,
        rotation_deg=0.0,
        tee_xy=TEE_XY,
        tees={"black": TEE_XY},
        pin_xy=pin_xy,
        lie=lie,
        drop_index=compute_drop_index(lie, TEE_XY, CELL_M),
    )


def open_straight() -> Hole:
    """Fairway everywhere: the no-hazard control."""
    lie = np.full((ROWS, COLS), int(Lie.FAIRWAY), dtype=np.uint8)
    return _finish(lie, number=901)


def water_carry(water_from_m: float = 180.0, water_to_m: float = 200.0) -> Hole:
    """``open_straight`` plus a water band across the full width between the two y values."""
    lie = np.full((ROWS, COLS), int(Lie.FAIRWAY), dtype=np.uint8)
    _, yy = _cell_centres()
    lie[(yy >= water_from_m) & (yy <= water_to_m)] = int(Lie.WATER)
    return _finish(lie, number=902)


def ob_side() -> Hole:
    """OB on columns 0 and 1, fairway on columns 2 to 7, rough on columns 8 to 11."""
    lie = np.full((ROWS, COLS), int(Lie.FAIRWAY), dtype=np.uint8)
    lie[:, 0:2] = int(Lie.OB)
    lie[:, 8:] = int(Lie.ROUGH)
    return _finish(lie, number=903)


BUNKER_FRONT_ROW = 63
BUNKER_FRONT_COLS = (5, 6, 7)


def bunker_front() -> Hole:
    """``open_straight`` plus bunkers in the three cells directly short of the green."""
    lie = np.full((ROWS, COLS), int(Lie.FAIRWAY), dtype=np.uint8)
    for c in BUNKER_FRONT_COLS:
        lie[BUNKER_FRONT_ROW, c] = int(Lie.BUNKER)
    return _finish(lie, number=904)


HOLE_BUILDERS = {
    "open_straight": open_straight,
    "water_carry": water_carry,
    "ob_side": ob_side,
    "bunker_front": bunker_front,
}


def three_club(driver_mu_c: float = 200.0) -> Player:
    """Driver, 7i and pw with round numbers; lie multipliers and putting from the contract."""

    def club(mu_c, sigma_theta_deg, sigma_d, p, mu_r, sigma_r) -> ClubParams:
        return ClubParams(
            mu_c=mu_c,
            sigma_theta_deg=sigma_theta_deg,
            sigma_d=sigma_d,
            p=p,
            mu_r=mu_r,
            sigma_r=sigma_r,
            sampled=True,
            stats=None,
        )

    clubs = {
        "driver": club(driver_mu_c, 6.0, 0.07, 0.10, 15.0, 8.0),
        "7i": club(140.0, 4.0, 0.05, 0.05, 5.0, 3.0),
        "pw": club(100.0, 3.5, 0.05, 0.05, 2.0, 1.0),
    }
    putting = PuttingTable(
        distance_m=np.asarray(PUTTING_DISTANCE_M, dtype=float),
        expected_putts=np.asarray(PUTTING_EXPECTED, dtype=float),
    )
    return Player(
        handicap=15,
        clubs=clubs,
        club_order=["driver", "7i", "pw"],
        lie={k: dict(v) for k, v in LIE_MULT.items()},
        putting=putting,
    )


PLAYER_BUILDERS = {"three_club": three_club}
