# Part 06: online.py

Branch `part/06-online`. Scope: `solver/caddie/online.py`, `solver/tests/test_online.py`.

## Purpose

Recommend an action at an arbitrary continuous position (not a cell centre) with an optional lie override: rollout lookahead (Ch 9.2, Alg 9.1) with the leaf value taken from the offline grid by bilinear interpolation (Ch 8.4, Alg 8.6). This is the reference implementation that `app/src/lib/rollout.ts` must match on a fixed seed.

## Equation

```
Q(x, a) = (1/m) sum_{j=1..m} [ r_j + U_interp(x'_j) ]
a* = argmax_a Q(x, a)
```

Depth is 1 shot of lookahead followed by the grid value at the landing; that is the "hybrid" form on textbook page 185 (value function at the leaves instead of a rollout policy).

## Interfaces

```python
def bilinear(U: np.ndarray, rows: int, cols: int, cell_m: float, x: np.ndarray, y: np.ndarray) -> np.ndarray
    # Alg 8.6 on the cell-centre lattice; clamp x, y to the lattice; NaN neighbours are replaced by the nearest non-NaN of the four, and if all four are NaN return the OB value (strokes at the nearest non-OUT cell + 1)

@dataclass
class Recommendation:
    club: str; dir_deg: float; expected_strokes: float
    q_by_action: np.ndarray          # (n_clubs, n_dirs) for the app's optional display
    baseline_pin_strokes: float      # Q of aim-at-pin with the longest club that reaches

def recommend(solution: Solution, hole: Hole, player: Player, x: float, y: float, lie: Lie | None, mode: PenaltyMode, m: int = 100, seed: int = 0) -> Recommendation
    # lie None -> hole.lie at the containing cell
    # sample m landings per action with fresh Halton draws (seeded), apply step logic from mdp.py on the continuous point (reuse landing_offsets and the terrain rule, but start from (x, y) not a cell centre)
    # leaf value = bilinear(solution.U, ..., x', y') with the landing cell's own lie; penalty landings use the redirected cell's value

def sample_sequence(solution, hole, player, x, y, mode, rng) -> list[dict]
    # plays the hole from (x, y) following the grid policy (nearest cell) until a green cell, then adds E[putts]; returns the list of shots {club, dir, from_xy, to_xy, lie, reward} for the app's play-it-out animation reference
```

## Slices

1. **Bilinear.** On a 3 x 3 grid with values equal to y, interpolation at any point returns y to 1e-6. NaN handling tested on a corner.
2. **Recommend at a cell centre.** On the toy hole, `recommend` at a cell centre returns the same club and direction as the policy grid for 9 of 10 sampled cells (m = 400).
3. **Recommend between cells.** At the midpoint of two cells whose policies differ, the expected strokes is between the two cell values.
4. **Lie override.** From a fairway point with `lie=ROUGH`, expected strokes is higher than with `lie=None`.
5. **Fixture for the TS port.** Write `docs/fixtures/shot_samples.json`: for seed 42 and the toy club from (25, 25) at dir 10, the first 20 landing (x, y) pairs. `rollout.ts` must reproduce them to 1e-3.
6. **sample_sequence.** On the toy hole, sequences end on the green within 12 shots, 99% of the time.

## Done when

`uv run python -m caddie recommend 11 --x 90 --y 180 --mode drop` prints a club, a direction, and expected strokes in under 1 s.

## Pitfalls

- Fresh draws here, not the shared value-iteration draws, otherwise the same 200 landings every call look oddly deterministic in the UI.
- The baseline "pin with longest reaching club" must use the same m draws so the comparison is paired.
