"""Tests for part 16: benchmark.py (cases, simulators, metrics, expectations, report)."""

from __future__ import annotations

from pathlib import Path

import numpy as np
import pytest

from caddie.benchmark import CASES_PATH, Case, load_cases
from caddie.mdp import Lie
from tests.fixtures.benchmark_holes import (
    BUNKER_FRONT_COLS,
    BUNKER_FRONT_ROW,
    COLS,
    ROWS,
    bunker_front,
    ob_side,
    open_straight,
    round_numbers,
    water_carry,
)

# --- slice 1: cases and synthetic holes ----------------------------------------------------------


def test_open_straight_is_fairway_with_a_round_green_at_the_far_end():
    hole = open_straight()
    assert hole.lie.shape == (ROWS, COLS) and hole.par == 4
    green = hole.lie == int(Lie.GREEN)
    assert green.sum() == 16  # the 4 x 4 block of centres within 12.5 m of (30, 330)
    assert np.all(hole.lie[~green] == int(Lie.FAIRWAY))
    assert abs(hole.pin_xy[0] - 30.0) < 1e-9 and abs(hole.pin_xy[1] - 330.0) < 1e-9
    assert hole.tee_xy == (30.0, 2.5)


def test_water_carry_band_rows_are_water_across_the_full_width():
    hole = water_carry(180, 200)
    water = hole.lie == int(Lie.WATER)
    rows = np.flatnonzero(water.any(axis=1))
    np.testing.assert_array_equal(rows, [36, 37, 38, 39])  # centres 182.5 to 197.5
    assert np.all(water[36:40])
    assert not water[35].any() and not water[40].any()


def test_ob_side_columns():
    hole = ob_side()
    assert np.all(hole.lie[:, 0:2] == int(Lie.OB))
    below_green = hole.lie[:60]
    assert np.all(below_green[:, 2:8] == int(Lie.FAIRWAY))
    assert np.all(below_green[:, 8:] == int(Lie.ROUGH))


def test_bunker_front_cells_sit_directly_short_of_the_green():
    hole = bunker_front()
    bunker = hole.lie == int(Lie.BUNKER)
    assert bunker.sum() == 3
    for c in BUNKER_FRONT_COLS:
        assert bunker[BUNKER_FRONT_ROW, c]
        assert hole.lie[BUNKER_FRONT_ROW + 1, c] == int(Lie.GREEN)


def test_round_numbers_player_numbers():
    p = round_numbers()
    assert p.club_order[:3] == ["driver", "5h", "7i"] and p.club_order[-1] == "sw20"
    assert len(p.club_order) == 9 and p.clubs["sw20"].mu_c == 20.0
    assert p.clubs["driver"].mu_c == 200.0 and round_numbers(190).clubs["driver"].mu_c == 190.0
    assert p.lie["rough"]["carry"] == 0.9 and p.lie["bunker"]["roll"] == 0.0
    assert float(p.putting(1.0)) == pytest.approx(1.07)


def test_load_cases_builds_every_synthetic_case(tmp_path: Path):
    cases = load_cases(CASES_PATH, tmp_path, ids=None, solve_missing=False)
    ids = [c.id for c in cases]
    for want in ("toy-drop", "toy-replay", "open-straight", "water-carry-weak", "ob-left"):
        assert want in ids
    assert "hole-12-drop-tee" not in ids  # no bundle under tmp_path
    for c in cases:
        assert isinstance(c, Case)
        assert c.hole.lie.ndim == 2 and c.player.club_order and c.expect
        assert c.mode in ("drop", "replay", "mulligan")
        assert len(c.start) == 3 and isinstance(c.start[2], Lie)
    weak = next(c for c in cases if c.id == "water-carry-weak")
    assert weak.player.clubs["driver"].mu_c == 190.0
    assert weak.start == (30.0, 2.5, Lie.TEE)
    front = next(c for c in cases if c.id == "bunker-front")
    assert front.start[1] == pytest.approx(front.hole.pin_xy[1] - 120.0)
    assert front.start[2] == Lie.FAIRWAY


def test_load_cases_rejects_an_unknown_builder(tmp_path: Path):
    bad = tmp_path / "cases.json"
    bad.write_text(
        '[{"id": "x", "hole": {"builder": "nope"}, "player": {"builder": "toy"}, '
        '"mode": "drop", "n": 10, "expect": [{"kind": "order", "lower": "grid", "upper": "pin"}]}]'
    )
    with pytest.raises(ValueError, match="nope"):
        load_cases(bad, tmp_path, solve_missing=False)


# --- slice 4: run_case on the cell simulator ---------------------------------------------------

METRIC_KEYS = {
    "mean_strokes",
    "std_strokes",
    "se_vs_grid",
    "p_blowup",
    "regret",
    "disagreement",
    "build_s",
    "decide_s",
    "decide_ms_per_shot",
    "passed",
    "failed",
}


@pytest.fixture(scope="module")
def toy_case(tmp_path_factory):
    from caddie.benchmark import load_cases

    out = tmp_path_factory.mktemp("out")
    (case,) = load_cases(CASES_PATH, out, ids=["toy-drop"])
    return case


def test_simulate_from_a_fairway_point_takes_fewer_strokes_than_from_the_tee(toy_case):
    from caddie.evaluate import optimal_policy, simulate

    hole, player, sol = toy_case.hole, toy_case.player, toy_case.solution
    pol = optimal_policy(sol, hole)
    tee = simulate(hole, player, pol, "drop", n=500, seed=0)
    near = simulate(hole, player, pol, "drop", n=500, seed=0, start=(7.5, 32.5, Lie.FAIRWAY))
    assert near.mean() < tee.mean() - 0.5
    same = simulate(hole, player, pol, "drop", n=500, seed=0, start=(*hole.tee_xy, Lie.TEE))
    np.testing.assert_array_equal(same, tee)


def test_run_case_metrics_and_expectations_on_the_toy(toy_case):
    from caddie.benchmark import run_case

    result = run_case(toy_case, ["grid", "rollout", "pin", "centre", "greedy"], seed=0)
    assert result["case"] == "toy-drop" and result["simulator"] == "cell"
    for name, m in result["approaches"].items():
        assert METRIC_KEYS <= set(m), name
    grid = result["approaches"]["grid"]
    assert grid["regret"] <= grid["se_vs_grid"] + 1e-9 and grid["se_vs_grid"] == 0.0
    assert grid["disagreement"] == 0.0
    assert result["approaches"]["pin"]["disagreement"] > 0.0
    assert result["approaches"]["greedy"]["decide_s"] > 0.0
    passed = {e for m in result["approaches"].values() for e in m["passed"]}
    assert {"grid-matches-tee-value", "grid-beats-pin", "grid-beats-centre"} <= passed
    assert "rollout-close-to-grid" in passed
    assert result["not_run"] == ["risk", "sparse2", "mcts"] or result["not_run"] == []


def test_check_expectations_reports_a_failing_one_with_its_measured_value(toy_case):
    from dataclasses import replace

    from caddie.benchmark import check_expectations, run_case

    extra = {"id": "impossible", "kind": "order", "lower": "pin", "upper": "grid", "by_at_least": 5}
    case = replace(toy_case, expect=toy_case.expect + [extra])
    result = run_case(case, ["grid", "pin"], seed=0, check=False)
    passed, failed, skipped = check_expectations(case, result)
    assert "grid-beats-pin" in passed
    (bad,) = [f for f in failed if f["id"] == "impossible"]
    assert bad["measured"]["pin"] > bad["measured"]["grid"]
    assert {s["id"] for s in skipped} == {"grid-beats-centre", "rollout-close-to-grid"}


# --- slice 5: point simulator ---------------------------------------------------------------------


def test_point_simulator_with_the_grid_policy_is_near_the_cell_simulator(toy_case):
    from caddie.approaches import APPROACHES
    from caddie.benchmark import simulate_points
    from caddie.evaluate import simulate

    hole, player, sol = toy_case.hole, toy_case.player, toy_case.solution
    cell = simulate(
        hole, player, APPROACHES["grid"].build(hole, player, sol, "drop"), "drop", 3000, 0
    )
    point = APPROACHES["grid"].point(hole, player, sol, "drop")
    strokes, decide_s = simulate_points(hole, player, point, "drop", 3000, 0, toy_case.start)
    assert strokes.shape == (3000,) and decide_s >= 0.0
    assert abs(strokes.mean() - cell.mean()) < 0.15
    again, _ = simulate_points(hole, player, point, "drop", 3000, 0, toy_case.start)
    np.testing.assert_array_equal(again, strokes)  # seeded and paired


def test_point_simulator_matches_an_independent_scalar_monte_carlo(toy_case):
    import math

    from caddie.benchmark import simulate_points
    from caddie.mdp import locate
    from caddie.online import mulberry32, sample_landing
    from tests.fixtures.toy_hole import TOY_CLUB

    hole, player = toy_case.hole, toy_case.player
    club = player.clubs[TOY_CLUB]

    def at_pin(x, y, lie):
        return TOY_CLUB, 0.0

    strokes, _ = simulate_points(hole, player, at_pin, "drop", 4000, 0, toy_case.start)

    rng = mulberry32(7)
    total = 0.0
    for _ in range(4000):
        x, y, lie = toy_case.start
        for _shot in range(40):
            shot = sample_landing(hole, player, club, (x, y), lie, 0.0, "drop", rng)
            total += -shot["reward"]
            x, y = shot["next"]
            _, code, _ = locate(hole, np.array([x]), np.array([y]))
            lie = Lie(int(code[0]))
            if lie == Lie.GREEN:
                total += float(player.putting(math.hypot(x - hole.pin_xy[0], y - hole.pin_xy[1])))
                break
    assert abs(strokes.mean() - total / 4000) < 0.05


def test_run_case_on_the_point_simulator_covers_the_point_capable_approaches(toy_case):
    from dataclasses import replace

    from caddie.benchmark import run_case

    case = replace(toy_case, n=300)
    result = run_case(case, ["grid", "rollout", "pin"], seed=0, simulator="point")
    assert result["simulator"] == "point"
    assert set(result["approaches"]) == {"grid", "rollout"}
    assert result["not_run"] == ["pin"]
    assert result["approaches"]["rollout"]["decide_s"] > result["approaches"]["grid"]["decide_s"]
    assert np.isfinite(result["approaches"]["rollout"]["disagreement"])


# --- slice 8: report and CLI ----------------------------------------------------------------------


def test_report_tables_summary_and_figure(toy_case, tmp_path: Path):
    from dataclasses import replace

    from caddie.benchmark import (
        FOLLOW_UPS,
        plot_strokes_vs_compute,
        run_case,
        write_case_table,
        write_summary,
    )

    case = replace(toy_case, n=300)
    results = [run_case(case, ["grid", "pin", "centre", "greedy"], seed=0)]
    out = tmp_path / "benchmark"
    table = write_case_table(results[0], out)
    assert table == out / "toy-drop_cell.md" and (out / "toy-drop_cell.csv").exists()
    text = table.read_text()
    assert "| grid |" in text and "regret" in text and "Expectations" in text
    summary = write_summary(results, out)
    assert summary == out / "summary.md" and (out / "summary.csv").exists()
    text = summary.read_text()
    rows = [
        line for line in text.splitlines() if line.startswith("| grid") or line.startswith("| pin")
    ]
    assert rows[0].startswith("| grid")  # ranked by mean regret: grid first
    for name in FOLLOW_UPS:
        assert name in text and "not run" in text
    fig = plot_strokes_vs_compute(results, out)
    assert fig == out / "strokes_vs_compute.png" and fig.stat().st_size > 1000


def test_cli_benchmark_runs_two_cases(tmp_path: Path):
    from caddie.cli import main

    code = main(
        [
            "benchmark",
            "--cases",
            "toy-drop,open-straight",
            "--approaches",
            "grid,pin,greedy",
            "--n",
            "200",
            "--point-n",
            "20",
            "--simulator",
            "both",
            "--no-sweeps",
            "--out",
            str(tmp_path),
        ]
    )
    assert code == 0
    out = tmp_path / "benchmark"
    assert (out / "summary.md").exists()
    assert (out / "toy-drop_cell.md").exists() and (out / "open-straight_cell.md").exists()
    assert (out / "toy-drop_point.md").exists()
    assert (out / "strokes_vs_compute.png").exists()
    assert (out / "solutions" / "open_straight_drop.npz").exists()
