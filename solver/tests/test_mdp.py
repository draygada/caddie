"""Tests for caddie.mdp (part 04)."""

import numpy as np
import pytest

from caddie.dispersion import ClubParams
from caddie.mdp import (
    DIRECTIONS_DEG,
    FROM_LIES,
    Draws,
    Lie,
    OffsetTables,
    build_offset_tables,
    landing_offsets,
    make_draws,
)
from tests.fixtures.toy_hole import toy_player

# slice 1: Lie enum, directions, draws


def test_lie_codes_match_contract():
    assert [int(v) for v in Lie] == [0, 1, 2, 3, 4, 5, 6, 7]
    assert Lie.OUT == 0 and Lie.TEE == 1 and Lie.GREEN == 5 and Lie.OB == 7


def test_directions():
    assert DIRECTIONS_DEG.shape == (91,)
    assert DIRECTIONS_DEG[0] == -90 and DIRECTIONS_DEG[-1] == 90 and DIRECTIONS_DEG[45] == 0
    assert np.all(np.diff(DIRECTIONS_DEG) == 2)


def test_make_draws_shapes_and_moments():
    d = make_draws(200)
    assert isinstance(d, Draws)
    for arr in (d.theta, d.z, d.u, d.roll):
        assert arr.shape == (200,)
    for arr in (d.theta, d.roll, d.z):
        assert abs(arr.mean()) < 0.1
        assert abs(arr.std() - 1.0) < 0.1
    assert np.all((d.u >= 0) & (d.u < 1))


def test_mixture_x_has_negative_mean():
    d = make_draws(200)
    x = d.x(0.25)
    assert x.shape == (200,)
    assert x.mean() < 0
    assert d.x(0.0).mean() == pytest.approx(d.z.mean())


def test_make_draws_deterministic_for_seed():
    a, b = make_draws(50, seed=3), make_draws(50, seed=3)
    assert np.array_equal(a.theta, b.theta) and np.array_equal(a.u, b.u)
    assert not np.array_equal(a.theta, make_draws(50, seed=4).theta)


# slice 2: landing offsets

UNIT_LIE = {"carry": 1.0, "sigma": 1.0, "roll": 1.0}


def club(mu_c=25.0, sigma_theta=4.0, sigma_d=0.05, p=0.05, mu_r=2.0, sigma_r=1.0) -> ClubParams:
    return ClubParams(mu_c, sigma_theta, sigma_d, p, mu_r, sigma_r, sampled=True, stats=None)


@pytest.fixture(scope="module")
def draws() -> Draws:
    return make_draws(200)


def test_landing_offsets_degenerate_dir0(draws):
    c = club(sigma_theta=0.0, sigma_d=0.0, sigma_r=0.0)
    dx, dy, roll = landing_offsets(c, UNIT_LIE, draws, 0.0)
    assert dx.shape == dy.shape == roll.shape == (200,)
    assert np.allclose(dx, 0.0) and np.allclose(dy, c.mu_c)
    assert np.allclose(roll, c.mu_r)


def test_landing_offsets_degenerate_dir90(draws):
    c = club(sigma_theta=0.0, sigma_d=0.0)
    dx, dy, _ = landing_offsets(c, UNIT_LIE, draws, 90.0)
    assert np.allclose(dx, c.mu_c) and np.allclose(dy, 0.0, atol=1e-9)


def test_landing_offsets_spread_and_lie_multipliers(draws):
    c = club()
    dx, dy, roll = landing_offsets(c, UNIT_LIE, draws, 0.0)
    carry = np.hypot(dx, dy)
    assert abs(carry.mean() - c.mu_c * (1 - c.p * 2 * c.sigma_d)) < 0.5
    assert dx.std() > 0.5 and dy.std() > 0.5
    rough = {"carry": 0.9, "sigma": 1.3, "roll": 0.5}
    dxr, dyr, rollr = landing_offsets(c, rough, draws, 0.0)
    assert np.hypot(dxr, dyr).mean() < carry.mean()
    assert dxr.std() > dx.std()
    assert np.allclose(rollr, 0.5 * roll)


# slice 3: offset tables


@pytest.fixture(scope="module")
def tables(draws) -> OffsetTables:
    return build_offset_tables(toy_player(), draws)


def test_from_lies_order():
    assert FROM_LIES == (Lie.TEE, Lie.FAIRWAY, Lie.ROUGH, Lie.BUNKER, Lie.GREEN)


def test_offset_tables_shape(tables):
    assert tables.dx.shape == tables.dy.shape == tables.roll.shape == (1, 5, 91, 200)
    assert tables.dx.dtype == np.float64


def test_offset_tables_rough_wider_than_fairway(tables):
    fw = FROM_LIES.index(Lie.FAIRWAY)
    rg = FROM_LIES.index(Lie.ROUGH)
    d0 = 45  # direction 0
    assert tables.dx[0, rg, d0].std() > tables.dx[0, fw, d0].std()
    assert tables.dy[0, rg, d0].mean() < tables.dy[0, fw, d0].mean()
    assert np.allclose(tables.roll[0, FROM_LIES.index(Lie.BUNKER), d0], 0.0)
    assert np.array_equal(tables.dx[0, fw, d0], tables.dx[0, FROM_LIES.index(Lie.TEE), d0])


def test_offset_tables_direction_axis(tables):
    fw = FROM_LIES.index(Lie.FAIRWAY)
    assert tables.dx[0, fw, 0].mean() < -20  # dir -90 is to the left
    assert tables.dx[0, fw, 90].mean() > 20
    assert tables.dy[0, fw, 45].mean() > 20
