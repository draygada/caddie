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


# slice 5 -------------------------------------------------------------------


def _synthetic_shots(rng, n, mu_c, sigma_d, p, sigma_theta, mu_r, sigma_r, lie="mat"):
    from caddie.dispersion import SHOT_DTYPE

    carry = _mixture_carries(rng, n, mu_c, sigma_d, p)
    theta = rng.normal(0, sigma_theta, n)
    lateral = carry * np.tan(np.radians(theta))
    total = carry + rng.normal(mu_r, sigma_r, n)
    return np.array(
        [(c, t, lat, lie, "2026-11-01") for c, t, lat in zip(carry, total, lateral, strict=True)],
        dtype=SHOT_DTYPE,
    )


def test_fit_rough_multipliers_recovers_carry_ratio():
    from caddie.dispersion import fit_club, fit_rough_multipliers

    rng = np.random.default_rng(7)
    mat = fit_club("7i", _synthetic_shots(rng, 50, 140.0, 0.06, 0.05, 6.0, 5.0, 2.0), 15, 215.0)
    rough = _synthetic_shots(rng, 20, 140.0 * 0.88, 0.08, 0.05, 8.0, 2.5, 2.0, lie="rough")
    mult = fit_rough_multipliers(mat, rough)
    assert set(mult) == {"carry", "sigma", "roll"}
    assert abs(mult["carry"] - 0.88) < 0.03
    assert mult["sigma"] > 1.0
    assert 0.0 <= mult["roll"] <= 1.0


def test_fit_rough_multipliers_defaults_below_15_shots():
    from caddie.dispersion import ROUGH_DEFAULTS, fit_club, fit_rough_multipliers

    rng = np.random.default_rng(8)
    mat = fit_club("7i", _synthetic_shots(rng, 50, 140.0, 0.06, 0.05, 6.0, 5.0, 2.0), 15, 215.0)
    rough = _synthetic_shots(rng, 14, 120.0, 0.08, 0.05, 8.0, 2.5, 2.0, lie="rough")
    assert fit_rough_multipliers(mat, rough) == ROUGH_DEFAULTS


# slice 6 -------------------------------------------------------------------


def _sampled_bag():
    from caddie.dispersion import ClubParams

    spec = {  # mu_c, sigma_theta, sigma_d, p, mu_r, sigma_r
        "driver": (215.0, 6.5, 0.07, 0.10, 18.0, 8.0),
        "5h": (172.0, 6.0, 0.065, 0.08, 10.0, 5.0),
        "7i": (140.0, 5.5, 0.06, 0.07, 5.0, 2.5),
        "9i": (118.0, 5.0, 0.06, 0.06, 3.0, 2.0),
        "sw": (86.0, 5.0, 0.07, 0.06, 1.5, 1.5),
    }
    return {k: ClubParams(*v, sampled=True, stats=None) for k, v in spec.items()}


def test_interpolate_clubs_fills_the_bag():
    from caddie.dispersion import CLUB_ORDER, interpolate_clubs

    clubs = interpolate_clubs(_sampled_bag())
    assert list(clubs) == CLUB_ORDER and len(clubs) == 12
    mu = [clubs[c].mu_c for c in CLUB_ORDER]
    assert all(a > b for a, b in zip(mu, mu[1:], strict=False)), mu
    for c, cp in clubs.items():
        for v in (cp.mu_c, cp.sigma_theta_deg, cp.sigma_d, cp.p, cp.mu_r, cp.sigma_r):
            assert np.isfinite(v), c
        assert cp.sampled == (c in _sampled_bag())
        assert cp.stats is None or cp.sampled


def test_interpolate_clubs_ratios_and_partial_wedges():
    from caddie.dispersion import interpolate_clubs

    clubs = interpolate_clubs(_sampled_bag())
    assert clubs["3w"].mu_c == pytest.approx(0.92 * 215.0)
    assert clubs["6i"].mu_c == pytest.approx(1.08 * 140.0)
    assert clubs["pw"].mu_c == pytest.approx(0.90 * 118.0)
    assert clubs["sw70"].mu_c == pytest.approx(0.78 * 86.0)
    assert clubs["sw30"].sigma_theta_deg == pytest.approx(1.2 * 5.0)
    assert clubs["sw30"].sigma_d == pytest.approx(1.2 * 0.07)
    assert clubs["sw30"].mu_r == pytest.approx(1.5)
    # 8i sits between 7i and 9i in mu_c, so its other parameters do too
    assert 5.0 <= clubs["8i"].sigma_theta_deg <= 5.5
    assert 3.0 <= clubs["8i"].mu_r <= 5.0


# slice 7 -------------------------------------------------------------------

CONTRACT_PUTTING = {
    "distance_m": [1, 2, 3, 4, 6, 8, 10, 15, 25],
    "expected_putts": [1.07, 1.41, 1.64, 1.78, 1.85, 1.93, 1.98, 2.15, 2.4],
}


class StubPutting:
    """Stands in for part 03's PuttingTable: only `to_json` is needed here."""

    def to_json(self) -> dict:
        return dict(CONTRACT_PUTTING)


@pytest.fixture(scope="module")
def synthetic_shots_csv(tmp_path_factory):
    rng = np.random.default_rng(9)
    spec = {
        "driver": (100, 215.0, 0.07, 0.10, 6.5, 18.0, 8.0, "tee"),
        "5h": (50, 172.0, 0.065, 0.08, 6.0, 10.0, 5.0, "mat"),
        "7i": (50, 140.0, 0.06, 0.07, 5.5, 5.0, 2.5, "mat"),
        "9i": (50, 118.0, 0.06, 0.06, 5.0, 3.0, 2.0, "mat"),
        "sw": (50, 86.0, 0.07, 0.06, 5.0, 1.5, 1.5, "mat"),
    }
    lines = ["club,carry_m,total_m,lateral_m,lie,date"]
    for club, (n, mu, sd, p, st, mr, sr, lie) in spec.items():
        for row in _synthetic_shots(rng, n, mu, sd, p, st, mr, sr, lie):
            lines.append(
                f"{club},{row['carry_m']:.2f},{row['total_m']:.2f},{row['lateral_m']:.2f},{lie},2026-11-01"
            )
    for row in _synthetic_shots(rng, 20, 140.0 * 0.9, 0.078, 0.07, 7.0, 2.5, 2.0, "rough"):
        lines.append(
            f"7i,{row['carry_m']:.2f},{row['total_m']:.2f},{row['lateral_m']:.2f},rough,2026-11-01"
        )
    path = tmp_path_factory.mktemp("shots") / "shots.csv"
    path.write_text("\n".join(lines) + "\n")
    return path


CLUB_KEYS = {"mu_c", "sigma_theta_deg", "sigma_d", "p", "mu_r", "sigma_r", "sampled", "stats"}
NIG_KEYS = {"m", "kappa", "alpha", "beta"}


def test_player_json_matches_contract(synthetic_shots_csv, tmp_path):
    from caddie.dispersion import CLUB_ORDER, build_player, write_player_json

    player = build_player(synthetic_shots_csv, StubPutting(), handicap=15)
    out = tmp_path / "player.json"
    write_player_json(player, out)
    doc = json.loads(out.read_text())
    assert set(doc) == {"handicap", "clubs", "club_order", "lie", "putting"}
    assert doc["handicap"] == 15
    assert doc["club_order"] == CLUB_ORDER and set(doc["clubs"]) == set(CLUB_ORDER)
    for club, cp in doc["clubs"].items():
        assert set(cp) == CLUB_KEYS, club
        if cp["sampled"]:
            st = cp["stats"]
            assert set(st) == {"n", "carry", "theta", "roll"}
            assert st["n"] in (50, 100)
            assert set(st["carry"]) == NIG_KEYS and set(st["roll"]) == NIG_KEYS
            assert set(st["theta"]) == {"alpha", "beta"}
        else:
            assert cp["stats"] is None
    assert set(doc["lie"]) == {"tee", "fairway", "rough", "bunker"}
    for v in doc["lie"].values():
        assert set(v) == {"carry", "sigma", "roll"}
    assert doc["lie"]["tee"] == doc["lie"]["fairway"] == {"carry": 1.0, "sigma": 1.0, "roll": 1.0}
    assert doc["lie"]["bunker"] == {"carry": 0.8, "sigma": 1.6, "roll": 0.0}
    assert 0.85 <= doc["lie"]["rough"]["carry"] <= 0.95
    assert doc["putting"] == CONTRACT_PUTTING
    # point estimates are consistent with the stored posterior state
    drv = doc["clubs"]["driver"]
    assert drv["mu_c"] == pytest.approx(drv["stats"]["carry"]["m"])
    assert abs(drv["mu_c"] - 215.0) < 5


def test_player_sample_written_to_out(synthetic_shots_csv):
    """The part's Done-when artifact: solver/out/player.sample.json from synthetic data."""
    from caddie.dispersion import build_player, write_player_json

    out = Path(__file__).resolve().parents[1] / "out" / "player.sample.json"
    write_player_json(build_player(synthetic_shots_csv, StubPutting(), 15), out)
    assert json.loads(out.read_text())["clubs"]["7i"]["sampled"] is True


# slice 8 -------------------------------------------------------------------


def test_stats_updates_fixture_is_reproducible(tmp_path):
    from caddie.dispersion import write_stats_updates_fixture

    committed = FIXTURES / "stats_updates.json"
    regenerated = tmp_path / "stats_updates.json"
    write_stats_updates_fixture(regenerated)
    assert json.loads(committed.read_text()) == json.loads(regenerated.read_text())


def test_stats_updates_fixture_shape():
    from caddie.dispersion import IG, NIG, ClubStats, update_club_stats

    doc = json.loads((FIXTURES / "stats_updates.json").read_text())
    assert doc["club"] == "driver" and len(doc["observations"]) == 5
    assert len(doc["after"]) == 5
    s = ClubStats(
        n=doc["prior"]["n"],
        carry=NIG(**doc["prior"]["carry"]),
        theta=IG(**doc["prior"]["theta"]),
        roll=NIG(**doc["prior"]["roll"]),
    )
    for obs, after in zip(doc["observations"], doc["after"], strict=True):
        s = update_club_stats(s, *obs)
        assert s.n == after["n"]
        assert abs(s.carry.m - after["carry"]["m"]) < 1e-9
        assert abs(s.theta.beta - after["theta"]["beta"]) < 1e-9
