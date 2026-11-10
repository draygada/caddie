"""Tests for caddie.value_iteration (part 05)."""

import numpy as np
import pytest

from caddie.mdp import DIRECTIONS_DEG, Lie, build_offset_tables, make_draws, pin_bearing_deg
from caddie.value_iteration import (
    Solution,
    all_actions,
    bellman_backup,
    initial_values,
    solve,
    state_mask,
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
