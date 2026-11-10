"""Part 08: write the data bundle the app consumes, exactly per the root contract.

``out_dir/<hole>/<mode>/{meta.json, lie.u8, value.f32, club.u8, dir.u8}`` plus
``out_dir/player.json``. Binary files are row-major ``rows x cols`` little-endian.
``value.f32`` holds strokes-to-go as a positive float32 with NaN where there is no
state (out-of-grid, water, OB).
"""

from __future__ import annotations

import json
import logging
import shutil
from pathlib import Path

import numpy as np
from shapely.geometry import Polygon

from caddie.dispersion import IG, NIG, ClubParams, ClubStats, Player, player_to_json
from caddie.geometry import Hole
from caddie.mdp import DIRECTIONS_DEG
from caddie.putting import PuttingTable
from caddie.value_iteration import Solution

log = logging.getLogger(__name__)

POLYGON_KINDS: tuple[str, ...] = ("fairway", "green", "bunker", "water", "ob", "tee", "rough")
POLYGON_SIMPLIFY_M = 1.0
BUNDLE_FILES: tuple[str, ...] = ("meta.json", "lie.u8", "value.f32", "club.u8", "dir.u8")


def bundle_dir(out_dir: Path, hole: int | str, mode: str) -> Path:
    return Path(out_dir) / str(hole) / mode


def _simplify_ring(ring: list[tuple[float, float]]) -> list[list[float]]:
    poly = Polygon(ring).simplify(POLYGON_SIMPLIFY_M, preserve_topology=True)
    return [[round(float(x), 2), round(float(y), 2)] for x, y in poly.exterior.coords]


def meta_dict(solution: Solution, hole: Hole, player: Player) -> dict:
    polygons = {
        kind: [_simplify_ring(r) for r in hole.polygons_xy.get(kind, [])] for kind in POLYGON_KINDS
    }
    return {
        "hole": hole.number,
        "par": hole.par,
        "penalty_mode": solution.mode,
        "rows": hole.rows,
        "cols": hole.cols,
        "cell_m": hole.cell_m,
        "origin": {"lat": hole.origin_lat, "lon": hole.origin_lon},
        "rotation_deg": hole.rotation_deg,
        "tee_xy": [float(hole.tee_xy[0]), float(hole.tee_xy[1])],
        "pin_xy": [float(hole.pin_xy[0]), float(hole.pin_xy[1])],
        "tees": {k: [float(v[0]), float(v[1])] for k, v in hole.tees.items()},
        "clubs": list(player.club_order),
        "directions_deg": [int(d) for d in DIRECTIONS_DEG],
        "polygons": polygons,
    }


def write_bundle(solution: Solution, hole: Hole, player: Player, out_dir: Path) -> None:
    """Write ``out_dir/<hole>/<mode>/`` with the five contract files."""
    n = hole.rows * hole.cols
    for name, arr in (("U", solution.U), ("club", solution.club), ("dir", solution.dir)):
        if arr.shape != (n,):
            raise ValueError(f"solution.{name} has shape {arr.shape}, expected ({n},)")
    d = bundle_dir(out_dir, hole.number, solution.mode)
    d.mkdir(parents=True, exist_ok=True)
    (d / "meta.json").write_text(json.dumps(meta_dict(solution, hole, player), indent=1) + "\n")
    (d / "lie.u8").write_bytes(np.ascontiguousarray(hole.lie, dtype=np.uint8).tobytes())
    (d / "value.f32").write_bytes(np.ascontiguousarray(solution.U, dtype="<f4").tobytes())
    (d / "club.u8").write_bytes(np.ascontiguousarray(solution.club, dtype=np.uint8).tobytes())
    (d / "dir.u8").write_bytes(np.ascontiguousarray(solution.dir, dtype=np.uint8).tobytes())
    log.info("wrote bundle %s", d)


def read_bundle(dir: Path) -> tuple[dict, np.ndarray, np.ndarray, np.ndarray, np.ndarray]:
    """Read a bundle back as ``(meta, lie, value, club, dir)``, arrays shaped (rows, cols)."""
    d = Path(dir)
    meta = json.loads((d / "meta.json").read_text())
    shape = (meta["rows"], meta["cols"])
    lie = np.frombuffer((d / "lie.u8").read_bytes(), dtype=np.uint8).reshape(shape)
    value = np.frombuffer((d / "value.f32").read_bytes(), dtype="<f4").reshape(shape)
    club = np.frombuffer((d / "club.u8").read_bytes(), dtype=np.uint8).reshape(shape)
    direction = np.frombuffer((d / "dir.u8").read_bytes(), dtype=np.uint8).reshape(shape)
    return meta, lie, value.astype(np.float32), club, direction


def write_player(player: Player, out_dir: Path) -> None:
    """Write ``out_dir/player.json`` per the root contract."""
    out_dir = Path(out_dir)
    out_dir.mkdir(parents=True, exist_ok=True)
    (out_dir / "player.json").write_text(json.dumps(player_to_json(player), indent=2) + "\n")
    log.info("wrote %s", out_dir / "player.json")


def _stats_from_json(doc: dict | None) -> ClubStats | None:
    if doc is None:
        return None
    return ClubStats(
        n=int(doc["n"]),
        carry=NIG(**doc["carry"]),
        theta=IG(**doc["theta"]),
        roll=NIG(**doc["roll"]),
    )


def player_from_json(doc: dict) -> Player:
    """Inverse of :func:`caddie.dispersion.player_to_json`, including ``stats``."""
    clubs = {
        name: ClubParams(
            mu_c=float(v["mu_c"]),
            sigma_theta_deg=float(v["sigma_theta_deg"]),
            sigma_d=float(v["sigma_d"]),
            p=float(v["p"]),
            mu_r=float(v["mu_r"]),
            sigma_r=float(v["sigma_r"]),
            sampled=bool(v["sampled"]),
            stats=_stats_from_json(v.get("stats")),
        )
        for name, v in doc["clubs"].items()
    }
    putting = PuttingTable(
        distance_m=np.asarray(doc["putting"]["distance_m"], dtype=float),
        expected_putts=np.asarray(doc["putting"]["expected_putts"], dtype=float),
    )
    return Player(
        handicap=int(doc["handicap"]),
        clubs=clubs,
        club_order=list(doc["club_order"]),
        lie={k: {kk: float(vv) for kk, vv in v.items()} for k, v in doc["lie"].items()},
        putting=putting,
    )


def read_player(path: Path) -> Player:
    return player_from_json(json.loads(Path(path).read_text()))


def copy_to_app(out_dir: Path, app_data_dir: Path = Path("../app/public/data")) -> None:
    """Copy ``player.json`` and every ``<hole>/<mode>/`` bundle under ``out_dir`` to the app."""
    out_dir, app_data_dir = Path(out_dir), Path(app_data_dir)
    app_data_dir.mkdir(parents=True, exist_ok=True)
    copied = 0
    if (out_dir / "player.json").exists():
        shutil.copy2(out_dir / "player.json", app_data_dir / "player.json")
        copied += 1
    for meta in sorted(out_dir.glob("*/*/meta.json")):
        src = meta.parent
        dst = app_data_dir / src.relative_to(out_dir)
        dst.mkdir(parents=True, exist_ok=True)
        for name in BUNDLE_FILES:
            shutil.copy2(src / name, dst / name)
            copied += 1
    log.info("copied %d files to %s", copied, app_data_dir)
