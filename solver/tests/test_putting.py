"""Tests for caddie.putting (part 03)."""

from pathlib import Path

import numpy as np
import pytest

from caddie.putting import FT_TO_M, load_make_table

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
