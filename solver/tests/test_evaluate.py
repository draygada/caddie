"""Tests for part 07: evaluate.py (baseline policies, simulation, metrics, bootstrap, figures)."""

from __future__ import annotations

from dataclasses import replace
from pathlib import Path

import numpy as np
import pytest

from caddie.dispersion import Player
from caddie.evaluate import (
    bootstrap_fit,
    centre_policy,
    evaluate_hole,
    optimal_policy,
    pin_policy,
    robustness,
    simulate,
)
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


# --- slice 2: simulate ------------------------------------------------------------------------


def test_simulate_optimal_matches_the_value_grid_at_the_tee(toy_drop):
    solution, hole, player = toy_drop
    strokes = simulate(hole, player, optimal_policy(solution, hole), "drop", n=5000, seed=0)
    assert strokes.shape == (5000,)
    tee = int(hole.tee_xy[1] // hole.cell_m) * hole.cols + int(hole.tee_xy[0] // hole.cell_m)
    assert abs(float(strokes.mean()) - float(solution.U[tee])) < 0.1
    assert np.all(strokes >= 2.0)  # at least one shot plus the flat 1.5 putts


def test_simulate_is_seeded_and_pairs_draws_across_policies(toy_drop):
    solution, hole, player = toy_drop
    a = simulate(hole, player, optimal_policy(solution, hole), "drop", n=200, seed=3)
    b = simulate(hole, player, optimal_policy(solution, hole), "drop", n=200, seed=3)
    np.testing.assert_array_equal(a, b)
    c = simulate(hole, player, optimal_policy(solution, hole), "drop", n=200, seed=4)
    assert not np.array_equal(a, c)


def test_simulate_pin_policy_is_no_better_than_optimal(toy_drop):
    solution, hole, player = toy_drop
    opt = simulate(hole, player, optimal_policy(solution, hole), "replay", n=3000, seed=1)
    pin = simulate(hole, player, pin_policy(hole, player), "replay", n=3000, seed=1)
    assert pin.mean() >= opt.mean() - 0.05
    # the toy brute force for "aim at the pin" under replay is about 8.3 strokes (part 04)
    assert 6.0 < pin.mean() < 10.0


# --- slice 3: evaluate_hole ----------------------------------------------------------------------

METRIC_KEYS = {
    "mean_strokes",
    "std_strokes",
    "histogram",
    "p_blowup",
    "disagreement",
    "strokes_saved_per_round",
}


def test_evaluate_hole_metrics(toy_drop):
    solution, hole, player = toy_drop
    results = evaluate_hole(hole, player, solution, "drop", n=2000, seed=0)
    assert set(results) >= {"hole", "mode", "par", "n", "policies"}
    assert set(results["policies"]) == {"optimal", "pin", "centre"}
    for name, m in results["policies"].items():
        assert set(m) == METRIC_KEYS, name
        assert sum(m["histogram"].values()) == 2000
        assert all(isinstance(k, int) for k in m["histogram"])
        assert 0.0 <= m["p_blowup"] <= 1.0
        assert 0.0 <= m["disagreement"] <= 1.0
    opt, pin = results["policies"]["optimal"], results["policies"]["pin"]
    assert opt["mean_strokes"] <= pin["mean_strokes"] <= pin["mean_strokes"] + 2.0
    assert opt["mean_strokes"] <= pin["mean_strokes"] + 1e-9
    assert pin["mean_strokes"] <= opt["mean_strokes"] + 2.0
    assert opt["disagreement"] == 0.0
    assert pin["disagreement"] > 0.0
    assert opt["strokes_saved_per_round"] == 0.0
    assert pin["strokes_saved_per_round"] == pytest.approx(
        18.0 * (pin["mean_strokes"] - opt["mean_strokes"])
    )
    assert results["strokes_saved_label"].startswith("extrapolation")


# --- slice 4: bootstrap -------------------------------------------------------------------

FIXTURE_CSV = Path(__file__).resolve().parent / "fixtures" / "shots_fixture.csv"
PUTTING_CSV = Path(__file__).resolve().parents[1] / "data" / "raw" / "putting.csv"


def test_bootstrap_fit_players_are_finite_with_a_tight_driver_carry():
    players = bootstrap_fit(FIXTURE_CSV, n_boot=5, seed=0, putting_path=PUTTING_CSV, handicap=15)
    assert len(players) == 5
    mus = []
    for p in players:
        assert p.club_order == players[0].club_order
        for name, cp in p.clubs.items():
            for v in (cp.mu_c, cp.sigma_theta_deg, cp.sigma_d, cp.p, cp.mu_r, cp.sigma_r):
                assert np.isfinite(v), (name, v)
        mus.append(p.clubs["driver"].mu_c)
    spread = (max(mus) - min(mus)) / float(np.mean(mus))
    assert spread < 0.15  # 3 driver shots in the fixture: see the xfail below for the 5% band
    # resampling changes the fit: not every bootstrap is identical
    assert len({round(m, 6) for m in mus}) > 1


@pytest.mark.xfail(
    strict=True,
    reason="part file band: driver mu_c spread under 5 percent across 5 bootstraps; the "
    "fixture CSV has 3 driver shots (sd 9 m), so a bootstrap mean moves by about 5 m and "
    "the spread is near 6 percent. The real export has 100 driver shots.",
)
def test_bootstrap_driver_spread_under_5_percent_part_file_band():
    players = bootstrap_fit(FIXTURE_CSV, n_boot=5, seed=0, putting_path=PUTTING_CSV, handicap=15)
    mus = [p.clubs["driver"].mu_c for p in players]
    assert (max(mus) - min(mus)) / float(np.mean(mus)) < 0.05


def test_bootstrap_fit_is_seeded():
    a = bootstrap_fit(FIXTURE_CSV, n_boot=2, seed=1, putting_path=PUTTING_CSV, handicap=15)
    b = bootstrap_fit(FIXTURE_CSV, n_boot=2, seed=1, putting_path=PUTTING_CSV, handicap=15)
    assert [p.clubs["driver"].mu_c for p in a] == [p.clubs["driver"].mu_c for p in b]


# --- slice 5: robustness --------------------------------------------------------------------


def _jittered_players(base: Player, n: int, seed: int) -> list[Player]:
    """Toy stand-ins for bootstrap players: the toy club with carry jittered by a few percent."""
    rng = np.random.default_rng(seed)
    out = []
    for _ in range(n):
        mu = base.clubs[TOY_CLUB].mu_c * (1 + rng.normal(0, 0.03))
        club = replace(base.clubs[TOY_CLUB], mu_c=mu)
        out.append(replace(base, clubs={TOY_CLUB: club}))
    return out


def test_robustness_percentiles_bracket_the_point_estimate(toy_drop):
    solution, hole, player = toy_drop
    players = _jittered_players(player, 5, seed=0)
    rob = robustness(hole, players, "drop", reference=solution, K=200, tol=0.01, max_sweeps=50)
    assert set(rob) >= {
        "n_boot",
        "tee_value_mean",
        "tee_value_p05",
        "tee_value_p95",
        "tee_values",
        "disagreement",
    }
    assert rob["n_boot"] == 5 and len(rob["tee_values"]) == 5
    tee = int(hole.tee_xy[1] // hole.cell_m) * hole.cols + int(hole.tee_xy[0] // hole.cell_m)
    point = float(solution.U[tee])
    assert rob["tee_value_p05"] <= point + 0.05
    assert rob["tee_value_p95"] >= point - 0.05
    assert rob["tee_value_p05"] <= rob["tee_value_mean"] <= rob["tee_value_p95"]
    assert len(rob["disagreement"]) == 5
    assert all(0.0 <= d <= 1.0 for d in rob["disagreement"])
