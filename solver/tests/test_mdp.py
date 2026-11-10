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
    candidate_actions,
    landing_offsets,
    make_draws,
    step_batch,
    terminal_values,
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
    assert abs(cols[0].mean() - 5) < 0.5
    assert 4.0 < cols[1].mean() < 5.0  # direction 0 points at the pin, so column 4 drifts right


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
    # from (2, 1) the pin bearing is about +30 deg; aiming -30 relative flies straight up +y
    # and carry 25 m lands around y = 39.5, row 7, where cols 0 to 3 are water
    h, origin, out, hazard = _hazard_runs((2, 1), DIR0 - 15, tables)
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
    # from (2, 8) the pin bearing is about -23 deg; +34 relative aims about 11 deg right of +y,
    # so most draws end in col 9 (OB) or off the grid
    h, origin, out, hazard = _hazard_runs((2, 8), DIR0 + 17, tables)
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


# slice 6: terminal values


def test_terminal_values_on_green_only():
    h = toy_hole()
    u = terminal_values(h, toy_player().putting)
    flat = h.lie.reshape(-1)
    assert u.shape == (100,)
    green = flat == Lie.GREEN
    assert np.all(np.isnan(u[~green]))
    assert np.all(u[green] == -1.5)  # flat putting table


def test_terminal_values_increase_in_magnitude_with_distance():
    from pathlib import Path

    from caddie.putting import build_putting_table

    h = toy_hole()
    table = build_putting_table(
        Path(__file__).resolve().parents[1] / "data" / "raw" / "putting.csv"
    )
    u = terminal_values(h, table)
    flat = h.lie.reshape(-1)
    green = np.flatnonzero(flat == Lie.GREEN)
    r, c = np.divmod(green, h.cols)
    dist = np.hypot((c + 0.5) * h.cell_m - h.pin_xy[0], (r + 0.5) * h.cell_m - h.pin_xy[1])
    order = np.argsort(dist)
    assert np.all(u[green] < 0)
    assert np.all(np.diff(u[green][order]) <= 1e-12)
    pin_idx = 9 * h.cols + 5
    assert u[pin_idx] == pytest.approx(-float(table(0.0)))


def test_candidate_actions_prunes_long_clubs():
    h = toy_hole()
    player = toy_player()
    # toy club mu_c 25: allowed when 25 <= 1.3 * distance, i.e. distance >= 19.23 m
    far = candidate_actions(h, player, (27.5, 2.5))
    near = candidate_actions(h, player, (27.5, 40.0))
    assert (
        far.shape == (91, 2) and np.all(far[:, 0] == 0) and np.array_equal(far[:, 1], np.arange(91))
    )
    assert near.shape == (91, 2)  # never empty: the shortest club stays


# slice 7: brute-force fixture


def test_brute_force_value_at_tee_replay():
    from tests.fixtures.toy_hole import brute_force_value_at_tee

    v1 = brute_force_value_at_tee("replay", n=20000, rng=np.random.default_rng(42))
    v2 = brute_force_value_at_tee("replay", n=20000, rng=np.random.default_rng(42))
    assert v1 == v2
    assert np.isfinite(v1) and v1 > 2.0


@pytest.mark.xfail(
    strict=True,
    reason="part file asks for 3 < E[strokes] < 6 under replay, but with the toy club "
    "(25 m carry, 2 m roll) every full shot from row 5 flies past the top of the grid, "
    "which is OB, and replay rehits from row 5; the aim-at-pin policy scores about 8.3. "
    "Needs a decision on the toy hole or the band",
)
def test_brute_force_replay_in_part_file_band():
    from tests.fixtures.toy_hole import brute_force_value_at_tee

    v = brute_force_value_at_tee("replay", n=20000, rng=np.random.default_rng(42))
    assert 3.0 < v < 6.0, v


def test_brute_force_other_modes_finite():
    from tests.fixtures.toy_hole import brute_force_value_at_tee

    vals = {
        m: brute_force_value_at_tee(m, n=5000, rng=np.random.default_rng(1))
        for m in ("mulligan", "drop", "replay")
    }
    assert all(np.isfinite(v) and v > 2.0 for v in vals.values()), vals
    assert vals["mulligan"] <= vals["replay"]


# slice 4 fix: precomputed OB drop lookup


def test_ob_drop_lookup_matches_nearest_playable():
    from caddie.mdp import ob_drop_lookup

    h = toy_hole()
    look = ob_drop_lookup(h)
    flat = h.lie.reshape(-1)
    assert look.shape == (100,) and look.dtype == np.int64
    playable = np.isin(flat, [1, 2, 3, 4, 5])
    assert np.array_equal(look[playable], np.flatnonzero(playable))
    # OB column 9 maps to column 8 on the same row; water at (7, 0..3) maps to a playable neighbour
    assert np.all(look[np.arange(10) * 10 + 9] == np.arange(10) * 10 + 8)
    for i in np.flatnonzero(flat == Lie.WATER):
        assert playable[look[i]] and abs(look[i] // 10 - i // 10) + abs(look[i] % 10 - i % 10) <= 2
    assert ob_drop_lookup(h) is look  # cached per hole


# slice 4 fix: directions relative to the cell's bearing to the pin


def test_pin_bearing():
    from caddie.mdp import pin_bearing_deg

    h = toy_hole()
    x = np.array([27.5, 7.5, 47.5, 27.5])
    y = np.array([2.5, 47.5, 47.5, 60.0])
    b = pin_bearing_deg(h, x, y)
    assert b[0] == pytest.approx(0.0)
    assert b[1] == pytest.approx(90.0) and b[2] == pytest.approx(-90.0)
    assert abs(b[3]) == pytest.approx(180.0)


def test_direction_zero_points_at_the_pin_from_anywhere(tables):
    h = toy_hole(hazards=False)
    player = toy_player()
    # cells left and right of the pin column on row 4; also a cell beyond the green, row 9 col 1
    from_idx = np.array([4 * 10 + 1, 4 * 10 + 8, 9 * 10 + 1])
    nxt, _ = step_batch(h, player, from_idx, h.lie.reshape(-1)[from_idx], 0, DIR0, tables, "replay")
    r, c = np.divmod(nxt, h.cols)
    x, y = (c + 0.5) * h.cell_m, (r + 0.5) * h.cell_m
    for k, (fx, fy) in enumerate(((7.5, 22.5), (42.5, 22.5), (7.5, 47.5))):
        moved = np.hypot(x[k] - fx, y[k] - fy)
        before = np.hypot(fx - h.pin_xy[0], fy - h.pin_xy[1])
        after = np.hypot(x[k] - h.pin_xy[0], y[k] - h.pin_xy[1])
        assert moved.mean() > 15
        assert (after < before).mean() > 0.9
