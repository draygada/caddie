"""The 10 x 10 toy hole from solver/CLAUDE.md, used by every test from part 04 on."""

from __future__ import annotations

import numpy as np

from caddie.dispersion import ClubParams, Player
from caddie.geometry import Hole, compute_drop_index
from caddie.mdp import Lie

TOY_CLUB = "test7i"
ROWS = COLS = 10
CELL_M = 5.0
PIN_RC = (9, 5)
GREEN_RADIUS_M = 7.5


class FlatPutting:
    """Putting table that is 1.5 putts everywhere."""

    expected = 1.5

    def __call__(self, d_m):
        return np.full_like(np.asarray(d_m, dtype=float), self.expected)

    def to_json(self) -> dict:
        return {"distance_m": [1], "expected_putts": [self.expected]}


def toy_player() -> Player:
    club = ClubParams(
        mu_c=25.0,
        sigma_theta_deg=4.0,
        sigma_d=0.05,
        p=0.05,
        mu_r=2.0,
        sigma_r=1.0,
        sampled=True,
        stats=None,
    )
    lie = {
        "tee": {"carry": 1.0, "sigma": 1.0, "roll": 1.0},
        "fairway": {"carry": 1.0, "sigma": 1.0, "roll": 1.0},
        "rough": {"carry": 0.9, "sigma": 1.3, "roll": 0.5},
        "bunker": {"carry": 0.8, "sigma": 1.6, "roll": 0.0},
    }
    return Player(
        handicap=15, clubs={TOY_CLUB: club}, club_order=[TOY_CLUB], lie=lie, putting=FlatPutting()
    )


def toy_hole(hazards: bool = True) -> Hole:
    """10 x 10 fairway hole, cell 5 m, tee row 0, pin at cell (9, 5).

    With ``hazards``: bunker at (5, 4) and (5, 5); water at row 7, cols 0 to 3;
    OB at col 9. Green is every cell within 7.5 m of the pin.
    """
    lie = np.full((ROWS, COLS), int(Lie.FAIRWAY), dtype=np.uint8)
    cx = (np.arange(COLS) + 0.5) * CELL_M
    cy = (np.arange(ROWS) + 0.5) * CELL_M
    pin_xy = (float(cx[PIN_RC[1]]), float(cy[PIN_RC[0]]))
    xx, yy = np.meshgrid(cx, cy)
    lie[np.hypot(xx - pin_xy[0], yy - pin_xy[1]) <= GREEN_RADIUS_M] = int(Lie.GREEN)
    if hazards:
        lie[5, 4] = lie[5, 5] = int(Lie.BUNKER)
        lie[7, 0:4] = int(Lie.WATER)
        lie[:, 9] = int(Lie.OB)
    tee_xy = (float(cx[5]), float(cy[0]))
    return Hole(
        number=0,
        par=3,
        cell_m=CELL_M,
        rows=ROWS,
        cols=COLS,
        origin_lat=0.0,
        origin_lon=0.0,
        rotation_deg=0.0,
        tee_xy=tee_xy,
        tees={"black": tee_xy},
        pin_xy=pin_xy,
        lie=lie,
        drop_index=compute_drop_index(lie, tee_xy, CELL_M),
    )
