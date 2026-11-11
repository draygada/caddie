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


MAX_SHOTS = 30


def brute_force_value_at_tee(
    mode: str, n: int = 20000, rng: np.random.Generator | None = None
) -> float:
    """Mean strokes to hole out from the tee with the policy "aim at the pin with test7i".

    Independent Monte Carlo (fresh draws, continuous aim), not the Halton
    tables, so it cross-checks the transition rules. Not optimal: value
    iteration must do at least as well.
    """
    from caddie.dispersion import MISHIT_MEAN

    rng = np.random.default_rng(0) if rng is None else rng
    hole = toy_hole()
    player = toy_player()
    club = player.clubs[TOY_CLUB]
    flat = hole.lie.reshape(-1)
    px, py = hole.pin_xy
    roll_by_lie = np.zeros(8)
    for code, name in ((1, "tee"), (2, "fairway"), (3, "rough"), (4, "bunker")):
        roll_by_lie[code] = player.lie[name]["roll"]
    roll_by_lie[5] = 1.0
    sigma_by_lie = np.ones(8)
    carry_by_lie = np.ones(8)
    for code, name in ((1, "tee"), (2, "fairway"), (3, "rough"), (4, "bunker")):
        sigma_by_lie[code] = player.lie[name]["sigma"]
        carry_by_lie[code] = player.lie[name]["carry"]

    def locate(x, y):
        r = np.floor(y / CELL_M).astype(int)
        c = np.floor(x / CELL_M).astype(int)
        outside = (r < 0) | (r >= ROWS) | (c < 0) | (c >= COLS)
        idx = np.clip(r, 0, ROWS - 1) * COLS + np.clip(c, 0, COLS - 1)
        lie = flat[idx].astype(int)
        lie = np.where(outside | (lie == 0), 7, lie)
        return idx, lie

    tee_idx = int(hole.tee_xy[1] // CELL_M) * COLS + int(hole.tee_xy[0] // CELL_M)
    idx = np.full(n, tee_idx)
    strokes = np.zeros(n)
    active = np.ones(n, dtype=bool)
    playable_idx = np.flatnonzero(np.isin(flat, [1, 2, 3, 4, 5]))
    pr, pc = np.divmod(playable_idx, COLS)
    playable_xy = np.column_stack(((pc + 0.5) * CELL_M, (pr + 0.5) * CELL_M))
    for _ in range(MAX_SHOTS):
        if not active.any():
            break
        a = np.flatnonzero(active)
        r, c = np.divmod(idx[a], COLS)
        x, y = (c + 0.5) * CELL_M, (r + 0.5) * CELL_M
        lie = flat[idx[a]].astype(int)
        aim = np.degrees(np.arctan2(px - x, py - y))
        theta = club.sigma_theta_deg * sigma_by_lie[lie] * rng.standard_normal(a.size)
        z = rng.standard_normal(a.size)
        xmix = np.where(rng.random(a.size) < club.p, z + MISHIT_MEAN, z)
        carry = club.mu_c * carry_by_lie[lie] * (1 + club.sigma_d * sigma_by_lie[lie] * xmix)
        b = np.radians(aim + theta)
        lx, ly = x + carry * np.sin(b), y + carry * np.cos(b)
        _, land_lie = locate(lx, ly)
        run = (
            (club.mu_r + club.sigma_r * rng.standard_normal(a.size))
            * roll_by_lie[lie]
            * roll_by_lie[land_lie]
        )
        ux, uy = np.sin(np.radians(aim)), np.cos(np.radians(aim))
        fx, fy = lx + ux * run, ly + uy * run
        fidx, flie = locate(fx, fy)
        hazard = (flie == 6) | (flie == 7)
        strokes[a] += np.where(hazard & (mode != "mulligan"), 2.0, 1.0)
        nxt = fidx.copy()
        if mode in ("mulligan", "replay"):
            nxt[hazard] = idx[a][hazard]
        else:
            water = flie == 6
            nxt[water] = hole.drop_index.reshape(-1)[fidx[water]]
            ob = flie == 7
            if ob.any():
                d = np.hypot(
                    playable_xy[:, 0][None] - fx[ob][:, None],
                    playable_xy[:, 1][None] - fy[ob][:, None],
                )
                nxt[ob] = playable_idx[np.argmin(d, axis=1)]
        idx[a] = nxt
        on_green = flat[nxt] == 5
        strokes[a[on_green]] += FlatPutting.expected
        active[a[on_green]] = False
    return float(strokes.mean())
