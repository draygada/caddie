"""Tests for part 08: export.py (bundle round trip) and cli.py."""

from __future__ import annotations

import json
import logging
import struct
from pathlib import Path

import numpy as np
import pytest

from caddie.cli import main
from caddie.dispersion import player_to_json
from caddie.export import player_from_json, read_bundle, write_bundle, write_player
from caddie.mdp import DIRECTIONS_DEG
from caddie.value_iteration import solve
from tests.fixtures.toy_hole import toy_hole, toy_player

META_KEYS = {
    "hole",
    "par",
    "penalty_mode",
    "rows",
    "cols",
    "cell_m",
    "origin",
    "rotation_deg",
    "tee_xy",
    "pin_xy",
    "tees",
    "clubs",
    "directions_deg",
    "polygons",
}
POLYGON_KEYS = {"fairway", "green", "bunker", "water", "ob", "tee", "rough"}
BUNDLE_FILES = ("meta.json", "lie.u8", "value.f32", "club.u8", "dir.u8")
SOLVER_DIR = Path(__file__).resolve().parents[1]


@pytest.fixture(scope="module")
def toy_solution():
    hole = toy_hole()
    player = toy_player()
    return solve(hole, player, "drop", K=200, tol=0.01, max_sweeps=50), hole, player


# --- slice 1: write_bundle round trip -------------------------------------------------------


def test_write_bundle_creates_five_files(toy_solution, tmp_path):
    solution, hole, player = toy_solution
    write_bundle(solution, hole, player, tmp_path)
    bundle_dir = tmp_path / "0" / "drop"
    assert sorted(p.name for p in bundle_dir.iterdir()) == sorted(BUNDLE_FILES)


def test_round_trip_arrays_equal(toy_solution, tmp_path):
    solution, hole, player = toy_solution
    write_bundle(solution, hole, player, tmp_path)
    meta, lie, value, club, direction = read_bundle(tmp_path / "0" / "drop")
    assert lie.shape == value.shape == club.shape == direction.shape == (hole.rows, hole.cols)
    assert lie.dtype == np.uint8 and club.dtype == np.uint8 and direction.dtype == np.uint8
    assert value.dtype == np.float32
    np.testing.assert_array_equal(lie, hole.lie)
    np.testing.assert_array_equal(value.ravel(), solution.U)
    np.testing.assert_array_equal(club.ravel(), solution.club)
    np.testing.assert_array_equal(direction.ravel(), solution.dir)


def test_meta_has_every_contract_key(toy_solution, tmp_path):
    solution, hole, player = toy_solution
    write_bundle(solution, hole, player, tmp_path)
    meta = json.loads((tmp_path / "0" / "drop" / "meta.json").read_text())
    assert set(meta) == META_KEYS
    assert meta["hole"] == 0 and meta["par"] == 3 and meta["penalty_mode"] == "drop"
    assert (meta["rows"], meta["cols"], meta["cell_m"]) == (hole.rows, hole.cols, hole.cell_m)
    assert set(meta["origin"]) == {"lat", "lon"}
    assert meta["tee_xy"] == list(hole.tee_xy) and meta["pin_xy"] == list(hole.pin_xy)
    assert meta["tees"] == {"black": list(hole.tee_xy)}
    assert meta["clubs"] == player.club_order
    assert len(meta["directions_deg"]) == 91
    assert meta["directions_deg"] == [int(d) for d in DIRECTIONS_DEG]
    assert set(meta["polygons"]) == POLYGON_KEYS
    assert all(isinstance(v, list) for v in meta["polygons"].values())


def test_meta_polygons_are_simplified_rings(toy_solution, tmp_path):
    """A wiggly ring in grid meters comes out simplified (tolerance 1.0 m) and closed."""
    solution, hole, player = toy_solution
    ring = [(0.0, 0.0), (10.0, 0.2), (20.0, 0.0), (20.0, 10.0), (0.0, 10.0), (0.0, 0.0)]
    hole.polygons_xy = {"fairway": [ring]}
    try:
        write_bundle(solution, hole, player, tmp_path)
    finally:
        hole.polygons_xy = {}
    meta = json.loads((tmp_path / "0" / "drop" / "meta.json").read_text())
    (out,) = meta["polygons"]["fairway"]
    assert out[0] == out[-1]
    assert len(out) == 5  # the 0.2 m wiggle is gone
    assert all(len(pt) == 2 for pt in out)


def test_write_player_matches_player_json(toy_solution, tmp_path):
    _, _, player = toy_solution
    write_player(player, tmp_path)
    doc = json.loads((tmp_path / "player.json").read_text())
    assert set(doc) == {"handicap", "clubs", "club_order", "lie", "putting"}
    assert doc["club_order"] == player.club_order
    assert doc["putting"] == player.putting.to_json()


# --- slice 2: byte layout -------------------------------------------------------------------


def test_value_f32_byte_layout(toy_solution, tmp_path):
    solution, hole, player = toy_solution
    write_bundle(solution, hole, player, tmp_path)
    d = tmp_path / "0" / "drop"
    n = hole.rows * hole.cols
    assert (d / "value.f32").stat().st_size == n * 4
    for name in ("lie.u8", "club.u8", "dir.u8"):
        assert (d / name).stat().st_size == n
    raw = (d / "value.f32").read_bytes()
    first = struct.unpack("<f", raw[:4])[0]
    assert first == solution.U[0]  # cell (0, 0) is fairway on the toy, so finite
    # the tee cell is playable, so its float is finite and equals U at that index
    tee = int(hole.tee_xy[1] // hole.cell_m) * hole.cols + int(hole.tee_xy[0] // hole.cell_m)
    tee_val = struct.unpack("<f", raw[4 * tee : 4 * tee + 4])[0]
    assert np.isfinite(tee_val) and tee_val == solution.U[tee]
    # last cell in row-major order is (rows - 1, cols - 1): OB on the toy, so NaN
    last = struct.unpack("<f", raw[-4:])[0]
    assert np.isnan(last) and hole.lie[-1, -1] == 7


# --- slice 3: CLI ---------------------------------------------------------------------------


def test_write_bundle_label_names_the_toy_dir(toy_solution, tmp_path):
    solution, hole, player = toy_solution
    write_bundle(solution, hole, player, tmp_path, label="toy")
    meta, *_ = read_bundle(tmp_path / "toy" / "drop")
    assert meta["hole"] == "toy"


def test_cli_solve_missing_player_exits_1(tmp_path, caplog):
    caplog.set_level(logging.ERROR)
    missing = tmp_path / "nope.json"
    code = main(["solve", "10", "--mode", "drop", "--player", str(missing), "--out", str(tmp_path)])
    assert code == 1
    assert any(str(missing) in r.message for r in caplog.records)
    assert not (tmp_path / "10").exists()


def test_cli_hole_toy_writes_lie_png(tmp_path):
    assert main(["hole", "toy", "--out", str(tmp_path)]) == 0
    png = tmp_path / "toy_lie.png"
    assert png.exists() and png.stat().st_size > 1000


def test_cli_solve_toy_logs_every_5_sweeps_and_writes_bundle(tmp_path, caplog):
    caplog.set_level(logging.INFO, logger="caddie.value_iteration")
    code = main(["solve", "toy", "--mode", "replay", "--out", str(tmp_path)])
    assert code == 0
    sweeps_logged = [
        int(r.message.split("sweep ")[1].split()[0])
        for r in caplog.records
        if r.name == "caddie.value_iteration" and "sweep" in r.message
    ]
    assert {5, 10} <= set(sweeps_logged)
    assert all(s % 5 == 0 for s in sweeps_logged[:-1])  # only the final sweep may be off-cycle
    meta, lie, value, club, direction = read_bundle(tmp_path / "toy" / "replay")
    assert meta["penalty_mode"] == "replay" and meta["hole"] == "toy"
    assert (tmp_path / "toy_replay_value.png").exists()


def test_cli_fit_writes_player_json(tmp_path):
    code = main(
        [
            "fit",
            "--shots",
            str(SOLVER_DIR / "tests" / "fixtures" / "shots_fixture.csv"),
            "--putting",
            str(SOLVER_DIR / "data" / "raw" / "putting.csv"),
            "--handicap",
            "15",
            "--out",
            str(tmp_path),
        ]
    )
    assert code == 0
    doc = json.loads((tmp_path / "player.json").read_text())
    assert doc["handicap"] == 15 and len(doc["club_order"]) == 12
    player = player_from_json(doc)
    assert player.clubs["driver"].stats is not None
    assert player_to_json(player) == doc  # full round trip, stats included


def test_cli_export_solves_when_bundle_missing(tmp_path):
    code = main(["export", "toy", "--mode", "drop", "--out", str(tmp_path)])
    assert code == 0
    assert all((tmp_path / "toy" / "drop" / f).exists() for f in BUNDLE_FILES)
