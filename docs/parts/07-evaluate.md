# Part 07: evaluate.py

Branch `part/07-evaluate`. Scope: `solver/caddie/evaluate.py`, `solver/tests/test_evaluate.py`, `solver/out/figures/`.

## Purpose

Quantify the policy (Ch 14.1) against baselines and measure robustness to the dispersion fit (Ch 14.3). Produces the tables and figures for the report.

## Policies

```python
Policy = Callable[[x, y, lie], tuple[club_idx, dir_idx]]

def optimal_policy(solution) -> Policy          # nearest cell lookup in club/dir grids
def pin_policy(hole, player) -> Policy          # dir 0; longest club with mu_c <= distance to pin, else the longest club
def centre_policy(hole, player) -> Policy       # aim at the green centroid; club whose mu_c is closest to that distance
```

## Metrics (per hole, per mode, per policy)

- `mean_strokes`, `std_strokes`, and the full histogram of scores over N plays.
- `p_blowup`: fraction of plays at or above par + 3.
- `disagreement`: fraction of non-terminal cells where the policy's (club, dir) differs from optimal; for pin and centre policies evaluated at cell centres.
- `strokes_saved_per_round`: 18 x (baseline mean - optimal mean) on the three holes averaged, labelled clearly as an extrapolation.

## Interfaces

```python
def simulate(hole, player, policy, mode, n: int, seed: int) -> np.ndarray      # (n,) strokes, using mdp.step logic from the tee
def evaluate_hole(hole, player, solution, mode, n=2000, seed=0) -> dict        # metrics for the three policies
def bootstrap_fit(shots_path, n_boot=50, seed=0) -> list[Player]               # resample shots per club with replacement, refit via part 02
def robustness(hole, players: list[Player], mode) -> dict                      # re-solve per bootstrap Player, report tee-value mean and 5/95 percentiles, and policy-disagreement vs the point-estimate solution
def write_report_tables(results: dict, out_dir: Path) -> None                  # CSV + markdown
def plot_histograms(results, out_dir) / plot_heatmap_with_policy(solution, hole, out_dir) / plot_disagreement_map(...)
```

## Slices

1. **Baseline policies.** On the toy hole, `pin_policy` from the tee returns dir 0 and the only club.
2. **simulate.** Toy hole, optimal policy, n = 5000: mean within 0.1 of `-U[tee]`. This is the key consistency check between value iteration and simulation.
3. **evaluate_hole.** Toy hole: optimal mean <= pin mean <= pin mean + 2; metrics dict has every key above.
4. **Bootstrap.** 5 bootstrap players from the fixture CSV: all parameters finite; spread of driver mu_c under 5%.
5. **Robustness.** Toy hole with 5 bootstraps: tee-value percentiles bracket the point estimate.
6. **Figures.** For hole 11 drop: histogram of the three policies on one axis, heatmap with policy arrows, disagreement map; written to `out/figures/`.

## Done when

`uv run python -m caddie evaluate 11 --mode drop` writes `out/tables/11_drop.md` with the metrics table and three PNGs.

## Pitfalls

- The simulation must use the same `step_batch` logic as the solver (import it, do not reimplement), otherwise mismatch between slice 2's two numbers is a bug you cannot localize.
- Pair the random draws across policies (same seed, same n) so differences are not noise.
