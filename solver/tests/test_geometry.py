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


# slice 4 -------------------------------------------------------------------


def _box(x0, y0, x1, y1):
    from shapely.geometry import box

    return box(x0, y0, x1, y1)


@pytest.fixture
def synthetic_hole():
    """Three polygons in grid meters on a 40 col x 60 row, 5 m grid (200 x 300 m)."""
    fairway = _box(60, 20, 140, 240)  # 80 x 220 = 17600 m2
    green = _box(80, 240, 120, 280)  # 40 x 40 = 1600 m2
    bunker = _box(120, 100, 160, 140)  # 40 x 40 = 1600 m2, half over the fairway
    return {"fairway": [fairway], "green": [green], "bunker": [bunker]}


def test_rasterize_counts_match_areas(synthetic_hole):
    from caddie.geometry import LIE_CODE, rasterize

    cell = 5.0
    lie = rasterize(synthetic_hole, rows=60, cols=40, cell_m=cell, margin_m=0.0)
    assert lie.dtype == np.uint8 and lie.shape == (60, 40)
    bunker = synthetic_hole["bunker"][0]
    fairway_visible = synthetic_hole["fairway"][0].difference(bunker)
    expected = {
        "bunker": bunker.area,
        "green": synthetic_hole["green"][0].area,
        "fairway": fairway_visible.area,
    }
    for kind, area in expected.items():
        got = np.count_nonzero(lie == LIE_CODE[kind]) * cell * cell
        assert abs(got - area) <= 0.10 * area, (kind, got, area)


def test_rasterize_priority_bunker_over_fairway(synthetic_hole):
    from caddie.geometry import LIE_CODE, rasterize

    lie = rasterize(synthetic_hole, rows=60, cols=40, cell_m=5.0, margin_m=0.0)
    # cell centre (132.5, 122.5) is inside both the fairway and the bunker
    assert lie[24, 26] == LIE_CODE["bunker"]
    # cell centre (102.5, 122.5) is fairway only
    assert lie[24, 20] == LIE_CODE["fairway"]


def test_rasterize_corridor_margin(synthetic_hole):
    from caddie.geometry import LIE_CODE, rasterize

    lie = rasterize(synthetic_hole, rows=60, cols=40, cell_m=5.0, margin_m=20.0)
    # far corner: outside every polygon plus 20 m -> OUT (0)
    assert lie[0, 0] == LIE_CODE["out"]
    # 10 m outside the fairway edge: inside the buffer, uncovered -> rough
    assert lie[20, 10] == LIE_CODE["rough"]  # centre (52.5, 102.5), 7.5 m left of the fairway
    # with no margin nothing is rough
    lie0 = rasterize(synthetic_hole, rows=60, cols=40, cell_m=5.0, margin_m=0.0)
    assert np.count_nonzero(lie0 == LIE_CODE["rough"]) == 0


# slice 5 -------------------------------------------------------------------


@pytest.fixture
def toy_lie():
    """The 10 x 10 toy pattern from solver/CLAUDE.md as a lie grid (fairway base)."""
    from caddie.geometry import LIE_CODE

    lie = np.full((10, 10), LIE_CODE["fairway"], dtype=np.uint8)
    lie[5, 4] = lie[5, 5] = LIE_CODE["bunker"]
    lie[7, 0:4] = LIE_CODE["water"]
    lie[:, 9] = LIE_CODE["ob"]
    return lie


def test_drop_index_water_maps_to_tee_side_fairway(toy_lie):
    from caddie.geometry import LIE_CODE, compute_drop_index

    drop = compute_drop_index(toy_lie, tee_xy=(27.5, 2.5), cell_m=5.0)
    assert drop.dtype == np.int32 and drop.shape == toy_lie.shape
    cols = toy_lie.shape[1]
    for c in range(4):
        i = drop[7, c]
        assert i >= 0
        r, cc = divmod(int(i), cols)
        assert r <= 7, "drop cell must be on the tee side"
        assert toy_lie[r, cc] in (LIE_CODE["fairway"], LIE_CODE["rough"])
    # water at (7, 0) drops straight back to (6, 0), its nearest tee-side fairway cell
    assert drop[7, 0] == 6 * cols + 0


def test_drop_index_minus_one_off_water(toy_lie):
    from caddie.geometry import LIE_CODE, compute_drop_index

    drop = compute_drop_index(toy_lie, tee_xy=(27.5, 2.5), cell_m=5.0)
    assert np.all(drop[toy_lie != LIE_CODE["water"]] == -1)
    assert np.count_nonzero(drop >= 0) == 4
