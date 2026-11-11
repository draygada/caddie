"""Fetch the Stanford Golf Course features from Overpass and write GeoJSON.

Usage: uv run python scripts/extract_osm.py [--out data/raw/osm_stanford.geojson]

The result is committed; this script exists to refresh it. The OSM JSON is
converted to GeoJSON by the small converter below instead of osmtogeojson
(npm) so the solver has no Node dependency.
"""

from __future__ import annotations

import argparse
import json
import logging
import sys
import urllib.parse
import urllib.request
from pathlib import Path

OVERPASS_URL = "https://overpass-api.de/api/interpreter"
QUERY = """
[out:json][timeout:60];
rel(3570691); map_to_area -> .course;
( way["golf"](area.course); relation["golf"](area.course); way["waterway"](area.course); );
out body; >; out skel qt;
"""

log = logging.getLogger("extract_osm")


def fetch(query: str = QUERY, url: str = OVERPASS_URL) -> dict:
    data = urllib.parse.urlencode({"data": query}).encode()
    req = urllib.request.Request(url, data=data, headers={"User-Agent": "caddie-solver/0.1"})
    with urllib.request.urlopen(req, timeout=120) as resp:  # noqa: S310
        return json.load(resp)


def _is_closed(coords: list[list[float]]) -> bool:
    return len(coords) >= 4 and coords[0] == coords[-1]


def _way_is_area(tags: dict) -> bool:
    if tags.get("area") == "no":
        return False
    if "golf" in tags and tags["golf"] not in {"hole", "cartpath", "path"}:
        return True
    return any(k in tags for k in ("natural", "landuse", "leisure", "building", "amenity"))


def osm_to_geojson(osm: dict) -> dict:
    """Convert Overpass JSON (nodes, ways, relations) into a GeoJSON FeatureCollection.

    Tagged nodes become Points. Ways become Polygons when closed and area-like,
    otherwise LineStrings. Relations with type=multipolygon become
    (Multi)Polygons from their outer ways; other relations are skipped.
    Untagged ways and nodes (geometry-only) produce no feature.
    """
    nodes: dict[int, list[float]] = {}
    ways: dict[int, dict] = {}
    for el in osm["elements"]:
        if el["type"] == "node":
            nodes[el["id"]] = [el["lon"], el["lat"]]
        elif el["type"] == "way":
            ways[el["id"]] = el

    features: list[dict] = []

    def feature(geom: dict, el: dict) -> dict:
        props = dict(el.get("tags", {}))
        props["osm_type"] = el["type"]
        props["osm_id"] = el["id"]
        return {"type": "Feature", "geometry": geom, "properties": props}

    for el in osm["elements"]:
        tags = el.get("tags")
        if not tags:
            continue
        if el["type"] == "node":
            features.append(feature({"type": "Point", "coordinates": nodes[el["id"]]}, el))
        elif el["type"] == "way":
            coords = [nodes[n] for n in el["nodes"] if n in nodes]
            if len(coords) < 2:
                continue
            if _is_closed(coords) and _way_is_area(tags):
                geom = {"type": "Polygon", "coordinates": [coords]}
            else:
                geom = {"type": "LineString", "coordinates": coords}
            features.append(feature(geom, el))
        elif el["type"] == "relation" and tags.get("type") == "multipolygon":
            rings = _assemble_rings(el, ways, nodes, role="outer")
            inner = _assemble_rings(el, ways, nodes, role="inner")
            if not rings:
                continue
            polys = [[r] + inner for r in rings] if len(rings) == 1 else [[r] for r in rings]
            geom = (
                {"type": "Polygon", "coordinates": polys[0]}
                if len(polys) == 1
                else {"type": "MultiPolygon", "coordinates": polys}
            )
            features.append(feature(geom, el))
    return {"type": "FeatureCollection", "features": features}


def _assemble_rings(rel: dict, ways: dict, nodes: dict, role: str) -> list[list[list[float]]]:
    """Join member ways with the given role into closed rings (greedy endpoint matching)."""
    segments = []
    for m in rel.get("members", []):
        if m["type"] == "way" and m.get("role", "outer") == role and m["ref"] in ways:
            coords = [nodes[n] for n in ways[m["ref"]]["nodes"] if n in nodes]
            if len(coords) >= 2:
                segments.append(coords)
    rings: list[list[list[float]]] = []
    while segments:
        ring = segments.pop(0)
        changed = True
        while not _is_closed(ring) and changed:
            changed = False
            for i, seg in enumerate(segments):
                if seg[0] == ring[-1]:
                    ring = ring + seg[1:]
                elif seg[-1] == ring[-1]:
                    ring = ring + seg[-2::-1]
                elif seg[-1] == ring[0]:
                    ring = seg[:-1] + ring
                elif seg[0] == ring[0]:
                    ring = seg[::-1][:-1] + ring
                else:
                    continue
                segments.pop(i)
                changed = True
                break
        if _is_closed(ring):
            rings.append(ring)
        else:
            log.warning("relation %s: unclosed %s ring dropped", rel["id"], role)
    return rings


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--out", type=Path, default=Path("data/raw/osm_stanford.geojson"))
    args = parser.parse_args(argv)
    logging.basicConfig(level=logging.INFO, format="%(levelname)s %(message)s")
    log.info("querying Overpass")
    osm = fetch()
    gj = osm_to_geojson(osm)
    args.out.parent.mkdir(parents=True, exist_ok=True)
    args.out.write_text(json.dumps(gj))
    log.info("wrote %d features to %s", len(gj["features"]), args.out)
    return 0


if __name__ == "__main__":
    sys.exit(main())
