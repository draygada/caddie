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


# slice 3 -------------------------------------------------------------------


def test_prior_with_zero_shots_is_in_band():
    from caddie.dispersion import params_from_stats, prior_for

    mu_c, sigma_theta, sigma_d, mu_r, sigma_r = params_from_stats(prior_for("7i", 15, 215.0))
    assert 120 <= mu_c <= 160
    assert 5 <= sigma_theta <= 9
    assert sigma_d == pytest.approx(0.08)
    assert mu_r > 0 and sigma_r > 0


def test_prior_moves_posterior_mean_under_three_percent():
    from caddie.dispersion import params_from_stats, prior_for, update_club_stats

    rng = np.random.default_rng(3)
    carry = rng.normal(150.0, 10.0, 50)  # deliberately off the 7i prior centre (~140)
    total = carry + rng.normal(4, 1.5, 50)
    lateral = rng.normal(0, 8, 50)
    s = prior_for("7i", 15, 215.0)
    for c, t, lat in zip(carry, total, lateral, strict=True):
        s = update_club_stats(s, float(c), float(t), float(lat))
    mu_c = params_from_stats(s)[0]
    assert abs(mu_c - carry.mean()) / carry.mean() < 0.03


# slice 4 -------------------------------------------------------------------


def _mixture_carries(rng, n, mu_c, sigma_d, p):
    mishit = rng.random(n) < p
    x = rng.normal(0.0, 1.0, n) + np.where(mishit, -2.0, 0.0)
    return mu_c * (1 + sigma_d * x)


def test_fit_p_recovers_mishit_rate():
    from caddie.dispersion import fit_p

    rng = np.random.default_rng(0)  # seed 4 draws only 2 mishits in 60, which fits p = 0.02
    carry = _mixture_carries(rng, 60, 140.0, 0.06, 0.10)
    p = fit_p(carry, mu_c=140.0, sigma_d=0.06)
    assert 0.03 <= p <= 0.20


def test_fit_p_hits_lower_bound_without_mishits():
    from caddie.dispersion import fit_p

    rng = np.random.default_rng(5)
    carry = _mixture_carries(rng, 60, 140.0, 0.06, 0.0)
    p = fit_p(carry, mu_c=140.0, sigma_d=0.06)
    assert p == pytest.approx(0.02, abs=1e-3)


def test_fit_club_round_trips_synthetic_data():
    from caddie.dispersion import SHOT_DTYPE, fit_club

    rng = np.random.default_rng(6)
    n = 80
    carry = _mixture_carries(rng, n, 140.0, 0.06, 0.08)
    theta = rng.normal(0, 6.0, n)
    lateral = carry * np.tan(np.radians(theta))
    total = carry + rng.normal(5.0, 2.0, n)
    shots = np.array(
        [(c, t, lat, "mat", "2026-11-01") for c, t, lat in zip(carry, total, lateral, strict=True)],
        dtype=SHOT_DTYPE,
    )
    cp = fit_club("7i", shots, handicap=15, driver_mu_hint=215.0)
    assert cp.sampled and cp.stats is not None and cp.stats.n == n
    assert abs(cp.mu_c - carry.mean()) < 2.0
    assert abs(cp.sigma_theta_deg - 6.0) < 1.0
    assert abs(cp.mu_r - 5.0) < 1.0
    assert abs(cp.sigma_r - 2.0) < 0.7
    assert 0.02 <= cp.p <= 0.25
