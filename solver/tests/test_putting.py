"""Tests for caddie.putting (part 03)."""

from pathlib import Path

import numpy as np
import pytest

from caddie.putting import FT_TO_M, load_make_table, make_prob

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
