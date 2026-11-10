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
