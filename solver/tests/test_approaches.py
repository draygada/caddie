"""Tests for part 16: approaches.py (the policy factories the benchmark compares)."""

from __future__ import annotations

import numpy as np
import pytest

from caddie.approaches import (
    APPROACHES,
    Approach,
    memoise_policy,
    playable_cells,
)
from caddie.evaluate import centre_policy, optimal_policy, pin_policy
from caddie.mdp import DIRECTIONS_DEG, Lie
from caddie.online import recommend
from caddie.value_iteration import solve
from tests.fixtures.toy_hole import toy_hole, toy_player

EIGHT = ("grid", "rollout", "pin", "centre", "greedy", "risk", "sparse2", "mcts")


@pytest.fixture(scope="module")
def toy_drop():
    hole = toy_hole()
    player = toy_player()
    return solve(hole, player, "drop", K=200, tol=0.01, max_sweeps=50), hole, player


# --- slice 2: registry ---------------------------------------------------------------------------


def test_registry_has_the_eight_ids_with_their_solution_needs():
    assert tuple(APPROACHES) == EIGHT
    for a in APPROACHES.values():
        assert isinstance(a, Approach) and a.id in EIGHT
    assert {k for k, a in APPROACHES.items() if not a.needs_solution} == {"pin", "centre", "greedy"}
    assert {k for k, a in APPROACHES.items() if a.point is not None} == {
        "grid",
        "rollout",
        "sparse2",
        "mcts",
    }


def _cells_xy(hole, cells):
    r, c = np.divmod(cells, hole.cols)
    return (c + 0.5) * hole.cell_m, (r + 0.5) * hole.cell_m


def test_grid_pin_centre_reproduce_part_07(toy_drop):
    solution, hole, player = toy_drop
    flat = hole.lie.reshape(-1)
    cells = playable_cells(hole, solution)
    xs, ys = _cells_xy(hole, cells)
    for name, ref in (
        ("grid", optimal_policy(solution, hole)),
        ("pin", pin_policy(hole, player)),
        ("centre", centre_policy(hole, player)),
    ):
        pol = APPROACHES[name].build(hole, player, solution, "drop")
        for x, y, cell in zip(xs, ys, cells, strict=True):
            lie = Lie(int(flat[cell]))
            assert pol(float(x), float(y), lie) == ref(float(x), float(y), lie)


def test_rollout_agrees_with_grid_at_cell_centres_up_to_ties(toy_drop):
    """Same club at every sampled cell; the grid direction's Q within 0.05 of the rollout's
    best (part 06 found the toy has direction ties, so exact matches are about 4 of 10)."""
    solution, hole, player = toy_drop
    flat = hole.lie.reshape(-1)
    cells = playable_cells(hole, solution)
    pick = np.random.default_rng(1).choice(cells, size=10, replace=False)
    xs, ys = _cells_xy(hole, pick)
    grid = APPROACHES["grid"].build(hole, player, solution, "drop")
    rollout = APPROACHES["rollout"].build(hole, player, solution, "drop", m=400)
    within = 0
    for x, y, c in zip(xs, ys, pick, strict=True):
        lie = Lie(int(flat[c]))
        gc, gd = grid(float(x), float(y), lie)
        rc, _rd = rollout(float(x), float(y), lie)
        assert rc == gc
        rec = recommend(solution, hole, player, float(x), float(y), lie, "drop", m=400, seed=0)
        within += rec.q_by_action[gc, gd] - rec.expected_strokes < 0.05
    assert within >= 9, f"{within} of 10 cells within 0.05 of the rollout's best"


def test_grid_point_policy_returns_names_and_degrees(toy_drop):
    solution, hole, player = toy_drop
    point = APPROACHES["grid"].point(hole, player, solution, "drop")
    club, deg = point(*hole.tee_xy, Lie.TEE)
    assert club in player.clubs and float(deg) in set(DIRECTIONS_DEG.tolist())


def test_memoise_policy_decides_each_cell_once(toy_drop):
    solution, hole, player = toy_drop
    calls = []

    def slow(x, y, lie):
        calls.append((x, y, lie))
        return 0, 45

    pol = memoise_policy(hole, slow)
    assert pol(2.5, 2.5, Lie.TEE) == (0, 45)
    assert pol(2.6, 2.4, Lie.TEE) == (0, 45)  # same cell
    assert pol(2.5, 2.5, Lie.ROUGH) == (0, 45)  # a different lie is a different state
    assert len(calls) == 2


# --- slice 3: greedy -----------------------------------------------------------------------------


def test_greedy_hits_the_driver_at_the_pin_on_the_open_hole():
    from tests.fixtures.benchmark_holes import open_straight, round_numbers

    hole, player = open_straight(), round_numbers()
    greedy = APPROACHES["greedy"].build(hole, player, None, "drop")
    club, direction = greedy(*hole.tee_xy, Lie.TEE)
    assert player.club_order[club] == "driver"
    assert abs(float(DIRECTIONS_DEG[direction])) <= 2.0


def test_greedy_is_no_better_than_grid_on_the_toy(toy_drop):
    from caddie.evaluate import simulate

    solution, hole, player = toy_drop
    grid = APPROACHES["grid"].build(hole, player, solution, "drop")
    greedy = memoise_policy(hole, APPROACHES["greedy"].build(hole, player, None, "drop"))
    a = simulate(hole, player, grid, "drop", n=2000, seed=0)
    b = simulate(hole, player, greedy, "drop", n=2000, seed=0)
    assert b.mean() >= a.mean() - 0.02


# --- slice 6: risk (exponential utility) -------------------------------------------------------


def test_exponential_utility_solve_converges_and_differs_from_grid_near_the_water(toy_drop):
    from caddie.approaches import risk_solution
    from caddie.value_iteration import solve as vi_solve

    solution, hole, player = toy_drop
    risk = risk_solution(hole, player, "drop", lam=0.5, K=200)
    assert risk.residual_history[-1] < 0.01
    cells = playable_cells(hole, solution)
    assert np.all(np.isfinite(risk.U[cells]))
    # the certainty equivalent is never below the expected strokes (Jensen)
    assert np.all(risk.U[cells] >= solution.U[cells] - 1e-3)
    differ = cells[
        (risk.club[cells] != solution.club[cells]) | (risk.dir[cells] != solution.dir[cells])
    ]
    assert differ.size > 0
    # lambda -> 0 recovers the expected-strokes solution
    tiny = vi_solve(hole, player, "drop", K=200, objective=("exp", 1e-4))
    np.testing.assert_allclose(tiny.U[cells], solution.U[cells], atol=0.02)
    plain = vi_solve(hole, player, "drop", K=200, objective="strokes")
    np.testing.assert_array_equal(plain.club, solution.club)


def test_risk_has_fewer_blowups_than_grid_on_the_weak_water_carry():
    from caddie.benchmark import CASES_PATH, load_cases, run_case
    from caddie.value_iteration import solve as vi_solve

    def plain(hole, player, mode, key, out_dir):
        return vi_solve(hole, player, mode, K=200)

    (case,) = load_cases(CASES_PATH, out_dir=None, ids=["water-carry-weak"], solve_fn=plain)
    result = run_case(case, ["grid", "pin", "risk"], seed=0)
    assert "grid-lays-up" in result["passed"] and "pin-goes-for-it" in result["passed"]
    assert "risk-fewer-blowups" in result["passed"]
    m = result["approaches"]
    assert abs(m["risk"]["mean_strokes"] - m["grid"]["mean_strokes"]) <= 0.3
    assert m["risk"]["build_s"] > 0.0
