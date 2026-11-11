# Part 16: benchmark.py

Branch `part/16-benchmark`. Scope: `solver/caddie/benchmark.py`, `solver/caddie/approaches.py`, `solver/tests/test_benchmark.py`, `solver/tests/test_approaches.py`, `solver/tests/fixtures/benchmark_holes.py`, `solver/tests/fixtures/benchmark_cases.json`, the `benchmark` subcommand in `solver/caddie/cli.py`, `solver/out/benchmark/`. Two additive changes outside those files are allowed and nothing else: an optional `start=(x, y, lie)` argument on `evaluate.simulate` (default: the Black tee, so part 07 is unchanged) and an `objective` argument on `value_iteration.solve` (default `"strokes"`, so parts 05 to 08 are unchanged). Depends on parts 05, 06, 07.

## Purpose

Compare ways of choosing the shot, not just policies: the offline grid against the online and heuristic alternatives in `docs/extensions.md`, on a fixed set of cases with stated expectations, and rank them on strokes, blow-up risk and compute. Three questions the report needs answered with numbers: how much of the grid's gain over the baselines a cheap rule recovers, what a risk-averse objective trades in mean strokes for fewer blow-ups, and whether the continuous-point methods (rollout, sparse sampling, MCTS) beat the 5 m grid once play happens between cell centres.

Two things the benchmark cannot show, stated so nobody reads them into it. First, the cell-to-cell simulator shares `step_batch` with the solver, so on that simulator the grid policy is optimal by construction and no approach beats its mean except by noise; only the point simulator (slice 5) can separate the continuous methods from it. Second, every ground truth here is the model's own transition rule, so "best" means best under the fitted dispersion, not on the course.

## Approaches

An approach is a factory for a `Policy` (part 07 type, `(x, y, lie) -> (club_idx, dir_idx)`) plus a continuous-point variant where one exists. Online approaches memoise decisions per `(cell, lie)` on the cell simulator and per decision on the point simulator; the time they spend is reported, not hidden.

| id | what it does | source |
| --- | --- | --- |
| `grid` | nearest-cell lookup in the value iteration solution | part 07 `optimal_policy` |
| `rollout` | one-shot lookahead onto the value grid, m = 100 | part 06 `recommend` |
| `pin` | aim at the pin, longest club that does not overshoot | part 07 `pin_policy` |
| `centre` | aim at the green centroid, club closest to that distance | part 07 `centre_policy` |
| `greedy` | the action minimising expected distance to the pin after one shot, penalty landings counted from the redirected point; no lookahead beyond that | new, extensions item 9 in spirit |
| `risk` | grid policy of a value iteration under exponential utility `U = -exp(lambda x strokes)`, lambda = 0.5 per stroke, same draws and tolerance as `grid` | new, extensions item 4 |
| `sparse2` | sparse sampling at depth 2 (Ch 9.4): m1 = 20 landings per action at the first level, the second level restricted to the grid action with m2 = 10, leaf = bilinear grid value | new, extensions item 7 |
| `mcts` | Monte Carlo tree search with UCB1 over clubs and progressive widening over a continuous aim (Ch 9.6): 300 iterations per decision, c = 1.0, widening k = 2, alpha = 0.5, leaf = bilinear grid value | new, extensions item 8 |

Not in this part: the cross-entropy rule (item 9) and goal-objective value iteration (the P(score <= par) variant), both noted as follow-ups in the summary table so the report can say they were considered.

The lambda, m1, m2, iteration budget and UCB constants are benchmark settings fixed here so runs are comparable; slice 8 sweeps lambda over {0.1, 0.5, 1.0} and the MCTS budget over {100, 300, 1000} for the compute figure, nothing else is tuned.

## Cases

A case is one JSON object in `solver/tests/fixtures/benchmark_cases.json`:

```json
{
  "id": "water-carry-weak",
  "hole": {"builder": "water_carry", "args": {"water_from_m": 180, "water_to_m": 200}},
  "player": {"builder": "round_numbers", "args": {"driver_mu_c": 190}},
  "start": {"x": 60.0, "y": 2.5, "lie": "tee"},
  "mode": "drop",
  "n": 2000,
  "expect": [
    {"kind": "action", "approach": "grid", "at": "start", "club_not": "driver"},
    {"kind": "action", "approach": "pin", "at": "start", "club": "driver"},
    {"kind": "order", "lower": "grid", "upper": "pin", "by_at_least": 0.3},
    {"kind": "order", "lower": "grid", "upper": "centre"},
    {"kind": "close", "a": "rollout", "b": "grid", "within": 0.05},
    {"kind": "blowup_order", "lower": "risk", "upper": "grid"}
  ]
}
```

`hole.builder` is `toy` or a function in `benchmark_holes.py`; `hole.number` with `mode` loads a real solved bundle from `out/<hole>/<mode>` instead. `player.builder` is `toy`, `round_numbers` (a synthetic 5-club player with the numbers below) or `file` (`player.json`). `start` defaults to the Black tee. Expectation kinds, all evaluated on paired draws at the case's `n`:

- `order`: `mean[lower] <= mean[upper] + se`, optionally `- by_at_least`; `se` is the standard error of the paired difference.
- `close`: `|mean[a] - mean[b]| <= within + se`.
- `blowup_order`: `p_blowup[lower] <= p_blowup[upper]`.
- `band`: `lo <= mean[approach] <= hi`, used where an independent value exists (the toy's `-U[tee]`, the brute-force Monte Carlo in `toy_hole.py`).
- `action`: the approach's decision at `at` (`start` or an `[x, y, lie]` point) has `club` / `club_not` / `dir_deg_min` / `dir_deg_max` (positive is the golfer's right).

Synthetic holes (`benchmark_holes.py`, all cell 5 m, 70 rows x 24 cols (350 x 120 m), a 60 m fairway on columns 6 to 17 with 30 m rough shoulders either side, tee at (60, 2.5), pin at the green centroid, par 4). The shoulders are there because off the grid is OB, as on the real holes, and a 60 m wide hole put a 6 degree driver off the hole a fifth of the time, which made the grid lay up for the wrong reason:

| builder | geometry | what it tests |
| --- | --- | --- |
| `open_straight` | fairway and shoulders only, round green of radius 12.5 m centred at (60, 330) | no-hazard control: every sensible approach should tie |
| `water_carry` | `open_straight` plus a water band across the full width from `water_from_m` to `water_to_m` | lay up or go for it, decided by the driver carry distribution |
| `ob_side` | the left shoulder is OB (columns 0 to 5, so the OB edge is 30 m left of the tee line), fairway 6 to 17, rough 18 to 23 | the optimal aim is offset away from the OB side |
| `bunker_front` | `open_straight` plus bunkers in the three cells directly short of the green (row 63, columns 11 to 13) | short-side avoidance: the grid plays to the centre or long |

The `round_numbers` player, a nine-club bag with regular gaps so no distance is awkward (`mu_c`, `sigma_theta_deg`, `sigma_d`, `p`, `mu_r`, `sigma_r`): `driver` 200 (overridable), 6, 0.07, 0.10, 15, 8; `5h` 170, 5, 0.06, 0.08, 10, 5; `7i` 140, 4, 0.05, 0.05, 5, 3; `9i` 120, 3.5, 0.05, 0.05, 3, 2; `pw` 100, 3.5, 0.05, 0.05, 2, 1; `sw80` 80, 3.5, 0.06, 0.05, 1.5, 1; `sw60` 60, 3.5, 0.06, 0.05, 1, 1; `sw40` 40, 3.5, 0.06, 0.05, 0.5, 0.5; `sw20` 20, 3.5, 0.06, 0.05, 0.5, 0.5. Lie multipliers and the putting table from the root data contract. These are round numbers chosen for the synthetic cases; they are not the fitted player. The bag is this full because a coarse one produced artefacts the real bag does not have: with driver, 7i, pw, sw50 and sw30 the value grid was non-monotone in distance (a driver that lands 90 to 120 m out was worse than a lay-up), the pin and greedy baselines could not finish on a 12.5 m green (a 30 m shot from 15 m lands off the far side), and the first version with a 100 m shortest club looped off the grid and made the exponential utility diverge.

Cases in v1, with the expectations each carries (the JSON is the source of truth; this list is the intent):

| id | hole, player, start, mode | expectations |
| --- | --- | --- |
| `toy-drop` | toy, toy player, tee, drop | `band` grid within 0.1 of `-U[tee]`; `order` grid <= pin, grid <= centre; `close` rollout to grid 0.05 |
| `toy-replay` | toy, toy player, tee, replay | `band` grid <= brute-force Monte Carlo value + 0.05; `order` grid <= pin |
| `open-straight` | `open_straight`, `round_numbers`, tee, drop | `close` every approach to grid within 0.3; `action` every approach hits the driver from the tee |
| `water-carry-weak` | `water_carry` 180 to 200, driver 190, tee, drop | as in the JSON above |
| `water-carry-strong` | same hole, driver 230, tee, drop | `action` grid hits the driver; `close` grid to pin 0.1; `blowup_order` risk <= grid |
| `ob-left` | `ob_side`, `round_numbers`, tee, drop | `action` grid `dir_deg_min` 2 (at least one step right of the pin; the OB edge is 30 m left of the tee line and the right side is only rough, so the offset is modest); `order` grid <= pin by 0.1 (measured 0.19 on this geometry); `action` risk `dir_deg_min` equal to grid's chosen offset |
| `bunker-front` | `bunker_front`, `round_numbers`, 120 m short of the pin in the fairway, drop | `order` grid <= pin; `close` greedy to grid 0.2 |
| `hole-11-drop-tee` | hole 11 bundle, `player.json`, Black tee, drop | `order` grid <= pin by 0.3, grid <= centre by 0.2; `close` rollout 0.05; `blowup_order` risk <= grid |
| `hole-11-drop-150` | hole 11, fairway point 137 m (150 yd) short of the pin, drop | `order` grid <= pin; `close` sparse2 to grid 0.1 |
| `hole-11-replay-tee` | hole 11, Black tee, replay | `order` grid <= pin; `blowup_order` risk <= grid |
| `hole-10-drop-tee` | hole 10 bundle, Black tee, drop | `order` grid <= pin, grid <= centre |

Hole 12 is listed in the JSON with `"skip_unless_solved": true` and runs once `out/12/drop` exists. The hole 11 numbers already measured by part 07 (grid 4.46, pin 4.87, centre 4.73) set the `by_at_least` margins above; they are not re-derived here.

## Metrics (per case, per approach)

- `mean_strokes`, `std_strokes`, `se_vs_grid` (standard error of the paired difference to `grid`).
- `p_blowup` as in part 07.
- `regret`: the approach's `mean_strokes` minus the smallest `mean_strokes` of any approach on this case.
- `disagreement`: share of a seeded sample of at most 100 playable cells where the approach's decision differs from `grid` (point approaches evaluated at cell centres). A sample, because the online approaches take up to a second per cell and the full set cost 17 minutes of decisions per run.
- `build_s`: seconds to construct the policy (a solve for `grid` and `risk`, zero for the baselines).
- `decide_s`: total seconds spent deciding during the simulation, and `decide_ms_per_shot`.
- `passed`: list of expectation ids met, `failed`: those not met, each with the measured value.

Summary across cases: wins (regret within one `se_vs_grid` of zero counts as a tie), mean regret, mean `p_blowup`, total compute, expectations passed over total. Ranking is by mean regret, ties broken by compute.

## Interfaces

```python
# approaches.py
@dataclass
class Approach:
    id: str
    build: Callable[[Hole, Player, Solution | None, PenaltyMode], Policy]
    point: Callable[[Hole, Player, Solution | None, PenaltyMode], PointPolicy] | None  # continuous variant or None
    needs_solution: bool

PointPolicy = Callable[[float, float, Lie], tuple[str, float]]   # (club name, dir_deg), continuous aim allowed

APPROACHES: dict[str, Approach]   # the eight ids above

def greedy_policy(hole, player, mode, K=200, seed=0) -> Policy
def risk_solution(hole, player, mode, lam=0.5, K=200, tol=0.01, seed=0) -> Solution   # value_iteration.solve(objective=("exp", lam))
def sparse2_point_policy(solution, hole, player, mode, m1=20, m2=10, seed=0) -> PointPolicy
def mcts_point_policy(solution, hole, player, mode, iters=300, c=1.0, k=2.0, alpha=0.5, seed=0) -> PointPolicy

# benchmark.py
@dataclass
class Case: id: str; hole: Hole; player: Player; start: tuple[float, float, Lie]; mode: PenaltyMode; n: int; expect: list[dict]; solution: Solution | None
def load_cases(path: Path, out_dir: Path, ids: list[str] | None = None) -> list[Case]      # builds synthetic holes, loads real bundles, solves on demand when no bundle exists for a synthetic hole (cached in out/benchmark/solutions/ under the hole and player keys, since two cases can share a hole with different players)
def simulate_points(hole, player, policy: PointPolicy, mode, n, seed, start) -> tuple[np.ndarray, float]   # continuous play via online.shots_from_point with one draw per shot; returns strokes and decide_s
def run_case(case: Case, approaches: list[str], seed: int = 0, simulator: str = "cell") -> dict             # metrics per approach, paired draws, expectations checked
def check_expectations(case: Case, metrics: dict, decisions: dict) -> tuple[list[str], list[dict]]
def write_case_table(result: dict, out_dir: Path) -> Path                                                    # out/benchmark/<case>.md and .csv
def write_summary(results: list[dict], out_dir: Path) -> Path                                                # out/benchmark/summary.md and .csv
def plot_strokes_vs_compute(results: list[dict], out_dir: Path) -> Path                                      # one point per (approach, case), x = compute per 1000 plays, y = regret, log x; lambda and MCTS budget sweeps as connected points
```

CLI: `uv run python -m caddie benchmark [--cases id,id] [--approaches id,id] [--n 2000] [--seed 0] [--simulator cell|point|both] [--out out]`. Default: every case that can run, every approach, both simulators where the approach has a point variant.

## Slices

1. **Cases and synthetic holes.** `benchmark_holes.py` builders produce `Hole`s whose lie arrays match the geometry table (water band rows, OB columns, bunker cells, green radius); `load_cases` on the fixture JSON returns every case with a built hole, a player, a start and a non-empty `expect`; a case with an unknown builder raises.
2. **Approach registry.** `APPROACHES` has the eight ids; `grid`, `pin`, `centre` reproduce part 07's policies on the toy; `rollout` agrees with `grid` at 9 of 10 sampled toy cell centres (m = 400). `needs_solution` is false for `pin`, `centre`, `greedy`.
3. **Greedy.** On `open_straight` from the tee, greedy hits the driver at the pin; on the toy, greedy's mean is no better than grid's (paired, n = 2000).
4. **run_case on the cell simulator.** `toy-drop` with every approach that exists so far: metrics have every key above; grid's regret is 0 within `se`; `check_expectations` passes `band`, `order` and `close` and reports a deliberately failing extra expectation with its measured value. `simulate(start=...)` from a non-tee fairway point returns fewer strokes than from the tee.
5. **Point simulator.** `simulate_points` with the grid policy on the toy has a mean within 0.15 of the cell simulator's (the two differ, that is the point); with a point policy that always aims at the pin it agrees with an independent scalar Monte Carlo through `sample_landing` within 0.05.
6. **Risk.** `value_iteration.solve(objective=("exp", 0.5))` on the toy converges and its policy differs from `grid` somewhere near the water; on `water-carry-weak`, `blowup_order` risk <= grid passes and risk's mean is within 0.3 of grid's.
7. **Sparse sampling and MCTS.** `sparse2` agrees with `grid` at 9 of 10 toy cell centres; `mcts` on `open_straight` from the tee returns the driver with an aim within 6 degrees of the pin; both decide a toy point in under 0.5 s.
8. **Report and CLI.** `write_case_table`, `write_summary`, `plot_strokes_vs_compute` write under `out/benchmark/`; the summary ranks by mean regret and lists the two follow-up approaches as "not run"; `uv run python -m caddie benchmark --cases toy-drop,open-straight` exits 0.

## Done when

`uv run python -m caddie benchmark` runs every case in the fixture that has a bundle or a builder, with all eight approaches on the cell simulator and the four point-capable ones (`rollout`, `sparse2`, `mcts`, plus `grid` for reference) on the point simulator, and writes `out/benchmark/summary.md` with the ranking, one table per case, and `out/benchmark/strokes_vs_compute.png`. On the toy and synthetic cases alone it finishes in under 15 minutes on a laptop from a cold solution cache (measured 14 minutes with 100 plays per approach on the point simulator; the ten synthetic solves are most of it, and a warm cache cuts the run to the decisions alone); the hole cases take longer and are reported with their times.

## Pitfalls

- Pair everything. The same seed and `n` for every approach on a case, and the same draw columns per play; otherwise an "order" expectation passing or failing is noise. Report `se_vs_grid` next to every mean.
- Memoise online decisions per `(cell, lie)` on the cell simulator or `mcts` will not finish; on the point simulator the budget per decision is what is being measured, so do not memoise there.
- The point simulator must land through `online.shots_from_point`, never a second copy of the terrain rule; the only new logic is the loop and the stopping rule (green, or `MAX_SIM_SHOTS`).
- Exponential utility changes the Bellman backup, not just the reward: `V(s) = min_a E[exp(lambda x cost) x V(s')]` with `V = exp(lambda x E[putts])` on the green, then the reported value is `log(V) / lambda`. Do not feed `-exp(lambda x strokes)` into the additive backup.
- A failed expectation is a finding, not a test failure: `run_case` records it and the CLI exits 0. Only the slice tests (which use the toy and synthetic cases with margins) fail the suite.
- Hole 12 has no bundle yet. Skip it with a logged reason, do not solve it inside the benchmark.
