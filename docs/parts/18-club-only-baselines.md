# Part 18: club-only baselines

Branch `part/18-club-only-baselines`. Scope: `solver/caddie/value_iteration.py` (an `aim` argument on `solve` and `bellman_backup`, default `"free"`, so parts 05 to 17 are unchanged), `solver/caddie/evaluate.py` (two new policies, the decomposition table, and the part 17 rules in `pin_policy` and `centre_policy`), `solver/caddie/approaches.py` (two new approach ids), `solver/tests/test_value_iteration.py`, `solver/tests/test_evaluate.py`, `solver/tests/test_approaches.py`. Depends on parts 05, 07, 16 and 17.

## Purpose

The status update says the centre baseline "chooses club optimally", which is not what `centre_policy` does: it takes the club whose mean carry is closest to the centroid distance. This part makes that sentence true and uses it to split the gain of the optimal policy into the part that comes from choosing the club and the part that comes from choosing the aim.

## Policies

| id | Club | Aim |
| --- | --- | --- |
| `pin` | longest that does not overshoot (part 07) | pin |
| `club_pin` | value iteration over clubs | pin, direction index of 0 degrees in every cell |
| `club_centre` | value iteration over clubs | the green centroid, nearest direction index per cell |
| `optimal` | value iteration over clubs and aims | free |

`club_pin` and `club_centre` are value iteration on the same MDP with the action set restricted to one direction per cell. Each solve tries 13 actions per cell instead of 13 x 91, so it is far cheaper than the full solve, and it converges by the same argument.

## Part 17 rules in every baseline

Part 17 changed the game, and a baseline that ignores it is not a fair comparison: in the part 16 rerun the pin rule averaged 13.16 strokes on hole 11 because it hit the same tree until the 40 shot cap. So all four rows obey two rules.

- **Tee-only clubs.** `pin` takes the longest allowed club that does not overshoot, `centre` the allowed club closest to the centroid distance, with `allowed_clubs` from part 17. The restricted solves inherit this from the backup.
- **Clear aim.** The aim is the target direction (pin or centroid) unless trees block it; then it is the nearest 2 degree step, within plus or minus 90, that is clear, lower angle first on a tie. If no step is clear the target direction is kept. A direction is blocked for a club and from-lie when the cell's ray table (part 17) has a tree at or before `min(low_flight_m(c), 0.5 c + TREE_STEP_BACK_M)` on the aim line or on the lines one `sigma_theta` either side, with `c` the club's mean carry from that lie. This is the solver-side twin of `clearAim` in the app's `shot.ts`; it reads the per-cell table, so it is exact at cell centres only.

With clear aim the direction of a restricted solve depends on the club as well as the cell. On a hole without trees and a bag without tee-only clubs, every policy is unchanged from part 07.

## Interfaces

```python
# value_iteration.py
Aim = Literal["free", "pin", "centre"]
def aim_dir_index(hole: Hole, cells: np.ndarray, aim: Aim) -> np.ndarray | None
    # None for "free"; else one direction index per cell. "centre" uses the green centroid computed here
    # (not imported from evaluate.py, which is a later part).
def clear_dir_index(hole, player, cells, from_lie, club_idx, dir_idx) -> np.ndarray
    # the clear aim rule above: one direction index per cell for this club; dir_idx unchanged on a hole without trees
def solve(..., aim: Aim = "free") -> Solution
    # restricted backups loop over clubs and the distinct clear direction indices, each on the subset of cells that use it

# evaluate.py
def club_only_policy(solution: Solution) -> Policy           # grid lookup, same as optimal_policy
def decomposition_table(results: dict) -> str               # markdown rows below
```

Decomposition table (markdown, written next to the existing report tables):

| Step | Mean strokes | Gain over previous |
| --- | --- | --- |
| Pin rule | | |
| Choose the club, aim at pin | | value of club choice |
| Choose the club, aim at centre | | value of aiming at the centre |
| Choose club and aim | | value of free aim |

## Slices

1. **Restricted backup.** `aim_dir_index` and the `aim` argument. Test on the toy hole: with `aim="pin"` every cell's `dir` is the 0 degree index; the restricted value is never better than the free value in any cell (to 1e-6); with one club and `aim="pin"` the solve equals evaluating the fixed pin policy.
2. **Clear aim and centre aim.** `clear_dir_index` on the part 17 tree fixture: a cell behind a tree gets the nearest clear step, a cell in the open keeps the target, and a restricted solve on that fixture converges. `pin_policy` and `centre_policy` use it and `allowed_clubs`; on the toy hole they are unchanged. On the toy hole the `club_centre` direction per cell equals the direction `centre_policy` picks; only the club may differ.
3. **Evaluate.** `evaluate_hole` adds `club_pin` and `club_centre` (paired draws as before) and writes the decomposition table. Test: the four means are ordered `optimal <= club_centre` and `optimal <= club_pin` within two paired standard errors on the toy hole.
4. **Benchmark ids.** `club_pin` and `club_centre` in `APPROACHES` with `needs_solution=True`; quick benchmark test passes.
5. **Hole 11 numbers.** Run `evaluate 11 --mode drop` with the sample player and paste the decomposition table in the PR.

## Done when

The decomposition table exists for hole 11 and the four rows add up: each gain is the difference of the two means above it.

## Pitfalls

- Do not change how `centre_policy` picks its club (closest mean carry); the status update sentence refers to it and the new policy has a new id. Only the two part 17 rules are added. The status update's 4.87 and 4.73 predate trees and are not reproduced by any current policy.
- The restricted solve must use the same Halton draws and tolerance as the free solve, or the gains mix model and sampling noise.
