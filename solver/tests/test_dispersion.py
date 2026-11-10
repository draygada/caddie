"""Tests for caddie.dispersion (part 02)."""

import json
from pathlib import Path

import numpy as np
import pytest

FIXTURE_CSV = Path(__file__).resolve().parent / "fixtures" / "shots_fixture.csv"
FIXTURES = Path(__file__).resolve().parents[2] / "docs" / "fixtures"


# slice 1 -------------------------------------------------------------------


def test_load_shots_fixture():
    from caddie.dispersion import load_shots

    shots = load_shots(FIXTURE_CSV)
    assert set(shots) == {"driver", "5h", "7i", "9i", "sw"}
    d = shots["driver"]
    assert d.shape == (3,)
    for col in ("carry_m", "total_m", "lateral_m"):
        assert np.issubdtype(d[col].dtype, np.floating)
    assert d["lie"].dtype.kind == "U"
    assert (shots["driver"]["lateral_m"] < 0).any()
    assert set(shots["7i"]["lie"]) == {"mat", "rough"}


def test_load_shots_rejects_bad_header(tmp_path):
    from caddie.dispersion import load_shots

    bad = tmp_path / "bad.csv"
    bad.write_text("club,carry,total\n7i,1,2\n")
    with pytest.raises(ValueError, match="header"):
        load_shots(bad)


def test_committed_shots_csv_has_schema_only():
    from caddie.dispersion import SHOTS_COLUMNS

    path = Path(__file__).resolve().parents[1] / "data" / "raw" / "shots.csv"
    lines = path.read_text().splitlines()
    assert lines[0].split(",") == list(SHOTS_COLUMNS)
