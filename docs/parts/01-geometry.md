# Part 01: geometry.py

Branch `part/01-geometry`. Scope: `solver/caddie/geometry.py`, `solver/tests/test_geometry.py`, `solver/data/holes/*.geojson`, `solver/scripts/extract_osm.py`.

## Purpose

Turn hole polygons into a hole-local meters grid with a lie code per cell, plus the drop cell for every water cell and the metadata the app needs to place the grid on a map.

## Inputs

- `solver/data/raw/osm_stanford.geojson`: Overpass export of relation 3570691 (all golf-tagged ways and relations, plus `waterway=*`). Query in slice 1.
- Hand-traced additions per hole in geojson.io, saved as `solver/data/raw/traced_<hole>.geojson`: `water` polygons (San Francisquito Creek where it is in play), `ob` polygons, and a point `pin`. Tee boxes come from OSM `golf=tee` polygons; if a tee's colour tag is missing, label it by distance from the green (longest = black) and say so in the PR.

## Outputs

```python
@dataclass
class Hole:
    number: int
    par: int
    cell_m: float                 # 5.0
    rows: int
    cols: int
    origin_lat: float             # Black tee
    origin_lon: float
    rotation_deg: float           # bearing of tee->pin, degrees clockwise from north
    tee_xy: tuple[float, float]   # grid meters, Black tee (grid origin)
    tees: dict[str, tuple[float, float]]   # every tee box found: black, white, blue, cardinal, from OSM golf=tee polygons' centroids with their ref/colour tag
    pin_xy: tuple[float, float]
    lie: np.ndarray               # uint8 (rows, cols), codes per root contract
    drop_index: np.ndarray        # int32 (rows, cols): flat index of the drop cell for water cells, -1 elsewhere
    polygons_xy: dict[str, list[list[tuple[float, float]]]]   # per lie name, in grid meters
```

## Interfaces

```python
def extract_hole_features(osm: dict, hole_number: int) -> dict[str, list[Polygon]]
    # returns {"tee": [...], "fairway": [...], "rough": [...], "bunker": [...], "green": [...]} as shapely Polygons in lon/lat
    # back-nine polygons lack ref tags: assign any untagged polygon to the hole whose golf=hole centerline is nearest (shapely distance), within 60 m

def to_local(lon: float, lat: float, origin_lon: float, origin_lat: float) -> tuple[float, float]
    # pyproj AEQD centred on origin -> (east, north) meters

def rotate(east: float, north: float, rotation_deg: float) -> tuple[float, float]
    # rotate so the tee->pin bearing becomes +y; returns (x, y)

def rasterize(polys_xy: dict[str, list[Polygon]], rows: int, cols: int, cell_m: float) -> np.ndarray
    # uint8 grid; priority when polygons overlap: water > ob > bunker > green > tee > fairway > rough; 0 where nothing covers the cell centre
    # everything inside the grid not covered by any polygon is rough (3), not 0; 0 is reserved for outside the hole corridor (see slice 4)

def compute_drop_index(lie: np.ndarray, tee_xy, cell_m) -> np.ndarray
    # for each water cell: nearest fairway or rough cell whose y is <= the water cell's y (tee side), by Euclidean distance; -1 for non-water

def build_hole(hole_number: int, osm_path: Path, traced_path: Path, cell_m: float = 5.0, margin_m: float = 40.0) -> Hole
```

## Slices

1. **OSM extract script.** `scripts/extract_osm.py` fetches the Overpass query below into `data/raw/osm_stanford.geojson` (commit the result; the script is for refresh). Test: file parses, contains 18 features with `golf=hole`, and holes 10, 11, 12 each have at least one `golf=green` within 60 m of the centerline end.

   ```
   [out:json][timeout:60];
   rel(3570691); map_to_area -> .course;
   ( way["golf"](area.course); relation["golf"](area.course); way["waterway"](area.course); );
   out body; >; out skel qt;
   ```

   Convert with `osmtogeojson` (npm) or write the small converter; either is fine, say which.

2. **Local projection and rotation.** `to_local`, `rotate`, and their inverses `to_lonlat`, `unrotate`. Test against `docs/fixtures/geo_points.json` (three lon/lat points with known grid xy for hole 11) to 0.5 m, and round-trip to 1e-6 degrees.

3. **Feature extraction and assignment.** `extract_hole_features` for holes 10, 11, 12. Test: each returns one green, at least one fairway, at least one tee; no polygon assigned to two holes.

4. **Rasterize.** Grid extent is the bounding box of all the hole's polygons plus `margin_m`, snapped to `cell_m`. Cells outside the union of all polygons buffered by `margin_m` get 0; inside the buffer but uncovered get rough. Test on a synthetic 3-polygon hole: counts of each code match the polygon areas to within 10%; priority rule holds where a bunker overlaps fairway.

5. **Drop index.** Test on the toy pattern: a water cell at row 7 maps to a fairway cell with row <= 7; non-water is -1.

6. **build_hole and GeoJSON merge.** Merge traced water, ob, pin with OSM features; populate `tees` (at least black and white per hole); write `data/holes/<hole>.geojson` in lon/lat for inspection. `build_hole(11, ...)` returns a `Hole` with rows between 60 and 110, cols between 20 and 50, pin inside a green cell, tee inside a tee cell. Also write `solver/out/<hole>_lie.png` via matplotlib.

## Done when

`uv run python -c "from caddie.geometry import build_hole; h = build_hole(10, ...); print(h.rows, h.cols)"` prints plausible sizes and `solver/out/10_lie.png` looks like hole 10 with the green in the right place. Build hole 10 first, then 11, then 12.

## Pitfalls

- OSM back-nine fairway/green ways carry no `ref`. Assign by nearest hole centerline, and check hole 11 and 12 do not swallow each other's greens (they are adjacent).
- The creek is `waterway=stream` (a line), not a polygon. Trace the in-play section as a polygon by hand; do not buffer the line.
- Rotation sign: after rotating, `pin_xy[1] > tee_xy[1]` and `abs(pin_xy[0] - tee_xy[0]) < 30`. Assert this in `build_hole`.
