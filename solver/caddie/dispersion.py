"""Part 02: per-club shot distributions from simulator data, and player.json.

Model per club, independent components:
  direction  theta ~ N(0, sigma_theta^2) degrees, positive = golfer's right
  carry      c = mu_c (1 + sigma_d X),  X ~ (1 - p) N(0, 1) + p N(-2, 1)
  roll       r = total - carry ~ N(mu_r, sigma_r^2)

Carry, direction and roll are fit by conjugate Bayesian updating from a skill-band
prior (textbook Ch 4.2); the mishit rate p by maximum likelihood (Ch 4.1) with the
other carry parameters held at their posterior means.
"""

from __future__ import annotations

import csv
import logging
from pathlib import Path

import numpy as np

log = logging.getLogger(__name__)

SHOTS_COLUMNS: tuple[str, ...] = ("club", "carry_m", "total_m", "lateral_m", "lie", "date")
SHOT_DTYPE = np.dtype(
    [("carry_m", "f8"), ("total_m", "f8"), ("lateral_m", "f8"), ("lie", "U8"), ("date", "U10")]
)


# --- slice 1: loader -----------------------------------------------------------------


def load_shots(path: Path) -> dict[str, np.ndarray]:
    """Canonical shots CSV -> club -> structured array (carry_m, total_m, lateral_m, lie, date)."""
    rows: dict[str, list[tuple]] = {}
    with Path(path).open(newline="") as f:
        reader = csv.reader(f)
        header = next(reader, None)
        if header is None or tuple(h.strip() for h in header) != SHOTS_COLUMNS:
            raise ValueError(f"{path}: header must be {','.join(SHOTS_COLUMNS)}, got {header}")
        for line in reader:
            if not line or not any(line):
                continue
            club, carry, total, lateral, lie, date = (v.strip() for v in line)
            rows.setdefault(club, []).append(
                (float(carry), float(total), float(lateral), lie, date)
            )
    return {club: np.array(r, dtype=SHOT_DTYPE) for club, r in rows.items()}
