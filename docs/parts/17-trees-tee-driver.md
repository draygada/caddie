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
- **A ball cannot pass through trees while it is below the canopy.** Amended 2026-11-17 after the first build: the original rule blocked the whole carry at ground level, and on hole 11 that stopped 67% of mid-iron shots from an average cell (single mapped trees dot the rough every 20 to 30 m), raised the tee value from 4.46 to 5.03 and tripled the solve time. The ball's height is now modelled, with three estimates of ours, not measurements:
  - `TREE_HEIGHT_M = 15`.
  - The carry is a parabola with apex `A = min(APEX_MAX_M, APEX_PER_CARRY x carry)`, `APEX_MAX_M = 24`, `APEX_PER_CARRY = 0.30`, so the height at distance `s` of a carry `c` is `4 A (s / c)(1 - s / c)`. A full shot peaks near 24 m; a 40 m pitch or a topped shot stays under the trees the whole way.
  - The ball is below the canopy for the first `low = c (1 - sqrt(1 - TREE_HEIGHT_M / A)) / 2` meters of the carry, and for all of it when `A <= TREE_HEIGHT_M`. With `A = 24` that is the first 19% of the carry.
  - **Climb.** If the carry line from S enters a tree cell within `low` meters, the ball stops there.
  - **Descent.** If the landing point L, or the points `DESCENT_STEP_M = 5` and `2 x DESCENT_STEP_M` short of it on the carry line (when they are past `low`), is in a tree cell, the ball stops at the first of those three points that is. Sampling three points instead of marching keeps the rule cheap; a real descent from 15 m covers about 10 m of ground.
  - **Roll.** The roll from L to F is on the ground and is checked in full.
  - A stopped ball rests `TREE_STEP_BACK_M = 2.5` m (half a cell) before the tree point that stopped it, walked back further while that spot is itself in a tree cell, with no roll after it and no penalty stroke. The terrain rule for the active mode then applies to the resting cell as usual.
- **No playable cell may be boxed in.** A tee, fairway, rough or bunker cell that trees cut off from the green (no 4-connected path of non-tree cells), or that has trees in 6 or more of its 8 neighbours, becomes a tree cell when the hole is built; the second test repeats until nothing changes. Without this a boxed-in cell has no way out, its value grows without bound and value iteration does not converge (hole 10 has one such cell, hole 11 a nearly boxed-in one worth 13 strokes).
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
TREE_HEIGHT_M = 15.0; APEX_MAX_M = 24.0; APEX_PER_CARRY = 0.30; DESCENT_STEP_M = 5.0
def low_flight_m(carry: np.ndarray) -> np.ndarray   # meters of the carry spent below the canopy at each end
# step_batch climb: blocked if ray[from_cell, bin(bearing)] <= low_flight_m(carry); rest at ray - TREE_STEP_BACK_M along the shot bearing.
# step_batch descent: the three sample points; roll: an exact first_tree_distance march from L on the draws that land near trees.
# geometry.py: seal_tree_pockets(lie) applies the boxed-in rule in build_hole.
TEE_ONLY_CLUBS = ("driver",)
```

```ts
// shot.ts
export const TREE_STEP_BACK_M = 2.5
export function firstTreeDistance(b: HoleBundle, from: XY, bearingDeg: number, maxM?: number): number   // same march as Python
export function lowFlightM(carry: number): number                                                           // same formula as Python
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
5. **Blocking in `step_batch`.** `low_flight_m` against hand values (carry 100 gives 19.4, carry 40 gives 40), added to `docs/fixtures/tree_rays.json`. `seal_tree_pockets` on synthetic grids and on the three holes. On the tree toy variant (25 m club, so the whole flight is low): a shot aimed through the row rests 2.5 m short of it with reward -1; a long club whose apex clears the row flies over it; the same shot aimed 20 degrees clear is unchanged from today; a roll into the row stops before it. The existing toy-hole value test still passes (no trees there).
6. **Blocking in `sampleShot`.** The same three cases in vitest with a seeded rng.
7. **Tee-only driver.** Candidate rules in all three places. Test: from a fairway cell 250 m out the candidate set has no driver; from a tee cell it does; the toy hole (one club) is unaffected.
8. **Re-solve and check.** Solve 11 drop with the sample player. Report in the PR: solve time before and after, the share of cells where the policy changed, and a policy-arrow PNG zoomed on the dogleg showing the aim moving off the trees. Run the part 16 benchmark; expectation changes are reported, not fixed here.

## Done when

On hole 11 with the sample player, no recommended tee shot's mean path crosses a tree cell while it is below the canopy, driver appears only on tee cells, and the app's Play it out never shows a ball passing through trees.

## Pitfalls

- OSM tree nodes are sparse in places and some will be stale. Missing trees mean the solver will happily aim through them; the satellite overlay in slice 2 is the check.
- The ray table is per playable cell, so it must be rebuilt whenever `lie` changes; cache it on the `Hole`, keyed by nothing else.
- A ball can start inside a tree cell only from the app (GPS or a dragged ball). Treat it as rough for the shot, and do not block on the first `TREE_STEP_BACK_M` so the player can chip out.
- The benchmark synthetic holes have no trees; their results should change only through the driver rule.
- The three height constants are estimates. The policy near tree lines is sensitive to them, so quote them whenever a tree-shaped recommendation is shown.
