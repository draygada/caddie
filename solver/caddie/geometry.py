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

from pyproj import Transformer
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
