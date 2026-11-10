"""Part 03: expected putts as a function of distance to the pin.

A Shot Scope make-rate table (one row per distance bin, feet) is turned into
``E[putts](d)`` by iterating the one-step recursion

    E[putts](d) = make(d) + (1 - make(d)) * (1 + E[putts](leave(d)))

to a fixed point on a 0.25 m grid. Green cells use ``-E[putts]`` as their
terminal value in the MDP.
"""

from __future__ import annotations

import csv
import logging
from pathlib import Path

import numpy as np

log = logging.getLogger(__name__)

FT_TO_M = 0.3048
MAKE_COLUMNS = ("distance_ft_lo", "distance_ft_hi", "make_pct")


def load_make_table(path: Path) -> tuple[np.ndarray, np.ndarray]:
    """Read ``putting.csv``; return bin midpoints in meters and make probabilities.

    Rows are sorted by midpoint. Percentages in the file become probabilities.
    """
    with Path(path).open(newline="") as fh:
        reader = csv.reader(fh)
        header = tuple(h.strip() for h in next(reader))
        if header != MAKE_COLUMNS:
            raise ValueError(f"putting.csv header must be {MAKE_COLUMNS}, got {header}")
        rows = [tuple(float(v) for v in row) for row in reader if row]
    if not rows:
        raise ValueError(f"putting.csv at {path} has no data rows")
    arr = np.asarray(rows, dtype=float)
    lo_ft, hi_ft, pct = arr[:, 0], arr[:, 1], arr[:, 2]
    if np.any(hi_ft <= lo_ft):
        raise ValueError("each putting bin needs distance_ft_hi > distance_ft_lo")
    mids_m = 0.5 * (lo_ft + hi_ft) * FT_TO_M
    probs = pct / 100.0
    order = np.argsort(mids_m)
    log.info("loaded %d putting bins from %s", len(rows), path)
    return mids_m[order], probs[order]


def make_prob(d_m: float | np.ndarray, mids_m: np.ndarray, probs: np.ndarray) -> np.ndarray:
    """Make probability at distance ``d_m`` (meters).

    Linear interpolation through (0, 1.0) and the bin midpoints; clamped at
    the last bin's probability beyond the last midpoint. Negative distances
    are treated as 0.
    """
    xs = np.concatenate(([0.0], np.asarray(mids_m, dtype=float)))
    ys = np.concatenate(([1.0], np.asarray(probs, dtype=float)))
    d = np.maximum(np.asarray(d_m, dtype=float), 0.0)
    return np.interp(d, xs, ys)
