# Part 20: robustness benchmark

Branch `part/20-robustness-benchmark`. Scope: `solver/caddie/benchmark.py` (a `robustness` run), the `benchmark --robust` flag in `cli.py`, `solver/tests/test_benchmark.py`, `solver/out/benchmark/robust/`, and the robustness section of `docs/results.md`. Depends on parts 16 and 19.

## Purpose

Part 16 grades every method on the same model the methods plan with, which flatters the model-based ones. This part asks the question that matters on the course: when the model of the player is slightly wrong, which method still chooses well? Every approach plans with the point fit of our player and is scored on players refitted from bootstrap resamples of our shots (Ch 14.3), which stand in for the true player we do not know.

## Method

- Truth players: `B = 20` bootstrap refits of `shots.csv` (resample shots within each club, refit with part 02).
- Planning player: the point fit. Grid solutions are solved once with it; rollout, sparse sampling and MCTS plan with it; nothing is re-solved per truth player.
- Simulation: the point simulator (part 16 slice 5), real-hole cases only (holes 10, 11, 12 from the tee and from 150 yards), `n = 500` paired plays per case per truth player.
- Score: regret against the best approach on each (case, truth player), averaged over truth players; report mean and the spread across truth players.

The ranking is "best under model error"; it is still not a field test, which would need roughly 35 plays of one hole per policy to separate a 0.4 stroke gap and thousands for the 0.05 gaps among the top methods.

## Slices

1. **Bootstrap players.** Deterministic given a seed; each refit has every club. Reuse `bootstrap_fit` from part 07.
2. **Robust run.** For one case and two truth players, every approach returns a regret and the planning player is never replaced by the truth player (test by checking the policy objects are identical across truths).
3. **Report.** Table: approach, mean regret, spread across truths, cases won; written to `solver/out/benchmark/robust/summary.md` and copied into `docs/results.md`.
4. **Full run.** Holes 10, 11, 12 with our player; record the wall time in the PR.

## Done when

`docs/results.md` has the robustness ranking alongside the part 16 ranking, with one paragraph on whether they agree.

## Pitfalls

- If a truth player is drawn from the same shots as the planning player, the spread understates real error; say so in the report rather than inflating it.
- Twenty truths times eight approaches is the expensive part; cache the grid solution and reuse paired draws across approaches as part 16 does.
