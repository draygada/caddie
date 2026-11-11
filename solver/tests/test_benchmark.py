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
    three_club,
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


def test_three_club_player_numbers():
    p = three_club()
    assert p.club_order == ["driver", "7i", "pw"]
    assert p.clubs["driver"].mu_c == 200.0 and three_club(190).clubs["driver"].mu_c == 190.0
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
