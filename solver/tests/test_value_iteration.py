"""Tests for caddie.value_iteration (part 05)."""

import json
import logging
import time
from pathlib import Path

import numpy as np
import pytest

from caddie.dispersion import ClubParams, Player
from caddie.geometry import build_hole
from caddie.mdp import DIRECTIONS_DEG, Lie, build_offset_tables, make_draws, pin_bearing_deg
from caddie.putting import build_putting_table
from caddie.value_iteration import (
    Solution,
    all_actions,
    bellman_backup,
    initial_values,
    solve,
    state_mask,
    write_value_png,
)
from tests.fixtures.toy_hole import brute_force_value_at_tee, toy_hole, toy_player

# slice 1: single backup on the toy hole


@pytest.fixture(scope="module")
def toy():
    hole, player = toy_hole(), toy_player()
    tables = build_offset_tables(player, make_draws(200))
    return hole, player, tables


def test_state_mask_and_initial_values(toy):
    hole, player, _ = toy
    flat = hole.lie.reshape(-1)
    playable, terminal = state_mask(hole)
    assert playable.sum() == np.isin(flat, [1, 2, 3, 4]).sum()
    assert terminal.sum() == (flat == Lie.GREEN).sum()
    assert not np.any(playable & terminal)
    u0 = initial_values(hole, player)
    assert u0.shape == (100,)
    assert np.all(u0[playable] == -(hole.par + 2))
    assert np.all(u0[terminal] == -1.5)
    assert np.all(np.isnan(u0[~playable & ~terminal]))


def test_all_actions_shape(toy):
    _, player, _ = toy
    acts = all_actions(player)
    assert acts.shape == (91, 2) and acts.dtype.kind == "i"


def test_single_backup_raises_values(toy):
    hole, player, tables = toy
    u0 = initial_values(hole, player)
    playable, terminal = state_mask(hole)
    u1, club, d = bellman_backup(u0, hole, player, tables, "replay", all_actions(player))
    assert u1.shape == u0.shape and club.shape == u0.shape and d.shape == u0.shape
    assert np.all(u1[playable] != u0[playable])
    assert np.all(u1[playable] <= -1.0)
    # cells one shot from the green rise; the rest take -1 + U_0 and fall
    rows = np.flatnonzero(playable) // hole.cols
    rose = u1[playable] > u0[playable]
    assert rose.any() and np.all(rows[rose] >= 2)
    assert np.all(~rose[rows <= 1])
    assert np.array_equal(u1[terminal], u0[terminal])
    assert np.all(np.isnan(u1[~playable & ~terminal]))
    assert np.all(club[playable] == 0) and np.all((d[playable] >= 0) & (d[playable] < 91))
    assert np.all(club[~playable] == 255) and np.all(d[~playable] == 255)
    assert u0 is not u1 and np.all(u0[playable] == -(hole.par + 2))  # input not mutated


@pytest.mark.xfail(
    strict=True,
    reason="part file says one sweep from U_0 = -par - 2 raises every non-terminal cell; "
    "with gamma = 1 a cell that cannot reach the green in one shot gets -1 + U_0, which "
    "is lower. Needs a decision on the initial value",
)
def test_single_backup_raises_every_cell_per_part_file(toy):
    hole, player, tables = toy
    u0 = initial_values(hole, player)
    playable, _ = state_mask(hole)
    u1, _, _ = bellman_backup(u0, hole, player, tables, "replay", all_actions(player))
    assert np.all(u1[playable] > u0[playable])


# slice 2: convergence on the toy hole


@pytest.fixture(scope="module")
def replay_solution() -> Solution:
    return solve(toy_hole(), toy_player(), "replay", K=200, tol=0.01, max_sweeps=200, seed=0)


def test_solve_converges(replay_solution):
    s = replay_solution
    assert s.mode == "replay" and s.hole == 0
    assert s.sweeps < 200
    assert len(s.residual_history) == s.sweeps
    assert s.residual_history[-1] < 0.01
    assert np.all(np.diff(s.residual_history[3:]) <= 1e-9)
    assert s.sweeps < 60


def test_solve_drop_converges_fast():
    s = solve(toy_hole(), toy_player(), "drop", K=200, tol=0.01, max_sweeps=50, seed=0)
    assert s.sweeps < 10 and s.residual_history[-1] < 0.01


def test_solution_arrays(replay_solution):
    s = replay_solution
    hole = toy_hole()
    playable, terminal = state_mask(hole)
    assert s.U.dtype == np.float32 and s.club.dtype == np.uint8 and s.dir.dtype == np.uint8
    assert s.U.shape == (100,)
    assert np.all(s.U[playable] > 1.0) and np.all(s.U[terminal] == 1.5)
    assert np.all(np.isnan(s.U[~playable & ~terminal]))
    assert np.all(s.club[~playable] == 255) and np.all(s.dir[~playable] == 255)
    assert np.all(s.club[playable] == 0) and np.all(s.dir[playable] < 91)


def test_tee_value_beats_brute_force(replay_solution):
    hole = toy_hole()
    tee_idx = int(hole.tee_xy[1] // hole.cell_m) * hole.cols + int(hole.tee_xy[0] // hole.cell_m)
    bf = brute_force_value_at_tee("replay", n=20000, rng=np.random.default_rng(42))
    assert replay_solution.U[tee_idx] <= bf + 0.05


# slice 3: policy sanity on the toy hole


@pytest.fixture(scope="module")
def solutions(replay_solution) -> dict[str, Solution]:
    out = {"replay": replay_solution}
    for m in ("mulligan", "drop"):
        out[m] = solve(toy_hole(), toy_player(), m, K=200, tol=0.01, max_sweeps=200, seed=0)
    return out


def _dir_deg(s: Solution, r: int, c: int) -> float:
    i = r * 10 + c
    assert s.dir[i] != 255
    return float(DIRECTIONS_DEG[s.dir[i]])


@pytest.mark.parametrize("mode", ["mulligan", "drop", "replay"])
def test_tee_shots_aim_around_the_bunkers(solutions, mode):
    # the tee cells in columns 4 and 5 sit directly behind the bunker at (5, 4) and (5, 5)
    s = solutions[mode]
    for c in (4, 5):
        assert _dir_deg(s, 0, c) != 0.0


@pytest.mark.parametrize("mode", ["mulligan", "drop", "replay"])
def test_column_8_aims_left_of_the_ob(solutions, mode):
    # directions are relative to the pin bearing, so "aims left" means the absolute aim
    # (bearing + direction) points left of +y, away from the OB column
    s = solutions[mode]
    hole = toy_hole()
    for r in range(hole.rows):
        if hole.lie[r, 8] in (1, 2, 3, 4):
            x, y = (8 + 0.5) * hole.cell_m, (r + 0.5) * hole.cell_m
            bearing = float(pin_bearing_deg(hole, np.array([x]), np.array([y]))[0])
            assert bearing + _dir_deg(s, r, 8) < 0.0, (r, 8)


# slice 4: mode ordering

TEE_IDX = 5  # cell (0, 5)


def test_mode_ordering_against_replay(solutions):
    u = {m: float(s.U[TEE_IDX]) for m, s in solutions.items()}
    assert u["mulligan"] <= u["replay"] + 1e-6
    assert u["drop"] <= u["replay"] + 1e-6


@pytest.mark.xfail(
    strict=True,
    reason="part file asks for mulligan <= drop at the tee; on the toy hole drop is about "
    "0.03 strokes better because an OB over the green drops onto the green (nearest "
    "playable cell) while a mulligan rehits from the trap cells beside it. Needs a "
    "decision on the toy hole or the OB drop rule",
)
def test_mulligan_no_worse_than_drop_per_part_file(solutions):
    assert solutions["mulligan"].U[TEE_IDX] <= solutions["drop"].U[TEE_IDX] + 1e-6


# slice 5: hole 10 end to end

SOLVER_DIR = Path(__file__).resolve().parents[1]
SAMPLE_PLAYER = SOLVER_DIR / "out" / "player.sample.json"


def player_from_json(doc: dict) -> Player:
    """Point estimates only; part 08 owns the full round trip."""
    clubs = {
        name: ClubParams(
            mu_c=v["mu_c"],
            sigma_theta_deg=v["sigma_theta_deg"],
            sigma_d=v["sigma_d"],
            p=v["p"],
            mu_r=v["mu_r"],
            sigma_r=v["sigma_r"],
            sampled=v["sampled"],
            stats=None,
        )
        for name, v in doc["clubs"].items()
    }
    putting = build_putting_table(SOLVER_DIR / "data" / "raw" / "putting.csv")
    return Player(doc["handicap"], clubs, doc["club_order"], doc["lie"], putting)


@pytest.mark.skipif(not SAMPLE_PLAYER.exists(), reason="run tests/test_dispersion.py first")
def test_hole_10_drop_end_to_end(caplog):
    caplog.set_level(logging.INFO, logger="caddie.value_iteration")
    player = player_from_json(json.loads(SAMPLE_PLAYER.read_text()))
    hole = build_hole(
        10,
        SOLVER_DIR / "data" / "raw" / "osm_stanford.geojson",
        SOLVER_DIR / "data" / "raw" / "traced_10.geojson",
        holes_dir=SOLVER_DIR / "data" / "holes",
        out_dir=SOLVER_DIR / "out",
    )
    t0 = time.perf_counter()
    s = solve(hole, player, "drop", K=200, tol=0.01, max_sweeps=100, seed=0, log_every=1)
    elapsed = time.perf_counter() - t0
    assert s.residual_history[-1] < 0.01 and s.sweeps < 100
    vi_logs = [
        r for r in caplog.records if r.name == "caddie.value_iteration" and "sweep" in r.message
    ]
    assert len(vi_logs) == s.sweeps
    playable, terminal = state_mask(hole)
    assert np.all(np.isfinite(s.U[playable])) and np.all(s.U[playable] > 1.0)
    tee = int(hole.tee_xy[1] // hole.cell_m) * hole.cols + int(hole.tee_xy[0] // hole.cell_m)
    assert playable[tee] and s.U[tee] < hole.par + 4
    out = SOLVER_DIR / "out" / "10_drop_value.png"
    write_value_png(s, hole, out, arrow_every=3)
    assert out.exists() and out.stat().st_size > 10_000
    logging.getLogger(__name__).info(
        "hole 10 drop: tee %.2f strokes, %d sweeps, %.0f s", s.U[tee], s.sweeps, elapsed
    )


# part 17 slice 7: tee-only driver ---------------------------------------------------


def test_driver_is_a_candidate_only_on_tee_cells():
    from caddie.value_iteration import club_cells, state_mask

    hole = toy_hole()
    hole.lie[0, 4:7] = int(Lie.TEE)
    base = toy_player()
    longer = ClubParams(30.0, 4.0, 0.05, 0.05, 2.0, 1.0, sampled=True, stats=None)
    player = Player(
        15,
        {"driver": longer, "test7i": base.clubs["test7i"]},
        ["driver", "test7i"],
        base.lie,
        base.putting,
    )
    playable, _ = state_mask(hole)
    cells = np.flatnonzero(playable)
    driver_cells = club_cells(hole, player, cells, 0)
    assert set(driver_cells.tolist()) == {4, 5, 6}
    assert np.array_equal(
        club_cells(hole, player, cells, 1), cells
    )  # the shortest club stays everywhere

    sol = solve(hole, player, "drop", K=100)
    off_tee = np.setdiff1d(cells, driver_cells)
    assert np.all(sol.club[off_tee] == 1)
    assert np.all(np.isin(sol.club[driver_cells], [0, 1]))


# part 18 slice 1: restricted backup --------------------------------------------------


def test_aim_dir_index_is_none_for_free_and_zero_degrees_for_pin(toy):
    from caddie.value_iteration import aim_dir_index

    hole, _, _ = toy
    playable, _ = state_mask(hole)
    cells = np.flatnonzero(playable)
    assert aim_dir_index(hole, cells, "free") is None
    pin = aim_dir_index(hole, cells, "pin")
    assert pin.shape == cells.shape
    assert np.all(DIRECTIONS_DEG[pin] == 0.0)
    with pytest.raises(ValueError):
        aim_dir_index(hole, cells, "left")


def test_pin_restricted_solve_aims_at_the_pin_and_is_never_better_than_free(toy):
    hole, player, _ = toy
    playable, _ = state_mask(hole)
    free = solve(hole, player, "drop", tol=1e-8, max_sweeps=500)
    pin = solve(hole, player, "drop", tol=1e-8, max_sweeps=500, aim="pin")
    assert np.all(DIRECTIONS_DEG[pin.dir[playable]] == 0.0)
    assert np.all(pin.club[playable] == 0)
    assert np.all(pin.U[playable] >= free.U[playable] - 1e-6)
    assert np.any(pin.U[playable] > free.U[playable] + 0.01)  # the bunkers and OB cost something


def test_one_club_pin_solve_equals_evaluating_the_fixed_pin_policy(toy):
    hole, player, tables = toy
    playable, _ = state_mask(hole)
    dir0 = int(np.flatnonzero(DIRECTIONS_DEG == 0)[0])
    U = initial_values(hole, player)
    for _ in range(500):  # policy evaluation: the single action (club 0, pin) in every cell
        U_new, _, _ = bellman_backup(U, hole, player, tables, "drop", np.array([[0, dir0]]))
        done = np.max(np.abs(U_new[playable] - U[playable])) < 1e-8
        U = U_new
        if done:
            break
    pin = solve(hole, player, "drop", tol=1e-8, max_sweeps=500, aim="pin")
    assert np.allclose(pin.U[playable], -U[playable], atol=1e-5)


def test_free_solve_is_unchanged_by_the_aim_argument(toy, replay_solution):
    hole, player, _ = toy
    again = solve(hole, player, "replay", K=200, max_sweeps=200, aim="free")
    assert np.array_equal(again.U, replay_solution.U, equal_nan=True)
    assert np.array_equal(again.dir, replay_solution.dir)


# part 18 slice 2: clear aim and centre aim -------------------------------------------


def _club(mu_c: float) -> ClubParams:
    return ClubParams(mu_c, 4.0, 0.05, 0.05, 2.0, 1.0, sampled=True, stats=None)


def test_clear_dir_index_steps_off_a_tree_and_keeps_the_target_in_the_open():
    from caddie.value_iteration import clear_dir_index
    from tests.fixtures.toy_hole import TREE_COLS, TREE_ROW, toy_tree_hole

    hole, player = toy_tree_hole(), toy_player()
    dir0 = int(np.flatnonzero(DIRECTIONS_DEG == 0)[0])
    behind = (TREE_ROW - 1) * hole.cols + 5  # one row short of the trees, on the pin line
    beyond = (TREE_ROW + 1) * hole.cols + 5  # past them
    edge = (TREE_ROW - 1) * hole.cols + 1  # two columns left of the tree row
    cells = np.array([behind, beyond, edge])
    lies = np.full(3, int(Lie.FAIRWAY))
    got = clear_dir_index(hole, player, cells, lies, 0, np.full(3, dir0))
    assert got[1] == dir0
    assert got[0] != dir0
    # the step taken is the nearest clear one: every step closer to the pin line is blocked
    from caddie.mdp import tree_ray_table

    ray = tree_ray_table(hole)
    bearing = float(pin_bearing_deg(hole, np.array([27.5]), np.array([17.5]))[0])
    spread = player.clubs["test7i"].sigma_theta_deg

    def blocked(di: int) -> bool:
        deg = bearing + DIRECTIONS_DEG[di]
        bins = np.rint(np.array([deg, deg - spread, deg + spread]) / 0.5).astype(int) % 720
        return bool(np.any(ray[behind, bins] <= 0.5 * 25.0 + 2.5))

    assert not blocked(int(got[0]))
    assert all(blocked(d) for d in range(min(dir0, got[0]) + 1, max(dir0, got[0])))
    assert blocked(dir0)
    assert TREE_COLS[0] > 1  # the edge cell really is off the row


def test_clear_dir_index_is_the_target_on_a_hole_without_trees(toy):
    from caddie.value_iteration import aim_dir_index, clear_dir_index

    hole, player, _ = toy
    playable, _ = state_mask(hole)
    cells = np.flatnonzero(playable)
    target = aim_dir_index(hole, cells, "centre")
    lies = hole.lie.reshape(-1)[cells]
    assert np.array_equal(clear_dir_index(hole, player, cells, lies, 0, target), target)


def test_pin_restricted_solve_converges_behind_trees():
    from tests.fixtures.toy_hole import toy_tree_hole

    hole, player = toy_tree_hole(), toy_player()
    playable, _ = state_mask(hole)
    pin = solve(hole, player, "drop", aim="pin")
    assert pin.sweeps < 100
    assert pin.residual_history[-1] < 0.01
    free = solve(hole, player, "drop")
    assert np.all(pin.U[playable] >= free.U[playable] - 0.02)
    assert np.any(DIRECTIONS_DEG[pin.dir[playable]] != 0.0)  # some cell had to step aside
