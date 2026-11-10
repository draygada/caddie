"""Part 01: hole polygons to a hole-local meters grid with a lie code per cell.

Frame: the Black tee is the projection centre. +y points from the Black tee toward
the pin, +x to the golfer's right. `rotation_deg` is the tee to pin bearing in
degrees clockwise from north. Grid cell (r, c) has its centre at
x = (c + 0.5) * cell_m, y = (r + 0.5) * cell_m, so the grid's lower-left corner
is (0, 0) and the tee sits at `tee_xy` inside the grid.
"""

from __future__ import annotations

import json
import logging
import math
from pathlib import Path

import numpy as np
from pyproj import Transformer
from shapely import contains_xy, union_all
from shapely.geometry import LineString, Point, Polygon, shape
from shapely.geometry.base import BaseGeometry

_WGS84 = "EPSG:4326"


def _aeqd(origin_lon: float, origin_lat: float) -> str:
    return f"+proj=aeqd +lat_0={origin_lat} +lon_0={origin_lon} +datum=WGS84 +units=m +no_defs"


def to_local(lon: float, lat: float, origin_lon: float, origin_lat: float) -> tuple[float, float]:
    """Lon/lat to (east, north) meters in an azimuthal equidistant frame at the origin."""
    t = Transformer.from_crs(_WGS84, _aeqd(origin_lon, origin_lat), always_xy=True)
    east, north = t.transform(lon, lat)
    return float(east), float(north)


def to_lonlat(
    east: float, north: float, origin_lon: float, origin_lat: float
) -> tuple[float, float]:
    """Inverse of `to_local`."""
    t = Transformer.from_crs(_aeqd(origin_lon, origin_lat), _WGS84, always_xy=True)
    lon, lat = t.transform(east, north)
    return float(lon), float(lat)


def rotate(east: float, north: float, rotation_deg: float) -> tuple[float, float]:
    """Rotate (east, north) so the bearing `rotation_deg` (clockwise from north) becomes +y.

    +x is then 90 degrees clockwise of +y, i.e. the golfer's right when facing the pin.
    """
    b = math.radians(rotation_deg)
    x = east * math.cos(b) - north * math.sin(b)
    y = east * math.sin(b) + north * math.cos(b)
    return x, y


def unrotate(x: float, y: float, rotation_deg: float) -> tuple[float, float]:
    """Inverse of `rotate`: grid-aligned (x, y) back to (east, north)."""
    b = math.radians(rotation_deg)
    east = x * math.cos(b) + y * math.sin(b)
    north = -x * math.sin(b) + y * math.cos(b)
    return east, north


def bearing_deg(east: float, north: float) -> float:
    """Bearing of the vector (east, north) in degrees clockwise from north, in [0, 360)."""
    return math.degrees(math.atan2(east, north)) % 360.0


# --- slice 3: feature extraction -------------------------------------------------------

log = logging.getLogger(__name__)

LIE_KINDS: tuple[str, ...] = ("tee", "fairway", "rough", "bunker", "green")
ASSIGN_MAX_M = 60.0
_M_PER_DEG_LAT = 111_320.0


def _deg_to_m(d_deg: float, lat: float) -> float:
    """Rough conversion of a shapely lon/lat distance to meters (fine for 60 m thresholds)."""
    return d_deg * _M_PER_DEG_LAT * math.cos(math.radians(lat))


def load_osm(path: Path) -> dict:
    with Path(path).open() as f:
        return json.load(f)


def hole_centerlines(osm: dict) -> dict[int, LineString]:
    """Hole number -> `golf=hole` centerline, tee end first."""
    out: dict[int, LineString] = {}
    for f in osm["features"]:
        p = f["properties"]
        if p.get("golf") == "hole" and "ref" in p:
            g = shape(f["geometry"])
            if isinstance(g, LineString):
                out[int(p["ref"])] = g
    return out


def _polygons_of(geom: BaseGeometry) -> list[Polygon]:
    if isinstance(geom, Polygon):
        return [geom] if geom.is_valid else [geom.buffer(0)]
    if geom.geom_type == "MultiPolygon":
        return [p for part in geom.geoms for p in _polygons_of(part)]
    return []


def _assign_hole(poly: Polygon, lines: dict[int, LineString]) -> int | None:
    """Nearest `golf=hole` centerline within ASSIGN_MAX_M, else None."""
    lat = poly.centroid.y
    best, best_m = None, math.inf
    for hole, line in lines.items():
        d = _deg_to_m(poly.distance(line), lat)
        if d < best_m:
            best, best_m = hole, d
    return best if best_m <= ASSIGN_MAX_M else None


def extract_hole_features(osm: dict, hole_number: int) -> dict[str, list[Polygon]]:
    """Golf polygons belonging to one hole, as shapely Polygons in lon/lat.

    Tagged polygons (`ref=<n>`) go to hole n. Untagged ones (the whole back nine in
    OSM) go to the hole whose centerline is nearest, within 60 m. If more than one
    green lands on a hole, the one nearest the centerline's pin end is kept and the
    others are logged and dropped (practice greens and neighbours' greens).
    """
    lines = hole_centerlines(osm)
    if hole_number not in lines:
        raise ValueError(f"no golf=hole centerline with ref={hole_number}")
    feats: dict[str, list[Polygon]] = {k: [] for k in LIE_KINDS}
    for f in osm["features"]:
        kind = f["properties"].get("golf")
        if kind not in LIE_KINDS:
            continue
        for poly in _polygons_of(shape(f["geometry"])):
            ref = f["properties"].get("ref")
            if ref is not None and str(ref).isdigit():
                assigned: int | None = int(ref)
            else:
                assigned = _assign_hole(poly, lines)
            if assigned == hole_number:
                feats[kind].append(poly)
    if len(feats["green"]) > 1:
        end = Point(lines[hole_number].coords[-1])
        feats["green"].sort(key=lambda g: g.distance(end))
        log.warning(
            "hole %d: %d greens assigned, keeping the one nearest the centerline end",
            hole_number,
            len(feats["green"]),
        )
        feats["green"] = feats["green"][:1]
    return feats


# --- slice 4: rasterize --------------------------------------------------------------

# Lie codes per the root data contract. Part 04 wraps these in the `Lie` IntEnum;
# geometry.py cannot import a later part, so the raw table lives here.
LIE_CODE: dict[str, int] = {
    "out": 0,
    "tee": 1,
    "fairway": 2,
    "rough": 3,
    "bunker": 4,
    "green": 5,
    "water": 6,
    "ob": 7,
}

# Lowest priority first: a later kind overwrites an earlier one where polygons overlap.
RASTER_PRIORITY: tuple[str, ...] = ("rough", "fairway", "tee", "green", "bunker", "ob", "water")


def cell_centres(rows: int, cols: int, cell_m: float) -> tuple[np.ndarray, np.ndarray]:
    """(x, y) arrays of shape (rows, cols) with the centre of every cell."""
    xs = (np.arange(cols) + 0.5) * cell_m
    ys = (np.arange(rows) + 0.5) * cell_m
    x, y = np.meshgrid(xs, ys)
    return x, y


def rasterize(
    polys_xy: dict[str, list[Polygon]],
    rows: int,
    cols: int,
    cell_m: float,
    margin_m: float = 40.0,
) -> np.ndarray:
    """uint8 (rows, cols) lie grid from polygons in grid meters.

    A cell takes the code of the highest-priority polygon covering its centre
    (water > ob > bunker > green > tee > fairway > rough). Cells inside the union of
    all polygons buffered by `margin_m` but covered by nothing are rough; cells
    outside that corridor are 0 (out of grid).
    """
    x, y = cell_centres(rows, cols, cell_m)
    lie = np.zeros((rows, cols), dtype=np.uint8)
    everything = [p for polys in polys_xy.values() for p in polys]
    if everything:
        corridor = union_all(everything).buffer(margin_m)
        inside = contains_xy(corridor, x, y)
        lie[inside] = LIE_CODE["rough"]
    for kind in RASTER_PRIORITY:
        polys = polys_xy.get(kind, [])
        if not polys:
            continue
        covered = contains_xy(union_all(polys), x, y)
        lie[covered] = LIE_CODE[kind]
    return lie


# --- slice 5: drop index -------------------------------------------------------------


def compute_drop_index(
    lie: np.ndarray, tee_xy: tuple[float, float], cell_m: float
) -> np.ndarray:
    """int32 (rows, cols): for each water cell, the flat index of its drop cell; -1 elsewhere.

    The drop cell is the nearest fairway or rough cell (Euclidean, cell centres) whose
    y is at or below the water cell's y, i.e. on the tee side. `tee_xy` is accepted for
    interface stability; with +y pointing at the pin the tee side is simply lower y.
    """
    rows, cols = lie.shape
    drop = np.full((rows, cols), -1, dtype=np.int32)
    water_r, water_c = np.nonzero(lie == LIE_CODE["water"])
    if water_r.size == 0:
        return drop
    land_mask = (lie == LIE_CODE["fairway"]) | (lie == LIE_CODE["rough"])
    land_r, land_c = np.nonzero(land_mask)
    if land_r.size == 0:
        raise ValueError("no fairway or rough cell available for a drop")
    for r, c in zip(water_r, water_c, strict=True):
        ok = land_r <= r
        if not np.any(ok):
            raise ValueError(f"water cell ({r}, {c}) has no tee-side fairway or rough cell")
        d2 = (land_r[ok] - r) ** 2 + (land_c[ok] - c) ** 2
        k = int(np.argmin(d2))
        drop[r, c] = int(land_r[ok][k]) * cols + int(land_c[ok][k])
    return drop
