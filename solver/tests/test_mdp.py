"""Tests for caddie.mdp (part 04)."""

import numpy as np
import pytest

from caddie.dispersion import ClubParams
from caddie.mdp import (
    DIRECTIONS_DEG,
    FROM_LIES,
    Draws,
    Lie,
    OffsetTables,
    build_offset_tables,
    landing_offsets,
    make_draws,
    step_batch,
)
from tests.fixtures.toy_hole import TOY_CLUB, toy_hole, toy_player

# slice 1: Lie enum, directions, draws


def test_lie_codes_match_contract():
    assert [int(v) for v in Lie] == [0, 1, 2, 3, 4, 5, 6, 7]
    assert Lie.OUT == 0 and Lie.TEE == 1 and Lie.GREEN == 5 and Lie.OB == 7


def test_directions():
    assert DIRECTIONS_DEG.shape == (91,)
    assert DIRECTIONS_DEG[0] == -90 and DIRECTIONS_DEG[-1] == 90 and DIRECTIONS_DEG[45] == 0
    assert np.all(np.diff(DIRECTIONS_DEG) == 2)


def test_make_draws_shapes_and_moments():
    d = make_draws(200)
    assert isinstance(d, Draws)
    for arr in (d.theta, d.z, d.u, d.roll):
        assert arr.shape == (200,)
    for arr in (d.theta, d.roll, d.z):
        assert abs(arr.mean()) < 0.1
        assert abs(arr.std() - 1.0) < 0.1
    assert np.all((d.u >= 0) & (d.u < 1))


def test_mixture_x_has_negative_mean():
    d = make_draws(200)
    x = d.x(0.25)
    assert x.shape == (200,)
    assert x.mean() < 0
    assert d.x(0.0).mean() == pytest.approx(d.z.mean())


def test_make_draws_deterministic_for_seed():
    a, b = make_draws(50, seed=3), make_draws(50, seed=3)
    assert np.array_equal(a.theta, b.theta) and np.array_equal(a.u, b.u)
    assert not np.array_equal(a.theta, make_draws(50, seed=4).theta)


# slice 2: landing offsets

UNIT_LIE = {"carry": 1.0, "sigma": 1.0, "roll": 1.0}


def club(mu_c=25.0, sigma_theta=4.0, sigma_d=0.05, p=0.05, mu_r=2.0, sigma_r=1.0) -> ClubParams:
    return ClubParams(mu_c, sigma_theta, sigma_d, p, mu_r, sigma_r, sampled=True, stats=None)


@pytest.fixture(scope="module")
def draws() -> Draws:
    return make_draws(200)


def test_landing_offsets_degenerate_dir0(draws):
    c = club(sigma_theta=0.0, sigma_d=0.0, sigma_r=0.0)
    dx, dy, roll = landing_offsets(c, UNIT_LIE, draws, 0.0)
    assert dx.shape == dy.shape == roll.shape == (200,)
    assert np.allclose(dx, 0.0) and np.allclose(dy, c.mu_c)
    assert np.allclose(roll, c.mu_r)


def test_landing_offsets_degenerate_dir90(draws):
    c = club(sigma_theta=0.0, sigma_d=0.0)
    dx, dy, _ = landing_offsets(c, UNIT_LIE, draws, 90.0)
    assert np.allclose(dx, c.mu_c) and np.allclose(dy, 0.0, atol=1e-9)


def test_landing_offsets_spread_and_lie_multipliers(draws):
    c = club()
    dx, dy, roll = landing_offsets(c, UNIT_LIE, draws, 0.0)
    carry = np.hypot(dx, dy)
    assert abs(carry.mean() - c.mu_c * (1 - c.p * 2 * c.sigma_d)) < 0.5
    assert dx.std() > 0.5 and dy.std() > 0.5
    rough = {"carry": 0.9, "sigma": 1.3, "roll": 0.5}
    dxr, dyr, rollr = landing_offsets(c, rough, draws, 0.0)
    assert np.hypot(dxr, dyr).mean() < carry.mean()
    assert dxr.std() > dx.std()
    assert np.allclose(rollr, 0.5 * roll)


# slice 3: offset tables


@pytest.fixture(scope="module")
def tables(draws) -> OffsetTables:
    return build_offset_tables(toy_player(), draws)


def test_from_lies_order():
    assert FROM_LIES == (Lie.TEE, Lie.FAIRWAY, Lie.ROUGH, Lie.BUNKER, Lie.GREEN)


def test_offset_tables_shape(tables):
    assert tables.dx.shape == tables.dy.shape == tables.roll.shape == (1, 5, 91, 200)
    assert tables.dx.dtype == np.float64


def test_offset_tables_rough_wider_than_fairway(tables):
    fw = FROM_LIES.index(Lie.FAIRWAY)
    rg = FROM_LIES.index(Lie.ROUGH)
    d0 = 45  # direction 0
    assert tables.dx[0, rg, d0].std() > tables.dx[0, fw, d0].std()
    assert tables.dy[0, rg, d0].mean() < tables.dy[0, fw, d0].mean()
    assert np.allclose(tables.roll[0, FROM_LIES.index(Lie.BUNKER), d0], 0.0)
    assert np.array_equal(tables.dx[0, fw, d0], tables.dx[0, FROM_LIES.index(Lie.TEE), d0])


def test_offset_tables_direction_axis(tables):
    fw = FROM_LIES.index(Lie.FAIRWAY)
    assert tables.dx[0, fw, 0].mean() < -20  # dir -90 is to the left
    assert tables.dx[0, fw, 90].mean() > 20
    assert tables.dy[0, fw, 45].mean() > 20


# slice 4: step_batch, no hazards

DIR0 = 45  # index of direction 0 in DIRECTIONS_DEG


def test_toy_hole_layout():
    h = toy_hole(hazards=False)
    assert h.lie.shape == (10, 10) and h.pin_xy == (27.5, 47.5)
    assert (h.lie == Lie.GREEN).sum() == 6
    assert set(np.unique(h.lie)) == {int(Lie.FAIRWAY), int(Lie.GREEN)}


def test_step_batch_no_hazards(tables):
    h = toy_hole(hazards=False)
    player = toy_player()
    from_idx = np.array([5, 4])  # tee row, cols 5 and 4
    from_lie = h.lie.reshape(-1)[from_idx]
    nxt, rew = step_batch(h, player, from_idx, from_lie, 0, DIR0, tables, "replay")
    assert nxt.shape == rew.shape == (2, 200)
    assert nxt.dtype.kind == "i"
    assert np.all(rew == -1.0)
    rows = nxt // h.cols
    frac = np.mean((rows >= 4) & (rows <= 6))
    assert frac >= 0.95, frac
    cols = nxt % h.cols
    assert abs(cols[0].mean() - 5) < 0.5 and abs(cols[1].mean() - 4) < 0.5


def test_step_batch_same_result_every_mode_without_hazards(tables):
    h = toy_hole(hazards=False)
    player = toy_player()
    from_idx = np.arange(1, 9)  # inner columns: edge columns can leave the grid
    from_lie = h.lie.reshape(-1)[from_idx]
    outs = [
        step_batch(h, player, from_idx, from_lie, 0, DIR0, tables, m)
        for m in ("mulligan", "drop", "replay")
    ]
    for a in outs[1:]:
        assert np.array_equal(a[0], outs[0][0]) and np.array_equal(a[1], outs[0][1])
    assert player.club_order[0] == TOY_CLUB


# slice 5: terrain rules


def _hazard_runs(from_rc, dir_idx, tables):
    h = toy_hole(hazards=True)
    player = toy_player()
    from_idx = np.array([from_rc[0] * h.cols + from_rc[1]])
    from_lie = h.lie.reshape(-1)[from_idx]
    out = {
        m: step_batch(h, player, from_idx, from_lie, 0, dir_idx, tables, m)
        for m in ("mulligan", "drop", "replay")
    }
    hazard = out["replay"][1][0] == -2.0
    return h, from_idx[0], out, hazard


def test_water_rules(tables):
    # from (2, 1) straight up +y: carry 25 m lands around y = 39.5, row 7, cols 0 to 3 is water
    h, origin, out, hazard = _hazard_runs((2, 1), DIR0, tables)
    assert 0.5 < hazard.mean() < 1.0, hazard.mean()
    flat = h.lie.reshape(-1)
    nxt, rew = out["mulligan"]
    assert np.all(rew == -1.0)
    assert np.all(nxt[0][hazard] == origin)
    assert np.all(flat[nxt[0][~hazard]] != Lie.WATER)
    nxt, rew = out["replay"]
    assert np.all(rew[0][hazard] == -2.0) and np.all(rew[0][~hazard] == -1.0)
    assert np.all(nxt[0][hazard] == origin)
    nxt, rew = out["drop"]
    assert np.all(rew[0][hazard] == -2.0)
    drop_rows = nxt[0][hazard] // h.cols
    assert np.all(drop_rows <= 7)
    assert np.all(np.isin(flat[nxt[0][hazard]], [int(Lie.FAIRWAY), int(Lie.ROUGH)]))
    # the same draws are hazards in every mode
    assert np.array_equal(out["mulligan"][0][0] == origin, hazard)


def test_ob_rules(tables):
    # from (2, 8) aiming 10 degrees right: most draws end in col 9 (OB) or off the grid
    h, origin, out, hazard = _hazard_runs((2, 8), DIR0 + 5, tables)
    assert hazard.mean() > 0.5, hazard.mean()
    flat = h.lie.reshape(-1)
    nxt, rew = out["mulligan"]
    assert np.all(rew == -1.0) and np.all(nxt[0][hazard] == origin)
    nxt, rew = out["replay"]
    assert np.all(rew[0][hazard] == -2.0) and np.all(nxt[0][hazard] == origin)
    nxt, rew = out["drop"]
    assert np.all(rew[0][hazard] == -2.0)
    dropped = nxt[0][hazard]
    assert np.all((dropped >= 0) & (dropped < h.rows * h.cols))
    assert np.all(
        np.isin(
            flat[dropped],
            [int(v) for v in (Lie.FAIRWAY, Lie.ROUGH, Lie.TEE, Lie.BUNKER, Lie.GREEN)],
        )
    )
    assert np.all(dropped % h.cols == 8)  # nearest playable column to the OB strip


def test_bunker_landing_stops_roll(tables):
    # from (0, 4) straight up: carry 25 m lands in row 5 (bunker at cols 4, 5); roll x0 there
    h = toy_hole(hazards=True)
    player = toy_player()
    from_idx = np.array([4])
    nxt, rew = step_batch(
        h, player, from_idx, h.lie.reshape(-1)[from_idx], 0, DIR0, tables, "replay"
    )
    flat = h.lie.reshape(-1)
    assert np.all(rew == -1.0)
    assert np.mean(flat[nxt[0]] == Lie.BUNKER) > 0.3


def test_step_batch_rejects_bad_mode(tables):
    h = toy_hole()
    with pytest.raises(ValueError, match="penalty_mode"):
        step_batch(h, toy_player(), np.array([5]), np.array([2]), 0, DIR0, tables, "none")  # type: ignore[arg-type]
