"""Tests for part 06: online.py (bilinear leaf values, rollout recommend, sequences)."""

from __future__ import annotations

import numpy as np

from caddie.online import bilinear

# --- slice 1: bilinear --------------------------------------------------------------------------


def _y_field(rows: int, cols: int, cell_m: float) -> np.ndarray:
    r = np.arange(rows)
    return np.repeat((r + 0.5) * cell_m, cols).astype(np.float32)


def test_bilinear_reproduces_a_field_equal_to_y():
    U = _y_field(3, 3, 5.0)
    x = np.array([2.5, 7.5, 12.5, 4.0, 9.9, 0.0, 15.0])
    y = np.array([2.5, 12.5, 7.5, 6.6, 3.3, 10.0, 12.5])
    np.testing.assert_allclose(bilinear(U, 3, 3, 5.0, x, y), y, atol=1e-6)


def test_bilinear_clamps_beyond_the_outer_centres():
    U = _y_field(3, 3, 5.0)
    out = bilinear(U, 3, 3, 5.0, np.array([7.5, 7.5, -4.0, 40.0]), np.array([0.0, 15.0, 7.5, 7.5]))
    np.testing.assert_allclose(out, [2.5, 12.5, 7.5, 7.5], atol=1e-6)


def test_bilinear_scalar_inputs():
    U = _y_field(3, 3, 5.0)
    assert float(bilinear(U, 3, 3, 5.0, 7.5, 9.0)) == 9.0


def test_bilinear_nan_corner_uses_nearest_finite_of_the_four():
    U = _y_field(3, 3, 5.0)
    U[0] = np.nan  # cell (0, 0)
    v = float(bilinear(U, 3, 3, 5.0, 3.0, 3.0))
    assert np.isfinite(v) and 2.5 <= v <= 7.5
    # a point nearer to the NaN cell than any finite cell still gets a finite value
    assert np.isfinite(float(bilinear(U, 3, 3, 5.0, 0.1, 0.1)))


def test_bilinear_all_nan_neighbours_returns_nearest_finite_plus_one():
    U = _y_field(4, 4, 5.0)
    U[[0, 1, 4, 5]] = np.nan  # the 2 x 2 block at the origin is OUT
    v = float(bilinear(U, 4, 4, 5.0, 5.0, 5.0))  # centre of that block
    # nearest finite cells are (0, 2) at 12.5 m and (2, 0) at 12.5 m, values 2.5 and 12.5
    assert v in (2.5 + 1.0, 12.5 + 1.0)
