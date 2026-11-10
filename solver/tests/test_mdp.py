"""Tests for caddie.mdp (part 04)."""

import numpy as np
import pytest

from caddie.mdp import DIRECTIONS_DEG, Draws, Lie, make_draws

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
