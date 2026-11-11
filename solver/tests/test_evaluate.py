"""Tests for part 07: evaluate.py (baseline policies, simulation, metrics, bootstrap, figures)."""

from __future__ import annotations

import numpy as np
import pytest

from caddie.evaluate import centre_policy, optimal_policy, pin_policy
from caddie.mdp import DIRECTIONS_DEG, Lie
from caddie.value_iteration import solve
from tests.fixtures.toy_hole import TOY_CLUB, toy_hole, toy_player

DIR0 = int(np.flatnonzero(DIRECTIONS_DEG == 0)[0])


@pytest.fixture(scope="module")
def toy_drop():
    hole = toy_hole()
    player = toy_player()
    return solve(hole, player, "drop", K=200, tol=0.01, max_sweeps=50), hole, player


# --- slice 1: baseline policies -----------------------------------------------------------------


def test_pin_policy_from_the_tee_is_dir_0_and_the_only_club(toy_drop):
    _, hole, player = toy_drop
    policy = pin_policy(hole, player)
    club_idx, dir_idx = policy(hole.tee_xy[0], hole.tee_xy[1], Lie.FAIRWAY)
    assert player.club_order[club_idx] == TOY_CLUB
    assert dir_idx == DIR0
    assert float(DIRECTIONS_DEG[dir_idx]) == 0.0


def test_centre_policy_aims_at_the_green_centroid_with_the_closest_club(toy_drop):
    _, hole, player = toy_drop
    policy = centre_policy(hole, player)
    club_idx, dir_idx = policy(hole.tee_xy[0], hole.tee_xy[1], Lie.FAIRWAY)
    assert player.club_order[club_idx] == TOY_CLUB
    # the toy green is symmetric about the pin column, so its centroid sits on the pin bearing
    assert dir_idx == DIR0
    # from a point left of the green the aim swings right of the pin bearing
    _, right = policy(2.5, 42.5, Lie.FAIRWAY)
    assert abs(float(DIRECTIONS_DEG[right])) <= 10


def test_optimal_policy_reads_the_solution_grids(toy_drop):
    solution, hole, player = toy_drop
    policy = optimal_policy(solution, hole)
    for idx in (5, 23, 61):
        r, c = divmod(idx, hole.cols)
        x, y = (c + 0.5) * hole.cell_m, (r + 0.5) * hole.cell_m
        assert policy(x, y, Lie(int(hole.lie[r, c]))) == (
            int(solution.club[idx]),
            int(solution.dir[idx]),
        )
    with pytest.raises(ValueError):
        policy(hole.pin_xy[0], hole.pin_xy[1], Lie.GREEN)  # terminal: no action
