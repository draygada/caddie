"""Tests for caddie.mdp (part 04)."""

import json
from pathlib import Path

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
    assert [int(v) for v in Lie] == [0, 1, 2, 3, 4, 5, 6, 7, 8]
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


# part 17 slice 3: lie code 8 ----------------------------------------------------


def test_trees_lie_code_and_roll_multiplier():
    from caddie.mdp import roll_multipliers

    assert Lie.TREES == 8
    m = roll_multipliers(toy_player())
    assert m.shape == (9,)
    assert m[Lie.TREES] == 0.0


def test_tree_cells_are_neither_playable_nor_terminal():
    from caddie.value_iteration import state_mask
    from tests.fixtures.toy_hole import TREE_COLS, TREE_ROW, toy_tree_hole

    hole = toy_tree_hole()
    playable, terminal = state_mask(hole)
    cells = TREE_ROW * hole.cols + np.arange(*TREE_COLS)
    assert not playable[cells].any() and not terminal[cells].any()
    assert int((hole.lie == Lie.TREES).sum()) == 5


def test_locate_reports_trees():
    from caddie.mdp import locate
    from tests.fixtures.toy_hole import toy_tree_hole

    hole = toy_tree_hole()
    _, lie, outside = locate(hole, np.array([27.5, 27.5]), np.array([22.5, 12.5]))
    assert lie.tolist() == [int(Lie.TREES), int(Lie.FAIRWAY)]
    assert not outside.any()


def test_bundle_round_trips_tree_cells(tmp_path):
    from caddie.export import read_bundle, write_bundle
    from caddie.value_iteration import NO_ACTION, Solution
    from tests.fixtures.toy_hole import toy_tree_hole

    hole = toy_tree_hole()
    n = hole.rows * hole.cols
    sol = Solution(
        hole=0,
        mode="drop",
        U=np.where(hole.lie.reshape(-1) == Lie.TREES, np.nan, 3.0).astype(np.float32),
        club=np.full(n, NO_ACTION, dtype=np.uint8),
        dir=np.full(n, NO_ACTION, dtype=np.uint8),
        sweeps=0,
    )
    write_bundle(sol, hole, toy_player(), tmp_path, label="toy")
    _, lie, value, _, _ = read_bundle(tmp_path / "toy" / "drop")
    assert int((lie == 8).sum()) == 5
    assert np.isnan(value[lie == 8]).all()


# part 17 slice 4: exact march ----------------------------------------------------

TREE_RAYS = Path(__file__).resolve().parents[2] / "docs" / "fixtures" / "tree_rays.json"


def test_first_tree_distance_straight_parallel_and_range():
    from caddie.mdp import RAY_STEP_M, first_tree_distance
    from tests.fixtures.toy_hole import toy_tree_hole

    hole = toy_tree_hole()
    d = first_tree_distance(hole, 27.5, 2.5, 0.0)  # tee, straight at the row (y 20 to 25)
    assert abs(d - 17.5) <= RAY_STEP_M and d == 18.0
    assert first_tree_distance(hole, 2.5, 12.5, 90.0) == np.inf  # below the row, along it
    assert first_tree_distance(hole, 27.5, 2.5, 180.0) == np.inf  # away from it, off the grid
    assert first_tree_distance(hole, 27.5, 2.5, 0.0, max_m=10.0) == np.inf
    # 45 degrees right from the tee: reaches y = 20 at x = 45, past the row's right end (x 40)
    assert first_tree_distance(hole, 27.5, 2.5, 45.0) == np.inf
    # 30 degrees right: reaches y = 20 at x = 37.6, inside the row
    assert first_tree_distance(hole, 27.5, 2.5, 30.0) == 21.0


def test_first_tree_distance_skips_the_clump_the_ball_starts_in():
    from caddie.mdp import first_tree_distance
    from tests.fixtures.toy_hole import toy_tree_hole

    hole = toy_tree_hole()
    assert first_tree_distance(hole, 27.5, 22.5, 0.0) == np.inf  # chips out toward the pin
    hole.lie[7, 5] = int(Lie.TREES)  # a second tree further up the line, y 35 to 40
    assert first_tree_distance(hole, 27.5, 22.5, 0.0) == 13.0


def test_tree_rays_fixture_matches_python():
    from caddie.mdp import first_tree_distance
    from tests.fixtures.toy_hole import toy_tree_hole

    doc = json.loads(TREE_RAYS.read_text())
    hole = toy_tree_hole()
    assert doc["rows"] == hole.rows and doc["cols"] == hole.cols and doc["cell_m"] == hole.cell_m
    assert doc["lie"] == hole.lie.reshape(-1).tolist()
    assert len(doc["cases"]) == 10
    hits = 0
    for case in doc["cases"]:
        d = first_tree_distance(hole, case["x"], case["y"], case["bearing_deg"])
        if case["distance_m"] is None:
            assert d == np.inf
        else:
            hits += 1
            assert d == pytest.approx(case["distance_m"], abs=1e-9)
    assert 3 <= hits <= 8  # the fixture mixes hits and misses


# part 17 slice 5: blocking in step_batch -------------------------------------------


def _tree_setup(player=None):
    from tests.fixtures.toy_hole import toy_tree_hole

    hole = toy_tree_hole()
    player = player or toy_player()
    return hole, player, build_offset_tables(player, make_draws(200))


def test_shot_through_the_tree_row_rests_short_of_it(tables):
    hole, player, _ = _tree_setup()
    tee = np.array([5])  # (0, 5): x 27.5, y 2.5, straight below the row
    nxt, rew = step_batch(hole, player, tee, hole.lie.reshape(-1)[tee], 0, DIR0, tables, "drop")
    rows, cols = np.divmod(nxt[0], hole.cols)
    assert np.all(rew == -1.0)  # blocked, never penalised
    assert np.all(rows <= 3)  # nothing got past y = 20
    assert np.mean(rows == 3) > 0.9  # 2.5 m short of the row is y 17.5
    assert not np.any(hole.lie.reshape(-1)[nxt] == Lie.TREES)
    clear = toy_hole(hazards=False)
    nxt0, _ = step_batch(clear, player, tee, clear.lie.reshape(-1)[tee], 0, DIR0, tables, "drop")
    assert np.mean(nxt0[0] // clear.cols >= 4) > 0.95  # the same shot without trees flies on


def test_shots_that_miss_the_trees_are_unchanged(tables):
    hole, player, _ = _tree_setup()
    clear = toy_hole(hazards=False)
    above = np.array([6 * hole.cols + 5, 6 * hole.cols + 2])  # past the row, heading to the pin
    for from_idx, d in ((above, DIR0), (np.array([5]), 0), (np.array([5]), 90)):
        lie = clear.lie.reshape(-1)[from_idx]
        a = step_batch(hole, player, from_idx, lie, 0, d, tables, "drop")
        b = step_batch(clear, player, from_idx, lie, 0, d, tables, "drop")
        assert np.array_equal(a[0], b[0]) and np.array_equal(a[1], b[1])


def test_roll_into_the_trees_stops_before_them():
    runner = club(mu_c=14.0, sigma_theta=0.5, sigma_d=0.01, p=0.0, mu_r=6.0, sigma_r=0.2)
    base = toy_player()
    player = type(base)(
        handicap=15,
        clubs={TOY_CLUB: runner},
        club_order=[TOY_CLUB],
        lie=base.lie,
        putting=base.putting,
    )
    hole, player, tables = _tree_setup(player)
    tee = np.array([5])
    nxt, rew = step_batch(hole, player, tee, hole.lie.reshape(-1)[tee], 0, DIR0, tables, "drop")
    rows = nxt[0] // hole.cols
    assert np.all(rows == 3)  # lands at y 16.5, would roll to 22.5, stops at 18
    assert np.all(rew == -1.0)
    clear = toy_hole(hazards=False)
    nxt0, _ = step_batch(clear, player, tee, clear.lie.reshape(-1)[tee], 0, DIR0, tables, "drop")
    assert np.all(nxt0[0] // clear.cols == 4)


def test_tree_ray_table_matches_the_exact_march():
    from caddie.mdp import RAY_BIN_DEG, first_tree_distance, tree_ray_table
    from tests.fixtures.toy_hole import toy_tree_hole

    hole = toy_tree_hole()
    table = tree_ray_table(hole)
    assert table.shape == (hole.rows * hole.cols, int(360 / RAY_BIN_DEG))
    for cell, bearing in ((5, 0.0), (5, 30.0), (5, 45.0), (12, 17.5), (65, 180.0), (5, -20.0)):
        r, c = divmod(cell, hole.cols)
        exact = first_tree_distance(hole, (c + 0.5) * 5.0, (r + 0.5) * 5.0, bearing)
        assert table[cell, int(round((bearing % 360) / RAY_BIN_DEG))] == exact
    clear = toy_hole(hazards=False)
    assert np.isinf(tree_ray_table(clear)).all()


def test_solve_on_the_tree_hole_goes_around_the_row():
    from caddie.value_iteration import NO_ACTION, solve
    from tests.fixtures.toy_hole import toy_tree_hole

    hole = toy_tree_hole()
    sol = solve(hole, toy_player(), "drop", K=100)
    trees = hole.lie.reshape(-1) == Lie.TREES
    assert np.isnan(sol.U[trees]).all()
    assert np.all(sol.club[trees] == NO_ACTION) and np.all(sol.dir[trees] == NO_ACTION)
    tee = 5
    assert np.isfinite(sol.U[tee])
    assert sol.dir[tee] != DIR0  # straight at the pin is blocked, so the policy aims around
    clear = solve(toy_hole(hazards=False), toy_player(), "drop", K=100)
    assert sol.U[tee] > clear.U[tee]  # the trees cost strokes


# part 17 slice 7: tee-only driver ---------------------------------------------------


def _two_club_player():
    base = toy_player()
    return type(base)(
        handicap=15,
        clubs={"driver": club(mu_c=30.0), TOY_CLUB: base.clubs[TOY_CLUB]},
        club_order=["driver", TOY_CLUB],
        lie=base.lie,
        putting=base.putting,
    )


def test_candidate_actions_drop_the_driver_off_the_tee_lie():
    from caddie.mdp import TEE_ONLY_CLUBS

    assert TEE_ONLY_CLUBS == ("driver",)
    h = toy_hole()
    h.lie[0, 5] = int(Lie.TEE)
    player = _two_club_player()
    far = (27.5, 2.5)  # the tee cell, 45 m out: both clubs pass the 1.3 x distance rule
    assert set(candidate_actions(h, player, far)[:, 0]) == {0, 1}  # lie read from the cell
    assert set(candidate_actions(h, player, far, lie=Lie.TEE)[:, 0]) == {0, 1}
    for lie in (Lie.FAIRWAY, Lie.ROUGH, Lie.BUNKER):
        assert set(candidate_actions(h, player, far, lie=lie)[:, 0]) == {1}
    assert set(candidate_actions(h, player, (22.5, 2.5))[:, 0]) == {1}  # a fairway cell


def test_candidate_actions_single_club_bags_are_unaffected():
    h = toy_hole()
    a = candidate_actions(h, toy_player(), (27.5, 2.5))
    b = candidate_actions(h, toy_player(), (27.5, 2.5), lie=Lie.ROUGH)
    assert np.array_equal(a, b)
    base = toy_player()
    only = type(base)(15, {"driver": base.clubs[TOY_CLUB]}, ["driver"], base.lie, base.putting)
    assert candidate_actions(h, only, (27.5, 2.5), lie=Lie.FAIRWAY).shape == (91, 2)  # never empty


# part 17 slice 5 (amended): the ball clears trees above the canopy -----------------


def test_low_flight_m_against_hand_values():
    from caddie.mdp import APEX_MAX_M, APEX_PER_CARRY, TREE_HEIGHT_M, low_flight_m

    assert (TREE_HEIGHT_M, APEX_MAX_M, APEX_PER_CARRY) == (15.0, 24.0, 0.30)
    low = low_flight_m(np.array([100.0, 215.0, 40.0, 50.0, 60.0, 0.0]))
    assert low[0] == pytest.approx(100.0 * (1 - np.sqrt(1 - 15 / 24)) / 2)  # 19.38
    assert low[0] == pytest.approx(19.38, abs=0.01)
    assert low[1] == pytest.approx(215.0 * 0.19381, abs=0.01)  # apex capped at 24 m
    assert low[2] == 40.0  # apex 12 m: under the trees all the way
    assert low[3] == 50.0  # apex exactly 15 m still does not clear
    assert 0 < low[4] < 30.0  # apex 18 m: clears in the middle
    assert low[5] == 0.0


def _long_player(mu_c=100.0):
    base = toy_player()
    long_club = club(mu_c=mu_c, sigma_theta=0.5, sigma_d=0.01, p=0.0, mu_r=0.0, sigma_r=0.0)
    player = type(base)(15, {TOY_CLUB: long_club}, [TOY_CLUB], base.lie, base.putting)
    return player, build_offset_tables(player, make_draws(200))


@pytest.mark.parametrize(
    ("tree_row", "expected"),
    [
        (12, "clears"),  # y 60 to 65: mid-flight, above the canopy
        (3, "climb"),  # y 15 to 20: inside the first 19.4 m
        (20, "descent"),  # y 100 to 105: the ball comes down into it
    ],
)
def test_a_full_shot_clears_trees_in_the_middle_of_its_carry(tree_row, expected):
    from tests.fixtures.toy_hole import tall_tree_hole

    hole = tall_tree_hole(tree_row)
    player, tables = _long_player()
    tee = np.array([5])
    nxt, rew = step_batch(hole, player, tee, hole.lie.reshape(-1)[tee], 0, DIR0, tables, "drop")
    rows = nxt[0] // hole.cols
    assert np.all(rew == -1.0)
    assert not np.any(hole.lie.reshape(-1)[nxt] == Lie.TREES)
    if expected == "clears":
        assert np.all(rows >= 19)  # lands near y 102.5, past the row
    elif expected == "climb":
        assert np.all(rows == 2)  # 2.5 m short of y 15
    else:
        assert np.all(rows == 19)  # stopped just short of y 100


def test_flight_fixture_matches_python():
    from caddie.mdp import APEX_MAX_M, APEX_PER_CARRY, DESCENT_STEP_M, TREE_HEIGHT_M, low_flight_m

    flight = json.loads(TREE_RAYS.read_text())["flight"]
    assert flight["tree_height_m"] == TREE_HEIGHT_M and flight["apex_max_m"] == APEX_MAX_M
    assert flight["apex_per_carry"] == APEX_PER_CARRY and flight["descent_step_m"] == DESCENT_STEP_M
    assert len(flight["cases"]) == 9
    for case in flight["cases"]:
        assert float(low_flight_m(np.array([case["carry_m"]]))[0]) == pytest.approx(
            case["low_m"], abs=1e-12
        )


# part 17: the exact rule for continuous points (same literals as app/src/lib/shot.test.ts) ----


def _exact(hole, x, y, bearing, carry, roll):
    from caddie.mdp import stop_at_trees_exact

    rad = np.radians(bearing)
    lx, ly = x + carry * np.sin(rad), y + carry * np.cos(rad)
    fx, fy = lx + roll * np.sin(rad), ly + roll * np.cos(rad)
    c = np.array([carry])
    out = stop_at_trees_exact(
        hole,
        x,
        y,
        np.array([bearing]),
        c,
        np.array([lx]),
        np.array([ly]),
        bearing,
        np.array([roll]),
        np.array([fx]),
        np.array([fy]),
    )
    return float(out[0][0]), float(out[1][0])


def test_exact_rule_matches_the_app_on_the_toy_tree_hole():
    from tests.fixtures.toy_hole import toy_tree_hole

    hole = toy_tree_hole()
    assert _exact(hole, 27.5, 2.5, 0.0, 25.0, 2.0) == pytest.approx((27.5, 2.5 + 18 - 2.5))  # climb
    assert _exact(hole, 7.5, 2.5, 0.0, 25.0, 2.0) == pytest.approx((7.5, 29.5))  # misses the row
    assert _exact(hole, 27.5, 2.5, 0.0, 14.0, 6.0) == pytest.approx((27.5, 16.5 + 4 - 2.5))  # roll
    assert _exact(hole, 27.5, 22.5, 0.0, 22.5, 0.0) == pytest.approx(
        (27.5, 45.0)
    )  # chips out of the clump
    clear = toy_hole(hazards=False)
    assert _exact(clear, 27.5, 2.5, 0.0, 25.0, 2.0) == pytest.approx((27.5, 29.5))


@pytest.mark.parametrize(("tree_row", "y"), [(12, 102.5), (3, 2.5 + 13 - 2.5)])
def test_exact_rule_on_the_tall_hole(tree_row, y):
    from tests.fixtures.toy_hole import tall_tree_hole

    assert _exact(tall_tree_hole(tree_row), 27.5, 2.5, 0.0, 100.0, 0.0) == pytest.approx((27.5, y))


def test_exact_rule_stops_a_ball_coming_down_into_trees():
    from tests.fixtures.toy_hole import tall_tree_hole

    _, y = _exact(tall_tree_hole(20), 27.5, 2.5, 0.0, 100.0, 0.0)  # row at y 100 to 105
    assert 95.0 <= y < 100.0


def test_shots_from_point_respects_trees():
    from caddie.online import shots_from_point
    from tests.fixtures.toy_hole import toy_tree_hole

    hole, player = toy_tree_hole(), toy_player()
    nx, ny, cost = shots_from_point(
        hole, player, 27.5, 2.5, Lie.FAIRWAY, player.clubs[TOY_CLUB], 0.0, make_draws(200), "drop"
    )
    assert np.all(ny < 20.0) and np.all(cost == 1.0)
