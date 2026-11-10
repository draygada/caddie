"""Tests for caddie.geometry (part 01)."""

import json
from pathlib import Path

import numpy as np
import pytest
from shapely.geometry import LineString, Point, shape

DATA = Path(__file__).resolve().parents[1] / "data"
OSM_PATH = DATA / "raw" / "osm_stanford.geojson"
FIXTURES = Path(__file__).resolve().parents[2] / "docs" / "fixtures"


@pytest.fixture(scope="module")
def osm() -> dict:
    with OSM_PATH.open() as f:
        return json.load(f)


def _features(osm: dict, key: str, value: str) -> list[dict]:
    return [f for f in osm["features"] if f["properties"].get(key) == value]


# slice 1 -------------------------------------------------------------------


def test_osm_file_parses(osm):
    assert osm["type"] == "FeatureCollection"
    assert len(osm["features"]) > 0


def test_osm_has_18_holes(osm):
    holes = _features(osm, "golf", "hole")
    assert len(holes) == 18
    refs = sorted(int(h["properties"]["ref"]) for h in holes)
    assert refs == list(range(1, 19))


@pytest.mark.parametrize("hole", [10, 11, 12])
def test_each_target_hole_has_a_green_near_centerline_end(osm, hole):
    [centerline] = [
        f for f in _features(osm, "golf", "hole") if int(f["properties"]["ref"]) == hole
    ]
    line = shape(centerline["geometry"])
    assert isinstance(line, LineString)
    end = Point(line.coords[-1])
    greens = [shape(f["geometry"]) for f in _features(osm, "golf", "green")]
    # 60 m in degrees at this latitude: 1 deg lat ~ 111 km, 1 deg lon ~ 88 km
    near = [g for g in greens if g.distance(end) * 88_000 < 60]
    assert near, f"hole {hole}: no green within 60 m of the centerline end"


# slice 2 -------------------------------------------------------------------


@pytest.fixture(scope="module")
def geo_points() -> dict:
    with (FIXTURES / "geo_points.json").open() as f:
        return json.load(f)


def test_fixture_points_project_to_known_xy(geo_points):
    from caddie.geometry import rotate, to_local

    o = geo_points["origin"]
    rot = geo_points["rotation_deg"]
    assert len(geo_points["points"]) == 3
    for p in geo_points["points"]:
        east, north = to_local(p["lon"], p["lat"], o["lon"], o["lat"])
        x, y = rotate(east, north, rot)
        assert abs(x - p["x"]) < 0.5, p
        assert abs(y - p["y"]) < 0.5, p


def test_projection_round_trips(geo_points):
    from caddie.geometry import rotate, to_local, to_lonlat, unrotate

    o = geo_points["origin"]
    rot = geo_points["rotation_deg"]
    for p in geo_points["points"]:
        east, north = to_local(p["lon"], p["lat"], o["lon"], o["lat"])
        x, y = rotate(east, north, rot)
        east2, north2 = unrotate(x, y, rot)
        lon, lat = to_lonlat(east2, north2, o["lon"], o["lat"])
        assert abs(lon - p["lon"]) < 1e-6
        assert abs(lat - p["lat"]) < 1e-6


def test_rotate_sends_pin_bearing_to_plus_y():
    from caddie.geometry import rotate

    # a point 100 m away along bearing 30 deg clockwise from north
    b = np.radians(30.0)
    east, north = 100 * np.sin(b), 100 * np.cos(b)
    x, y = rotate(east, north, 30.0)
    assert abs(x) < 1e-9
    assert abs(y - 100) < 1e-9
    # a point to the golfer's right (bearing 120) has positive x
    b = np.radians(120.0)
    x, y = rotate(100 * np.sin(b), 100 * np.cos(b), 30.0)
    assert x > 99.9 and abs(y) < 1e-9


def test_root_contract_equirectangular_formula_agrees_to_one_meter(geo_points):
    """The app side uses the simple formula from the root CLAUDE.md; it should stay close."""
    from caddie.geometry import rotate

    o = geo_points["origin"]
    rot = geo_points["rotation_deg"]
    for p in geo_points["points"]:
        north = (p["lat"] - o["lat"]) * 111320
        east = (p["lon"] - o["lon"]) * 111320 * np.cos(np.radians(o["lat"]))
        x, y = rotate(east, north, rot)
        assert abs(x - p["x"]) < 1.0 and abs(y - p["y"]) < 1.0, p


# slice 3 -------------------------------------------------------------------

LIE_KINDS = ("tee", "fairway", "rough", "bunker", "green")


@pytest.mark.parametrize("hole", [10, 11, 12])
def test_extract_hole_features_has_required_kinds(osm, hole):
    from caddie.geometry import extract_hole_features

    feats = extract_hole_features(osm, hole)
    assert set(feats) == set(LIE_KINDS)
    assert len(feats["green"]) == 1
    assert len(feats["fairway"]) >= 1
    assert len(feats["tee"]) >= 1
    for kind in LIE_KINDS:
        for poly in feats[kind]:
            assert poly.geom_type == "Polygon" and poly.is_valid


def test_no_polygon_assigned_to_two_holes(osm):
    from caddie.geometry import extract_hole_features

    seen: dict[tuple[float, float], int] = {}
    for hole in (10, 11, 12):
        for kind in LIE_KINDS:
            for poly in extract_hole_features(osm, hole)[kind]:
                key = tuple(round(v, 9) for v in poly.representative_point().coords[0])
                assert key not in seen, f"polygon in hole {hole} already in hole {seen[key]}"
                seen[key] = hole
