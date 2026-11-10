"""Tests for caddie.dispersion (part 02)."""

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


# slice 2 -------------------------------------------------------------------


def test_update_nig_recovers_mean_and_std():
    from caddie.dispersion import params_from_stats, prior_for, update_nig

    rng = np.random.default_rng(0)
    x = rng.normal(215.0, 15.0, size=200)
    s = prior_for("driver", handicap=15, driver_mu_hint=215.0).carry
    for v in x:
        s = update_nig(s, float(v))
    assert abs(s.m - 215.0) < 2.0
    assert abs(np.sqrt(s.beta / (s.alpha - 1)) - 15.0) < 2.0
    assert s.kappa == pytest.approx(5.0 + 200)
    stats = prior_for("driver", 15, 215.0)
    stats.carry = s
    mu_c, _, sigma_d, _, _ = params_from_stats(stats)
    assert mu_c == pytest.approx(s.m)
    assert abs(sigma_d - 15.0 / 215.0) < 0.01


def test_update_ig_recovers_direction_sigma():
    from caddie.dispersion import prior_for, update_ig

    rng = np.random.default_rng(1)
    theta = rng.normal(0.0, 6.0, size=200)
    s = prior_for("driver", 15, 215.0).theta
    for v in theta:
        s = update_ig(s, float(v))
    assert abs(np.sqrt(s.beta / (s.alpha - 1)) - 6.0) < 0.6


def test_update_order_does_not_matter():
    from caddie.dispersion import prior_for, update_club_stats

    rng = np.random.default_rng(2)
    n = 50
    carry = rng.normal(140, 8, n)
    total = carry + rng.normal(5, 2, n)
    lateral = rng.normal(0, 6, n)
    a = b = prior_for("7i", 15, 215.0)
    for i in range(n):
        a = update_club_stats(a, carry[i], total[i], lateral[i])
    for i in reversed(range(n)):
        b = update_club_stats(b, carry[i], total[i], lateral[i])
    assert a.n == b.n == n
    for comp in ("carry", "theta", "roll"):
        for fld, va in vars(getattr(a, comp)).items():
            assert abs(va - getattr(getattr(b, comp), fld)) < 1e-9 * max(1.0, abs(va))
