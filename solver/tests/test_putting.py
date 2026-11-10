"""Tests for caddie.putting (part 03)."""

import json
from pathlib import Path

import numpy as np
import pytest

from caddie.putting import (
    CONTRACT_DISTANCES_M,
    FT_TO_M,
    GRID_MAX_M,
    GRID_STEP_M,
    PuttingTable,
    build_putting_table,
    load_make_table,
    make_prob,
    solve_expected_putts,
    write_putting_png,
)

DATA = Path(__file__).resolve().parents[1] / "data" / "raw" / "putting.csv"


# slice 1: loader


def test_load_make_table_midpoints_in_meters():
    mids_m, probs = load_make_table(DATA)
    assert mids_m.shape == probs.shape == (8,)
    # first bin 0 to 3 ft, midpoint 1.5 ft
    assert mids_m[0] == pytest.approx(1.5 * FT_TO_M)
    # last bin 30 to 60 ft, midpoint 45 ft
    assert mids_m[-1] == pytest.approx(45.0 * FT_TO_M)
    assert np.all(np.diff(mids_m) > 0)


def test_load_make_table_probabilities():
    _, probs = load_make_table(DATA)
    assert probs[0] == pytest.approx(0.93)
    assert probs[-1] == pytest.approx(0.02)
    assert np.all((probs > 0) & (probs < 1))
    assert np.all(np.diff(probs) < 0)


def test_load_make_table_rejects_bad_header(tmp_path):
    bad = tmp_path / "putting.csv"
    bad.write_text("lo,hi,pct\n0,3,93\n")
    with pytest.raises(ValueError, match="header"):
        load_make_table(bad)


# slice 2: make probability interpolation


@pytest.fixture(scope="module")
def make_table():
    return load_make_table(DATA)


def test_make_prob_is_one_at_zero(make_table):
    mids, probs = make_table
    assert make_prob(np.array([0.0]), mids, probs)[0] == pytest.approx(1.0)


def test_make_prob_at_1p5m(make_table):
    mids, probs = make_table
    p = make_prob(np.array([1.5]), mids, probs)[0]
    assert 0.5 < p < 0.8


def test_make_prob_monotone_and_clamped(make_table):
    mids, probs = make_table
    d = np.linspace(0.0, 60.0, 241)
    p = make_prob(d, mids, probs)
    assert np.all(np.diff(p) <= 1e-12)
    assert p[-1] == pytest.approx(probs[-1])
    assert make_prob(np.array([200.0]), mids, probs)[0] == pytest.approx(probs[-1])


def test_make_prob_accepts_scalar(make_table):
    mids, probs = make_table
    assert np.ndim(make_prob(2.0, mids, probs)) == 0


# slice 3: fixed-point recursion


@pytest.fixture(scope="module")
def table() -> PuttingTable:
    return build_putting_table(DATA)


def test_table_grid(table):
    assert table.distance_m[0] == 0.0
    assert table.distance_m[-1] == pytest.approx(GRID_MAX_M)
    assert np.allclose(np.diff(table.distance_m), GRID_STEP_M)
    assert table.expected_putts.shape == table.distance_m.shape


def test_expected_putts_anchor_values(table):
    assert table(0.3) < 1.1
    assert 1.6 < table(3.0) < 2.0


@pytest.mark.xfail(
    strict=True,
    reason="part file asks for 1.9 < E(12 m) < 2.3, but the specified leave rule "
    "max(0.6 m, 0.12 d) with the 15 hcp table gives about 2.43; needs a human decision "
    "on the leave rule or the band",
)
def test_expected_putts_at_12m_in_part_file_band(table):
    assert 1.9 < table(12.0) < 2.3


def test_expected_putts_monotone(table):
    assert np.all(np.diff(table.expected_putts) >= -1e-12)
    d = np.linspace(0.0, 80.0, 801)
    assert np.all(np.diff(table(d)) >= -1e-12)


def test_recursion_converges_fast(make_table):
    mids, probs = make_table
    grid = np.arange(0.0, GRID_MAX_M + GRID_STEP_M / 2, GRID_STEP_M)
    _, n_iter = solve_expected_putts(grid, mids, probs, leave_frac=0.12, leave_min_m=0.6)
    assert n_iter < 50


def test_call_extrapolates_linearly_beyond_grid(table):
    slope = (table.expected_putts[-1] - table.expected_putts[-2]) / GRID_STEP_M
    assert table(50.0) == pytest.approx(table.expected_putts[-1] + 10.0 * slope)
    assert np.ndim(table(np.array([1.0, 2.0]))) == 1
    assert table(-1.0) == pytest.approx(table.expected_putts[0])


# slice 4: serialize


def test_to_json_matches_contract_shape(table):
    block = table.to_json()
    assert set(block) == {"distance_m", "expected_putts"}
    assert block["distance_m"] == list(CONTRACT_DISTANCES_M) == [1, 2, 3, 4, 6, 8, 10, 15, 25]
    assert len(block["expected_putts"]) == 9
    assert all(isinstance(v, float) for v in block["expected_putts"])
    assert all(isinstance(v, int) for v in block["distance_m"])
    assert block["expected_putts"] == sorted(block["expected_putts"])
    json.dumps(block)


def test_to_json_values_match_table(table):
    block = table.to_json()
    for d, e in zip(block["distance_m"], block["expected_putts"], strict=True):
        assert e == pytest.approx(float(table(d)), abs=1e-3)


def test_putting_png_written(table):
    out = Path(__file__).resolve().parents[1] / "out" / "putting.png"
    write_putting_png(table, out)
    assert out.exists() and out.stat().st_size > 1000
