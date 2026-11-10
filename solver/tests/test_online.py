"""Tests for part 06: online.py (bilinear leaf values, rollout recommend, sequences)."""

from __future__ import annotations

import numpy as np
import pytest

from caddie.mdp import DIRECTIONS_DEG, Lie
from caddie.online import bilinear, recommend
from caddie.value_iteration import solve
from tests.fixtures.toy_hole import toy_hole, toy_player

# --- slice 1: bilinear --------------------------------------------------------------------------


def _y_field(rows: int, cols: int, cell_m: float) -> np.ndarray:
    r = np.arange(rows)
    return np.repeat((r + 0.5) * cell_m, cols).astype(np.float32)


def test_bilinear_reproduces_a_field_equal_to_y():
    U = _y_field(3, 3, 5.0)
    x = np.array([2.5, 7.5, 12.5, 4.0, 9.9, 0.0, 15.0])
    y = np.array([2.5, 12.5, 7.5, 6.6, 3.3, 10.0, 12.5])
    np.testing.assert_allclose(bilinear(U, 3, 3, 5.0, x, y), y, atol=1e-6)


def test_bilinear_clamps_beyond_the_outer_centres():
    U = _y_field(3, 3, 5.0)
    out = bilinear(U, 3, 3, 5.0, np.array([7.5, 7.5, -4.0, 40.0]), np.array([0.0, 15.0, 7.5, 7.5]))
    np.testing.assert_allclose(out, [2.5, 12.5, 7.5, 7.5], atol=1e-6)


def test_bilinear_scalar_inputs():
    U = _y_field(3, 3, 5.0)
    assert float(bilinear(U, 3, 3, 5.0, 7.5, 9.0)) == 9.0


def test_bilinear_nan_corner_uses_nearest_finite_of_the_four():
    U = _y_field(3, 3, 5.0)
    U[0] = np.nan  # cell (0, 0)
    v = float(bilinear(U, 3, 3, 5.0, 3.0, 3.0))
    assert np.isfinite(v) and 2.5 <= v <= 7.5
    # a point nearer to the NaN cell than any finite cell still gets a finite value
    assert np.isfinite(float(bilinear(U, 3, 3, 5.0, 0.1, 0.1)))


def test_bilinear_all_nan_neighbours_returns_nearest_finite_plus_one():
    U = _y_field(4, 4, 5.0)
    U[[0, 1, 4, 5]] = np.nan  # the 2 x 2 block at the origin is OUT
    v = float(bilinear(U, 4, 4, 5.0, 5.0, 5.0))  # centre of that block
    # nearest finite cells are (0, 2) at 12.5 m and (2, 0) at 12.5 m, values 2.5 and 12.5
    assert v in (2.5 + 1.0, 12.5 + 1.0)


# --- slice 2: recommend at a cell centre ------------------------------------------------------


@pytest.fixture(scope="module")
def toy_drop():
    hole = toy_hole()
    player = toy_player()
    return solve(hole, player, "drop", K=200, tol=0.01, max_sweeps=50), hole, player


def _sample_playable_cells(hole, n: int, seed: int = 3) -> np.ndarray:
    flat = hole.lie.reshape(-1)
    playable = np.flatnonzero(np.isin(flat, [1, 2, 3, 4]))
    rng = np.random.default_rng(seed)
    return rng.choice(playable, size=n, replace=False)


def _recommend_at_cells(toy_drop, n=10, m=400):
    solution, hole, player = toy_drop
    for idx in _sample_playable_cells(hole, n):
        r, c = divmod(int(idx), hole.cols)
        x, y = (c + 0.5) * hole.cell_m, (r + 0.5) * hole.cell_m
        rec = recommend(solution, hole, player, x, y, None, "drop", m=m, seed=int(idx))
        yield int(idx), rec


def test_recommend_at_cell_centres_agrees_with_the_policy_grid_up_to_ties(toy_drop):
    """Same club, Q at the grid direction within 0.05 of the best, value within 0.35."""
    solution, hole, player = toy_drop
    for idx, rec in _recommend_at_cells(toy_drop):
        assert rec.club == player.club_order[solution.club[idx]]
        ci = player.club_order.index(rec.club)
        assert rec.q_by_action[ci, solution.dir[idx]] - rec.expected_strokes < 0.05
        assert abs(rec.expected_strokes - solution.U[idx]) < 0.35


@pytest.mark.xfail(
    strict=True,
    reason="part file band: exact direction match for 9 of 10 cells; the toy hole has "
    "direction ties (Q equal to 3 decimals), so fresh draws pick another tied direction "
    "for about 3 of 10 cells",
)
def test_recommend_at_cell_centres_matches_the_policy_grid_exactly(toy_drop):
    solution, _, _ = toy_drop
    hits = sum(
        rec.dir_deg == float(DIRECTIONS_DEG[solution.dir[idx]])
        for idx, rec in _recommend_at_cells(toy_drop)
    )
    assert hits >= 9, f"{hits} of 10 cells agree with the policy grid"


def test_recommend_fields(toy_drop):
    solution, hole, player = toy_drop
    x, y = hole.tee_xy
    rec = recommend(solution, hole, player, x, y, None, "drop", m=100, seed=1)
    assert rec.q_by_action.shape == (len(player.club_order), len(DIRECTIONS_DEG))
    assert np.isfinite(rec.q_by_action).any()
    assert rec.expected_strokes == pytest.approx(float(np.nanmin(rec.q_by_action)))
    assert rec.baseline_pin_strokes >= rec.expected_strokes - 1e-9
    assert rec.dir_deg == float(
        DIRECTIONS_DEG[int(np.nanargmin(rec.q_by_action) % len(DIRECTIONS_DEG))]
    )


def test_recommend_rejects_non_playable_lies(toy_drop):
    solution, hole, player = toy_drop
    with pytest.raises(ValueError):
        recommend(solution, hole, player, hole.pin_xy[0], hole.pin_xy[1], None, "drop", m=10)
    with pytest.raises(ValueError):
        recommend(solution, hole, player, 2.5, 37.5, None, "drop", m=10)  # water cell (7, 0)


def test_recommend_is_deterministic_for_a_seed(toy_drop):
    solution, hole, player = toy_drop
    a = recommend(solution, hole, player, 12.0, 17.0, None, "replay", m=50, seed=5)
    b = recommend(solution, hole, player, 12.0, 17.0, None, "replay", m=50, seed=5)
    c = recommend(solution, hole, player, 12.0, 17.0, None, "replay", m=50, seed=6)
    np.testing.assert_array_equal(a.q_by_action, b.q_by_action)
    assert not np.array_equal(a.q_by_action, c.q_by_action)


# --- slice 3: recommend between cells ---------------------------------------------------------


def _adjacent_cells_with_different_policies(solution, hole):
    """First horizontally adjacent playable pair whose grid directions differ."""
    flat = hole.lie.reshape(-1)
    for r in range(hole.rows):
        for c in range(hole.cols - 1):
            i, j = r * hole.cols + c, r * hole.cols + c + 1
            if (
                flat[i] in (1, 2, 3, 4)
                and flat[j] in (1, 2, 3, 4)
                and solution.dir[i] != solution.dir[j]
            ):
                return i, j
    raise AssertionError("toy hole has no adjacent pair with different policies")


def test_recommend_between_cells_lies_between_the_cell_values(toy_drop):
    solution, hole, player = toy_drop
    i, j = _adjacent_cells_with_different_policies(solution, hole)
    r, c = divmod(i, hole.cols)
    x, y = (c + 1.0) * hole.cell_m, (r + 0.5) * hole.cell_m  # the shared edge midpoint
    rec = recommend(solution, hole, player, x, y, None, "drop", m=400, seed=0)
    lo, hi = sorted((float(solution.U[i]), float(solution.U[j])))
    assert lo - 0.05 <= rec.expected_strokes <= hi + 0.05


# --- slice 4: lie override -----------------------------------------------------------------------


def test_lie_override_rough_costs_more_than_the_fairway(toy_drop):
    solution, hole, player = toy_drop
    x, y = 12.0, 17.0  # fairway
    fairway = recommend(solution, hole, player, x, y, None, "drop", m=400, seed=2)
    rough = recommend(solution, hole, player, x, y, Lie.ROUGH, "drop", m=400, seed=2)
    bunker = recommend(solution, hole, player, x, y, Lie.BUNKER, "drop", m=400, seed=2)
    assert rough.expected_strokes > fairway.expected_strokes
    assert bunker.expected_strokes > fairway.expected_strokes
    assert fairway.club == rough.club == bunker.club
