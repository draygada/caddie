# Part 17: trees and tee-only driver

Branch `part/17-trees-tee-driver`. Scope: `solver/scripts/extract_osm.py`, `solver/data/raw/osm_stanford.geojson`, `solver/caddie/geometry.py`, `solver/caddie/mdp.py`, `solver/caddie/value_iteration.py` (candidate rule only), `solver/tests/test_geometry.py`, `solver/tests/test_mdp.py`, `solver/tests/fixtures/toy_hole.py` (a tree variant only; the existing toy hole is unchanged), `docs/fixtures/tree_rays.json`, `app/src/lib/types.ts`, `app/src/lib/shot.ts`, `app/src/lib/rollout.ts` (candidate rule only), `app/src/lib/heatmap.ts` (tree colour), their tests. Depends on parts 01 to 08 and 12.

## Purpose

Two guardrails the model lacks today. First, trees: the hole has no tree cells, and only the landing cell of a shot is checked, so the solver happily cuts a dogleg corner over a wood. Second, the driver is a candidate from any lie, so the policy recommends driver off the fairway in about a third of hole 11's cells. After this part the solver aims around trees on its own and only hits driver from a tee.

## Data

OpenStreetMap already maps the trees around the course; the current export misses them because the Overpass query only asks for `golf=*` and `waterway=*`. A query on 2026-11-16 over the course bounding box returned 1,598 `natural=tree` nodes, 34 `natural=wood` ways and 1 relation, 6 `natural=tree_row` ways and 1 `natural=scrub` way. Nobody has tagged OB or hazard areas, so the traced OB polygons stay as they are.

Rasterising, all in hole-local meters:

| OSM feature | Becomes |
| --- | --- |
| `natural=wood` polygon or multipolygon | the polygon |
| `natural=tree` node | a disc of radius `diameter_crown / 2` if tagged, else `TREE_CROWN_RADIUS_M = 4.0` |
| `natural=tree_row` line | the line buffered by `TREE_CROWN_RADIUS_M` |
| `natural=scrub` | ignored (rough already covers it) |

A cell is `trees` when its centre falls inside the union. Precedence: green, tee, bunker, water and OB keep their code; trees overwrite fairway and rough. `TREE_CROWN_RADIUS_M` is our estimate, not a measured value; check the overlay against the satellite view in slice 2 and change the constant there if the canopies look clearly larger or smaller.

## Rules

- **New lie code 8, `trees`.** Like water, tree cells are terrain, not states: `value.f32` is NaN there and `club.u8`, `dir.u8` are 255.
- **A ball cannot pass through trees.** For a shot from point S, the carry segment from S to the landing point L and the roll segment from L to the final point F are both checked. If either segment enters a tree cell, the ball comes to rest `TREE_STEP_BACK_M = 2.5` m (half a cell) before the first tree point along that segment, with no roll after it and no penalty stroke, and the terrain rule for the active mode then applies to that resting cell as usual. This is deliberately strict: real shots clear trees once they are high in the air. A loft exemption is out of scope and listed as a follow-up.
- **Driver only from a tee.** `TEE_ONLY_CLUBS = ("driver",)`. From any lie other than tee, those clubs are not candidates. Applies to `club_cells` in value iteration, `candidate_actions` in `mdp.py` and `candidateClubs` in `rollout.ts`.

## Interfaces

```python
# geometry.py
TREE_CROWN_RADIUS_M = 4.0
def extract_trees(osm: dict, hole_number: int) -> list[Polygon]   # the union pieces, in hole-local meters
# rasterize() gains the "trees" layer with the precedence above

# mdp.py
class Lie(IntEnum): ...; TREES = 8
TREE_STEP_BACK_M = 2.5
RAY_BIN_DEG = 0.5
RAY_STEP_M = 1.0
RAY_MAX_M = 320.0
def first_tree_distance(hole: Hole, x: float, y: float, bearing_deg: float, max_m: float = RAY_MAX_M) -> float
    # exact march in RAY_STEP_M steps from (x, y); inf if no tree within max_m. The reference both halves test against.
def tree_ray_table(hole: Hole) -> np.ndarray
    # (n_cells, 720) float32: first_tree_distance from every playable cell centre at each 0.5 degree absolute bearing.
    # Built once per hole and cached on the Hole; holes with no tree cells get an all-inf table without marching.
# step_batch: carry blocked if carry_len >= ray[from_cell, bin(bearing)]; rest at ray - TREE_STEP_BACK_M along the shot bearing.
# roll blocked by an exact first_tree_distance march from L (rolls are short, so this is cheap on the few draws that land near trees).
TEE_ONLY_CLUBS = ("driver",)
```

```ts
// shot.ts
export const TREE_STEP_BACK_M = 2.5
export function firstTreeDistance(b: HoleBundle, from: XY, bearingDeg: number, maxM?: number): number   // same march as Python
// sampleShot applies the blocking rule with an exact march (no table: the rollout starts from a continuous point)

// rollout.ts
export const TEE_ONLY_CLUBS = ['driver']
```

The cell table uses 0.5 degree bins, so at 250 m a bin is about 2.2 m wide, under half a cell. The cell solver (table) and the app rollout (exact march) can therefore disagree on a draw that grazes a tree edge; parity is tested on `first_tree_distance` itself, not on whole shots.

## Slices

1. **Fetch trees.** Extend the Overpass query in `extract_osm.py` with `natural=tree|wood|tree_row` inside the course area plus a 100 m buffer, re-export, commit the geojson. Test: the converter turns a tree node into a Point and a wood way into a Polygon (fixture JSON, no network).
2. **Rasterise trees.** `extract_trees` and the precedence rule. Tests on a synthetic hole: a disc of radius 4 m marks the expected cells, a tree inside a bunker leaves the bunker, a tree on fairway becomes trees. Write `solver/out/<hole>_lie.png` for 10, 11, 12 with trees in dark green and eyeball them against the satellite view; note any big mismatch in the PR.
3. **Lie code 8 end to end.** `Lie.TREES`, `lie.u8` round trip, NaN value and 255 actions on tree cells, app `Lie` type widened and heatmap colour added. Existing toy tests unchanged.
4. **Exact march and fixture.** `first_tree_distance` on a tree variant of the toy hole: straight at a tree row returns the row distance to within `RAY_STEP_M`, parallel to it returns inf. Write `docs/fixtures/tree_rays.json` (10 cases of x, y, bearing, distance); `firstTreeDistance` in TS reproduces every case to 1e-6.
5. **Blocking in `step_batch`.** On the tree toy variant: a shot aimed through the row rests 2.5 m short of it with reward -1; the same shot aimed 20 degrees clear is unchanged from today; a roll into the row stops before it. The existing toy-hole value test still passes (no trees there).
6. **Blocking in `sampleShot`.** The same three cases in vitest with a seeded rng.
7. **Tee-only driver.** Candidate rules in all three places. Test: from a fairway cell 250 m out the candidate set has no driver; from a tee cell it does; the toy hole (one club) is unaffected.
8. **Re-solve and check.** Solve 11 drop with the sample player. Report in the PR: solve time before and after, the share of cells where the policy changed, and a policy-arrow PNG zoomed on the dogleg showing the aim moving off the trees. Run the part 16 benchmark; expectation changes are reported, not fixed here.

## Done when

On hole 11 with the sample player, no recommended tee shot's mean path crosses a tree cell, driver appears only on tee cells, and the app's Play it out never shows a ball passing through trees.

## Pitfalls

- OSM tree nodes are sparse in places and some will be stale. Missing trees mean the solver will happily aim through them; the satellite overlay in slice 2 is the check.
- The ray table is per playable cell, so it must be rebuilt whenever `lie` changes; cache it on the `Hole`, keyed by nothing else.
- A ball can start inside a tree cell only from the app (GPS or a dragged ball). Treat it as rough for the shot, and do not block on the first `TREE_STEP_BACK_M` so the player can chip out.
- The benchmark synthetic holes have no trees; their results should change only through the driver rule.
