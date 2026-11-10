# Part 05: value_iteration.py

Branch `part/05-value-iteration`. Scope: `solver/caddie/value_iteration.py`, `solver/tests/test_value_iteration.py`.

## Purpose

Solve the hole MDP offline (Ch 7.5, Alg 7.8) and emit the value grid and greedy policy grids.

## Equation

Undiscounted, gamma = 1. For each non-terminal cell i with its own lie, Eq 7.16 with the expectation over the K fixed draws:

```
U_{k+1}(i) = max_{(club, dir)} [ (1/K) sum_j ( r_j + U_k(next_j) ) ]
```

where `(next_j, r_j) = step_batch(...)` for draw j. Terminal cells keep `U = terminal_values`. Stop when `max |U_{k+1} - U_k| < tol`.

Because `r` is -1 or -2 and gamma = 1, initialize `U_0 = -par - 2` everywhere (pessimistic) so values rise monotonically; this makes the residual check meaningful and avoids a transient optimistic policy.

## Interfaces

```python
@dataclass
class Solution:
    hole: int
    mode: PenaltyMode
    U: np.ndarray          # float32 (rows*cols,), strokes-to-go as a POSITIVE number (= -value), NaN on OUT
    club: np.ndarray       # uint8, 255 on terminal/OUT
    dir: np.ndarray        # uint8, 255 on terminal/OUT
    sweeps: int
    residual_history: list[float]

def bellman_backup(U: np.ndarray, hole, player, tables, mode, candidates: np.ndarray) -> tuple[np.ndarray, np.ndarray, np.ndarray]
    # one full sweep over all non-terminal, non-OUT cells
    # for each (club, dir) in candidates: next, r = step_batch(all cells); q = (r + U[next]).mean(axis=1)
    # track running max and argmax across actions; returns (U_new, best_club, best_dir)
    # memory: process actions in a loop, cells vectorized; never materialize (cells x actions x K)

def solve(hole: Hole, player: Player, mode: PenaltyMode, K: int = 200, tol: float = 0.01, max_sweeps: int = 100, seed: int = 0, log_every: int = 5) -> Solution

def sweep_order(hole: Hole) -> np.ndarray
    # (optional, Ch 7.6 asynchronous VI) cell indices sorted by decreasing y so backups near the green happen first within a sweep; Gauss-Seidel in-place update halves the sweep count. Only if the synchronous version is slower than 10 s per sweep on hole 12.
```

## Slices

1. **Single backup on the toy hole.** From `U_0`, one sweep raises every non-terminal cell's value (less negative). Terminal cells unchanged.
2. **Convergence on the toy hole.** `solve(toy, mode="replay")` converges under 60 sweeps; residual history is non-increasing after sweep 3; tee value is at least as good as `brute_force_value_at_tee("replay")` minus 0.05.
3. **Policy sanity on the toy hole.** The cell directly behind the bunker row aims around it (dir != 0) or lays up; cells in column 8 (next to the OB column) aim left (dir < 0).
4. **Mode ordering.** For the toy hole, tee value satisfies `mulligan <= drop <= replay` in strokes-to-go.
5. **Hole 10 end to end.** Using `build_hole(10)` and `out/player.sample.json`: solve converges, runtime logged per sweep, `solver/out/10_drop_value.png` heatmap written with the policy arrows subsampled every 3 cells. Target under 2 minutes total on a laptop.

## Done when

Heatmap for hole 10 shows strokes-to-go rising in bunkers and rough, close to par at the Black tee for `drop`, and arrows that bend away from trouble.

## Pitfalls

- `U[next]` gathers with a `(N, K)` index array; make sure `next` is int64 and flat.
- NaN on OUT cells must never enter a max; mask them before the gather (treat as the OB rule in `step_batch`, which already redirects).
- Do not compare `U` against Stauffer and Guillot numbers; different player, different course.
