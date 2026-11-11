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
from dataclasses import dataclass, field
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
    corridor: BaseGeometry | None = None,
) -> np.ndarray:
    """uint8 (rows, cols) lie grid from polygons in grid meters.

    A cell takes the code of the highest-priority polygon covering its centre
    (water > ob > bunker > green > tee > fairway > rough). Cells inside the union of
    all polygons buffered by `margin_m` but covered by nothing are rough; cells
    outside that corridor are 0 (out of grid). `corridor` replaces the buffered union
    when given (build_hole adds the hole centerline so a gap between tee boxes and
    the first fairway polygon does not become out of bounds).
    """
    x, y = cell_centres(rows, cols, cell_m)
    lie = np.zeros((rows, cols), dtype=np.uint8)
    everything = [p for polys in polys_xy.values() for p in polys]
    if corridor is None and everything:
        corridor = union_all(everything).buffer(margin_m)
    if corridor is not None:
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


def compute_drop_index(lie: np.ndarray, tee_xy: tuple[float, float], cell_m: float) -> np.ndarray:
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


# --- slice 6: build_hole and GeoJSON merge ---------------------------------------------

TEE_NAMES: tuple[str, ...] = ("black", "white", "blue", "cardinal", "red", "gold")
_M_PER_YD = 0.9144


@dataclass
class Hole:
    number: int
    par: int
    cell_m: float
    rows: int
    cols: int
    origin_lat: float  # lon/lat of the grid's (0, 0) corner, see module docstring
    origin_lon: float
    rotation_deg: float  # bearing Black tee -> pin, degrees clockwise from north
    tee_xy: tuple[float, float]  # Black tee, grid meters
    tees: dict[str, tuple[float, float]]
    pin_xy: tuple[float, float]
    lie: np.ndarray  # uint8 (rows, cols)
    drop_index: np.ndarray  # int32 (rows, cols)
    polygons_xy: dict[str, list[list[tuple[float, float]]]] = field(default_factory=dict)


@dataclass
class Traced:
    """Hand-traced additions for one hole, in lon/lat."""

    water: list[Polygon] = field(default_factory=list)
    ob: list[Polygon] = field(default_factory=list)
    pin: list[Point] = field(default_factory=list)
    tee: list[tuple[str | None, Polygon]] = field(default_factory=list)  # (colour, polygon)


def load_traced(path: Path) -> Traced:
    """Read `traced_<hole>.geojson`.

    Each feature carries a `kind` property (water, ob, pin, or tee). A tee feature may
    also carry a `tee` property with its colour name. Returns an empty `Traced` when the
    file does not exist, after logging a warning.
    """
    out = Traced()
    path = Path(path)
    if not path.exists():
        log.warning("no traced file %s: water and OB are empty, pin = green centroid", path)
        return out
    with path.open() as f:
        gj = json.load(f)
    for feat in gj["features"]:
        kind = feat["properties"].get("kind")
        geom = shape(feat["geometry"])
        if kind == "pin" and isinstance(geom, Point):
            out.pin.append(geom)
        elif kind in ("water", "ob") and isinstance(geom, Polygon):
            getattr(out, kind).append(geom)
        elif kind == "tee" and isinstance(geom, Polygon):
            out.tee.append((feat["properties"].get("tee"), geom))
        else:
            log.warning("%s: skipping feature kind=%r type=%s", path.name, kind, geom.geom_type)
    return out


def _hole_tags(osm: dict, hole_number: int) -> dict:
    for f in osm["features"]:
        p = f["properties"]
        if p.get("golf") == "hole" and p.get("ref") == str(hole_number):
            return p
    raise ValueError(f"no golf=hole centerline with ref={hole_number}")


def label_tees(
    tee_polys: list[Polygon], pin: Point, tags: dict, to_xy
) -> dict[str, tuple[float, float]]:
    """Name tee polygons by matching their distance to the pin against the `dist:*` tags.

    OSM back-nine tees carry no colour tag. Each polygon's centroid distance to the
    pin (yards) is matched to the closest `dist:<colour>` yardage on the centerline;
    without those tags, polygons are named longest first in TEE_NAMES order.
    """
    cents = [p.centroid for p in tee_polys]
    xy = [to_xy(c.x, c.y) for c in cents]
    pin_xy = to_xy(pin.x, pin.y)
    dist_yd = [math.hypot(x - pin_xy[0], y - pin_xy[1]) / _M_PER_YD for x, y in xy]
    tagged = {
        k.split(":", 1)[1]: float(v)
        for k, v in tags.items()
        if k.startswith("dist:") and str(v).replace(".", "", 1).isdigit()
    }
    tees: dict[str, tuple[float, float]] = {}
    order = sorted(range(len(xy)), key=lambda i: -dist_yd[i])
    if tagged:
        remaining = dict(tagged)
        for i in order:
            if not remaining:
                break
            name = min(remaining, key=lambda n: abs(remaining[n] - dist_yd[i]))
            tees[name] = xy[i]
            del remaining[name]
    else:
        for name, i in zip(TEE_NAMES, order, strict=False):
            tees[name] = xy[i]
    if xy:
        # The frame is anchored at the longest tee box, which is "black" by convention
        # (also kept under its matched colour, e.g. cardinal, when that differs).
        tees["black"] = xy[order[0]]
    unlabelled = len(xy) - len({v for v in tees.values()})
    if unlabelled > 0:
        log.info("%d tee polygon(s) matched no dist tag and were left unnamed", unlabelled)
    return tees


def _ring_xy(poly: Polygon, to_xy) -> list[tuple[float, float]]:
    return [to_xy(x, y) for x, y in poly.exterior.coords]


def _ring_lonlat(ring: list[tuple[float, float]], rot: float, olon: float, olat: float):
    return [list(to_lonlat(*unrotate(x, y, rot), olon, olat)) for x, y in ring]


def build_hole(
    hole_number: int,
    osm_path: Path,
    traced_path: Path,
    cell_m: float = 5.0,
    margin_m: float = 40.0,
    holes_dir: Path = Path("data/holes"),
    out_dir: Path = Path("out"),
) -> Hole:
    """Assemble a `Hole` and write `<holes_dir>/<n>.geojson` and `<out_dir>/<n>_lie.png`.

    Frame: AEQD centred at the Black tee, rotated so tee -> pin is +y, then translated so
    the grid's lower-left corner (bbox of all polygons plus margin, snapped to cell_m) is
    (0, 0). `origin_lat/lon` is that corner, so the root contract's grid-to-lat/lon formula
    applies to grid coordinates directly.
    """
    osm = load_osm(osm_path)
    tags = _hole_tags(osm, hole_number)
    feats = extract_hole_features(osm, hole_number)
    traced = load_traced(traced_path)

    green = feats["green"][0]
    pin_ll: Point = traced.pin[0] if traced.pin else green.centroid
    if not traced.pin:
        log.info("hole %d: pin set to the green centroid", hole_number)

    # Black tee = tee polygon farthest from the pin (dist tags are checked in label_tees).
    tee_polys = list(feats["tee"]) + [poly for _, poly in traced.tee]
    if not tee_polys:
        raise ValueError(f"hole {hole_number}: no tee polygon found")
    black = max(tee_polys, key=lambda p: p.centroid.distance(pin_ll))
    o_lon, o_lat = black.centroid.x, black.centroid.y
    east, north = to_local(pin_ll.x, pin_ll.y, o_lon, o_lat)
    rot = bearing_deg(east, north)

    def to_xy_tee(lon: float, lat: float) -> tuple[float, float]:
        return rotate(*to_local(lon, lat, o_lon, o_lat), rot)

    # Polygons in the tee-centred frame.
    polys_tee: dict[str, list[Polygon]] = {}
    for kind in LIE_KINDS:
        polys_tee[kind] = [Polygon(_ring_xy(p, to_xy_tee)) for p in feats[kind]]
    for kind in ("water", "ob"):
        polys_tee[kind] = [Polygon(_ring_xy(p, to_xy_tee)) for p in getattr(traced, kind)]
    for _, poly in traced.tee:
        polys_tee["tee"].append(Polygon(_ring_xy(poly, to_xy_tee)))
    centerline_tee = LineString(
        [to_xy_tee(lon, lat) for lon, lat in hole_centerlines(osm)[hole_number].coords]
    )

    everything = [p for ps in polys_tee.values() for p in ps]
    corridor_tee = union_all([*everything, centerline_tee.buffer(1.0)]).buffer(margin_m)
    minx, miny, maxx, maxy = corridor_tee.bounds
    minx, miny, maxx, maxy = minx + margin_m, miny + margin_m, maxx - margin_m, maxy - margin_m
    x0 = math.floor((minx - margin_m) / cell_m) * cell_m
    y0 = math.floor((miny - margin_m) / cell_m) * cell_m
    cols = int(math.ceil((maxx + margin_m - x0) / cell_m))
    rows = int(math.ceil((maxy + margin_m - y0) / cell_m))

    def shift(xy: tuple[float, float]) -> tuple[float, float]:
        return (xy[0] - x0, xy[1] - y0)

    def to_xy(lon: float, lat: float) -> tuple[float, float]:
        return shift(to_xy_tee(lon, lat))

    polys_xy_shapely = {
        k: [Polygon([shift(c) for c in p.exterior.coords]) for p in ps]
        for k, ps in polys_tee.items()
    }
    corridor = Polygon(
        [shift(c) for c in corridor_tee.exterior.coords]
        if corridor_tee.geom_type == "Polygon"
        else []
    )
    if corridor_tee.geom_type != "Polygon":  # disjoint pieces: fall back to the default rule
        log.warning(
            "hole %d: corridor is not a single polygon, using the buffered union", hole_number
        )
        corridor = None
    lie = rasterize(polys_xy_shapely, rows, cols, cell_m, margin_m=margin_m, corridor=corridor)
    tee_xy = shift((0.0, 0.0))
    pin_xy = to_xy(pin_ll.x, pin_ll.y)
    tees = label_tees(tee_polys, pin_ll, tags, to_xy)
    tees["black"] = tee_xy  # exact, avoids float drift from the centroid round trip
    for name, poly in traced.tee:
        if name:
            tees[name] = to_xy(poly.centroid.x, poly.centroid.y)

    assert pin_xy[1] > tee_xy[1], "pin must be up the +y axis from the tee"
    assert abs(pin_xy[0] - tee_xy[0]) < 30, "pin must sit near the +y axis"

    drop = compute_drop_index(lie, tee_xy, cell_m)
    origin_lon, origin_lat = to_lonlat(*unrotate(x0, y0, rot), o_lon, o_lat)

    polygons_xy = {
        k: [[(float(x), float(y)) for x, y in p.exterior.coords] for p in ps]
        for k, ps in polys_xy_shapely.items()
        if ps
    }
    hole = Hole(
        number=hole_number,
        par=int(tags.get("par", 4)),
        cell_m=cell_m,
        rows=rows,
        cols=cols,
        origin_lat=origin_lat,
        origin_lon=origin_lon,
        rotation_deg=rot,
        tee_xy=tee_xy,
        tees=tees,
        pin_xy=pin_xy,
        lie=lie,
        drop_index=drop,
        polygons_xy=polygons_xy,
    )
    write_hole_geojson(hole, Path(holes_dir) / f"{hole_number}.geojson")
    write_lie_png(hole, Path(out_dir) / f"{hole_number}_lie.png")
    return hole


def write_hole_geojson(hole: Hole, path: Path) -> None:
    """Merged hole features in lon/lat for inspection in geojson.io."""
    feats = []
    for kind, rings in hole.polygons_xy.items():
        for ring in rings:
            feats.append(
                {
                    "type": "Feature",
                    "properties": {"kind": kind, "hole": hole.number},
                    "geometry": {
                        "type": "Polygon",
                        "coordinates": [
                            _ring_lonlat(ring, hole.rotation_deg, hole.origin_lon, hole.origin_lat)
                        ],
                    },
                }
            )
    pts = {"pin": hole.pin_xy, **{f"tee:{k}": v for k, v in hole.tees.items()}}
    for name, xy in pts.items():
        lon, lat = to_lonlat(*unrotate(*xy, hole.rotation_deg), hole.origin_lon, hole.origin_lat)
        feats.append(
            {
                "type": "Feature",
                "properties": {"kind": name, "hole": hole.number},
                "geometry": {"type": "Point", "coordinates": [lon, lat]},
            }
        )
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps({"type": "FeatureCollection", "features": feats}, indent=1))


_LIE_COLOURS = {
    0: "#ffffff", 1: "#3b6d11", 2: "#7ccd4a", 3: "#2e7d32", 4: "#e6d8a8",
    5: "#b9f6ca", 6: "#4fa3e0", 7: "#d32f2f",
}  # fmt: skip


def write_lie_png(hole: Hole, path: Path) -> None:
    import matplotlib

    matplotlib.use("Agg")
    import matplotlib.pyplot as plt
    from matplotlib.colors import ListedColormap

    cmap = ListedColormap([_LIE_COLOURS[i] for i in range(8)])
    fig, ax = plt.subplots(figsize=(4, 4 * hole.rows / max(hole.cols, 1)))
    extent = (0, hole.cols * hole.cell_m, 0, hole.rows * hole.cell_m)
    ax.imshow(hole.lie, cmap=cmap, vmin=-0.5, vmax=7.5, origin="lower", extent=extent)
    ax.plot(*hole.pin_xy, "k*", ms=10, label="pin")
    for name, xy in hole.tees.items():
        ax.plot(*xy, "ko", ms=4)
        ax.annotate(name, xy, fontsize=6, xytext=(3, 3), textcoords="offset points")
    ax.set_title(f"hole {hole.number} lie grid ({hole.rows} x {hole.cols})")
    ax.set_xlabel("x (m, right)")
    ax.set_ylabel("y (m, to pin)")
    path.parent.mkdir(parents=True, exist_ok=True)
    fig.savefig(path, dpi=150, bbox_inches="tight")
    plt.close(fig)
