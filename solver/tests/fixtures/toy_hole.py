"""The 10 x 10 toy hole from solver/CLAUDE.md, used by every test from part 04 on."""

from __future__ import annotations

import numpy as np

from caddie.dispersion import ClubParams, Player

TOY_CLUB = "test7i"


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
