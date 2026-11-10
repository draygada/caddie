"""Part 01: hole polygons to a hole-local meters grid with a lie code per cell.

Frame: the Black tee is the projection centre. +y points from the Black tee toward
the pin, +x to the golfer's right. `rotation_deg` is the tee to pin bearing in
degrees clockwise from north. Grid cell (r, c) has its centre at
x = (c + 0.5) * cell_m, y = (r + 0.5) * cell_m, so the grid's lower-left corner
is (0, 0) and the tee sits at `tee_xy` inside the grid.
"""

from __future__ import annotations

import math

from pyproj import Transformer

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
