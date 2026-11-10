"""Tests for caddie.value_iteration (part 05)."""

import numpy as np
import pytest

from caddie.mdp import Lie, build_offset_tables, make_draws
from caddie.value_iteration import all_actions, bellman_backup, initial_values, state_mask
from tests.fixtures.toy_hole import toy_hole, toy_player

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
