# Part 19: real player data and full solve

Branch `part/19-real-data`. Scope: `solver/scripts/stmax_to_shots.py`, `solver/tests/test_stmax.py`, `solver/tests/fixtures/stmax_sample.csv`, `solver/data/raw/shots.csv`, the committed toy fixture and its test in `solver/tests/test_export.py`, `app/public/data/player.json`, `app/public/data/{10,11,12}/{drop,replay,mulligan}/`, `app/src/lib/loader.test.ts` (bundle presence), `docs/results.md`. Depends on parts 02, 08, 17, 18.

## Purpose

Replace the sample player with ours, solve all three holes under all three penalty modes, ship every bundle to the app, and produce the numbers the final video quotes. Everything here is running existing code on real data; no new modelling.

## What we need from the launch monitor

Per shot, from the STMax CSV export: club, carry, total distance, offline (lateral) distance, and the date. Nothing else is used by the model; keep the full export anyway in `solver/data/raw/stmax/` in case we want spin or launch direction later.

Shots, from the root decisions: 50 each with SW, 9i, 7i and 5-hybrid, 100 with driver off a tee. Keep every shot, including tops and shanks: the mishit rate `p` is fitted from them, and deleting them makes the policy too aggressive. The 20 rough 7i shots are only possible if the simulator has a rough setting; without it the default rough multipliers stay and the PR says so.

Before writing the converter, ask, do not guess (part 02 rule): the column names and units in the export (yards or meters), and whether a positive offline value means right of the target as the golfer stands.

## Slices

1. **Toy fixture test.** `test_committed_toy_fixture_matches_a_fresh_solve` has failed since part 16. Find whether the committed fixture or the tolerance is stale; regenerate the fixture or tighten the reason in the test, and say which in the PR.
2. **STMax converter.** `scripts/stmax_to_shots.py` maps the export to the canonical CSV, converting yards to meters and flipping the lateral sign if needed, with the answers recorded in a comment at the top. Test on a 5-row golden file cut from the first real export.
3. **Fit.** `caddie fit` on the real shots. Every sampled club passes the part 02 sanity ranges or prints the warning. The PR has a table of sample player against real player per sampled club (mu_c, sigma_theta, sigma_d, p).
4. **Solve.** Holes 10, 11, 12 under drop, replay and mulligan with trees and the tee-only driver. Log sweeps and time per solve; hole 12 is solved for the first time here.
5. **Export and ship.** `caddie export` for all nine bundles into `app/public/data/`, commit them with the real `player.json`. Loader test: every bundle in the picker loads and has the four binary files at the right length.
6. **Results.** `caddie evaluate` per hole and mode with the part 18 decomposition and the 50-refit bootstrap (Ch 14.3); `docs/results.md` collects the tables and figures the video uses.
7. **Benchmark on real holes.** Rerun part 16's real-hole cases with the real player; add the ranking to `docs/results.md`.

## Done when

The deployed app shows holes 10, 11 and 12 in all three modes with our own player, and `docs/results.md` has the evaluation, decomposition, robustness and benchmark tables for all three holes.

## Pitfalls

- Yards: the STMax screen is in yards by default; a missed conversion makes every club 9% short.
- The sample `player.json` and the untracked hole 11 bundle in the working tree are from the sample player; this part overwrites them, so do not commit them before slice 5.
- Hole 12 has not been solved before; if a sweep takes over 10 s, follow the numba rule in `solver/CLAUDE.md`.
