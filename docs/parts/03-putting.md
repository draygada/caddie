# Part 03: putting.py

Branch `part/03-putting`. Scope: `solver/caddie/putting.py`, `solver/tests/test_putting.py`, `solver/data/raw/putting.csv`.

## Purpose

Expected putts as a function of distance to the pin, from a make-rate table. Used as the terminal value on green cells.

## Inputs

`putting.csv` with header `distance_ft_lo,distance_ft_hi,make_pct` for the player's handicap band, from Shot Scope (via MyGolfSpy 2025). Example rows for a 15 handicap: `0,3,93`, `3,6,59`, `6,9,36`, `9,12,22`, `12,18,16`, `18,24,9`, `24,30,7`, `30,60,2`.

## Model

Expected putts from distance d:

```
E[putts](d) = 1 * make(d) + (1 - make(d)) * (1 + E[putts](leave(d)))
```

with `leave(d)` = expected leave distance after a miss. Shot Scope gives only a 30 ft lag leave (7.8 ft at 25 hcp, 4.6 ft at scratch). Use `leave(d) = max(0.6 m, 0.12 d)` and iterate the recursion to a fixed point on a 0.25 m grid from 0 to 40 m. Beyond 40 m, extrapolate linearly in d with the slope at 40 m.

## Outputs

```python
@dataclass
class PuttingTable:
    distance_m: np.ndarray        # 0.25 m grid
    expected_putts: np.ndarray

    def __call__(self, d_m: float | np.ndarray) -> np.ndarray   # linear interpolation, clamped
```

## Interfaces

```python
def load_make_table(path: Path) -> tuple[np.ndarray, np.ndarray]   # bin midpoints in meters, make prob
def make_prob(d_m: np.ndarray, mids_m, probs) -> np.ndarray          # linear interp, 1.0 at 0, clamped at the last bin
def build_putting_table(path: Path, leave_frac: float = 0.12, leave_min_m: float = 0.6) -> PuttingTable
```

## Slices

1. **Loader.** Parse the CSV; midpoints converted feet to meters.
2. **Make probability interpolation.** Test: make(0) = 1, make(1.5 m) between 0.5 and 0.8, monotone decreasing.
3. **Fixed-point recursion.** Test: E[putts](0.3 m) < 1.1; E[putts](3 m) between 1.6 and 2.0; E[putts](12 m) between 1.9 and 2.3; monotone increasing in d. Converges in under 50 iterations.
4. **Serialize.** `to_json()` produces the `putting` block of `player.json` at the 9 distances listed in the root contract.

## Done when

`PuttingTable` plot in `solver/out/putting.png` is smooth and monotone, and the 9-point JSON block matches the root contract shape.
