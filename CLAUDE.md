# Caddie: project rules for agents

A personalized golf caddie for Stanford Golf Course holes 10, 11, 12. Hole play is a Markov decision process; a Python solver computes the optimal club and aim from every position offline, and a TypeScript web app shows it, first on a desktop (M1) and then on a phone with GPS (M2). CS 238 final project, Diego Raygada and Hylton Harvey.

Read this file, then the CLAUDE.md of the half you are working in (`solver/CLAUDE.md` or `app/CLAUDE.md`), then the one part file for your task in `docs/parts/`.

## Workflow (non-negotiable)

1. One branch per part file: `part/<nn>-<name>`, e.g. `part/04-mdp`.
2. Within a branch, one commit per slice, in the order the part file lists them. Commit message: `<nn>-<name> slice <k>: <slice title>`.
3. Each slice: write the test first, make it fail, implement, make it pass, commit. Never skip the failing run.
4. Do not touch files outside the part's listed scope. If you need a change elsewhere, stop and say so.
5. Open a PR per branch when every slice is committed. The PR description lists the slices and how to run the checks.
6. Never use em dashes in any text you write (code, comments, docs, commits).
7. Do not invent numbers. Parameter defaults come from the part file or `player.json`; if a value is missing, say so.

## Decisions (frozen; change only by editing this file in a dedicated PR)

| Topic | Decision |
| --- | --- |
| Repo | Monorepo. `solver/` Python (uv). `app/` TypeScript (Vite, React, MapLibre GL, Tailwind, Zustand). Joined only by files in `app/public/data/`. |
| Hosting | No backend. Static on Vercel. PWA with service worker in M2. |
| Coordinates | Hole-local meters. Origin at the Black tee, +y toward the pin, +x to the golfer's right. Lat/lon only in `meta.json` and at the GPS edge. |
| Grid | 5 m cells, row-major, row 0 at the tee end. |
| State | `(cell, lie)`, lie in {tee, fairway, rough, bunker, green}. Water and OB are terrain rules, not states. |
| Action | `(club, direction)`. Directions: pin bearing plus or minus 90 degrees in 2 degree steps, 91 values. Clubs: 13 incl. partial wedges. |
| Transition | Land at sampled carry and lateral; look up lie at landing; add roll scaled by lie. |
| Dispersion | Direction N(0, sigma_theta). Carry = mu_c (1 + sigma_d X), X ~ (1-p) N(0,1) + p N(-2,1). Roll N(mu_r, sigma_r). |
| Data | 50 shots each SW, 9i, 7i, 5-hybrid; 100 driver; 20 rough 7i. Source: STMax launch monitor export. Canonical CSV columns `club, carry_m, total_m, lateral_m, lie, date`. |
| Fit | Conjugate Bayesian update (Ch 4.2) for carry, direction, roll from a Broadie-Ko skill-band prior; the posterior sufficient statistics are stored in `player.json`. scipy MLE for p with mishit mean fixed at -2, p in [0.02, 0.25]. Unsampled clubs linear in carry. |
| Lie | rough: carry x0.9, sigmas x1.3, roll x0.5. bunker: carry x0.8, sigmas x1.6, roll x0. tee = fairway. |
| Putting | Green cells terminal: U = -E[putts](distance to pin) from a Shot Scope make-rate curve. |
| Penalties | `penalty_mode` in {mulligan, drop, replay}. mulligan: rehit from origin, +0. drop: nearest fairway cell on the entry side, +1. replay: from origin, +1. One solve per mode. |
| Solver | Value iteration, gamma = 1, K = 200 fixed Halton draws per club shared across sweeps, stop at residual < 0.01. |
| Online | Rollout lookahead at a continuous point, m = 100 draws per action, leaf = bilinear interpolation of the value grid. Python in M1, TS Web Worker in M2. |
| Evaluation | 2,000 simulated plays per hole per policy. Policies: optimal, pin-longest-club, centre-of-green. Bootstrap the fit 50 times. |
| Output | Per hole per mode: `meta.json, lie.u8, value.f32, club.u8, dir.u8`. |
| Tee and pin | Grid origin and rotation are fixed at the Black tee; the player may choose any tee box in the app (the value grid does not depend on where you start). Pin fixed at the green centroid. |
| App M1 | Heatmap, click-to-place ball, club + arrow + expected strokes, play-it-out animation + histogram. |
| App M2 | GPS, lie override buttons, rollout in a Web Worker, PWA offline, Vercel. |
| Tests | pytest on a 10x10 toy hole; vitest on `grid.ts` and `shot.ts`; GitHub Actions on PR. |

## Data contract (the only interface between halves)

`app/public/data/player.json`:

```json
{
  "handicap": 15,
  "clubs": {
    "driver": {"mu_c": 215.0, "sigma_theta_deg": 6.5, "sigma_d": 0.07, "p": 0.10, "mu_r": 18.0, "sigma_r": 8.0, "sampled": true,
               "stats": {"n": 100,
                         "carry": {"m": 215.0, "kappa": 105.0, "alpha": 53.0, "beta": 11500.0},
                         "theta": {"alpha": 53.0, "beta": 2150.0},
                         "roll":  {"m": 18.0, "kappa": 105.0, "alpha": 53.0, "beta": 3300.0}}},
    "3w":     {"mu_c": 195.0, "sigma_theta_deg": 6.0, "sigma_d": 0.07, "p": 0.09, "mu_r": 14.0, "sigma_r": 7.0, "sampled": false, "stats": null}
  },
  "club_order": ["driver","3w","5h","6i","7i","8i","9i","pw","sw","sw70","sw50","sw30"],
  "lie": {
    "tee":     {"carry": 1.0, "sigma": 1.0, "roll": 1.0},
    "fairway": {"carry": 1.0, "sigma": 1.0, "roll": 1.0},
    "rough":   {"carry": 0.9, "sigma": 1.3, "roll": 0.5},
    "bunker":  {"carry": 0.8, "sigma": 1.6, "roll": 0.0}
  },
  "putting": {"distance_m": [1, 2, 3, 4, 6, 8, 10, 15, 25], "expected_putts": [1.07, 1.41, 1.64, 1.78, 1.85, 1.93, 1.98, 2.15, 2.4]}
}
```

`app/public/data/<hole>/<mode>/meta.json`:

```json
{
  "hole": 11, "par": 4, "penalty_mode": "drop",
  "rows": 90, "cols": 36, "cell_m": 5.0,
  "origin": {"lat": 37.4110, "lon": -122.1780},
  "rotation_deg": 212.0,
  "tee_xy": [90.0, 0.0], "pin_xy": [95.0, 320.0],
  "tees": {"black": [90.0, 0.0], "white": [88.0, 25.0], "blue": [86.0, 60.0]},
  "clubs": ["driver","3w","5h","6i","7i","8i","9i","pw","sw","sw70","sw50","sw30"],
  "directions_deg": [-90, -88, "...", 90],
  "polygons": {"fairway": [[[x, y], "..."]], "green": [], "bunker": [], "water": [], "ob": [], "tee": [], "rough": []}
}
```

`stats` is the conjugate posterior state per sampled club (Normal-Inverse-Gamma for carry and roll with unknown mean and variance; Inverse-Gamma for the direction variance with mean fixed at 0). The point estimates `mu_c`, `sigma_d`, `mu_r`, `sigma_r`, `sigma_theta_deg` are the posterior means derived from `stats` at write time, and the MVP reads only the point estimates. The stretch goal (on-course learning, part 15, not yet written) updates `stats` one shot at a time in the app and recomputes the point estimates; nothing in M1 or M2 depends on `stats` beyond carrying it through. `p` and the lie multipliers are not learned.

Binary files next to it, all `rows x cols`, row-major, little-endian:

| File | dtype | Values |
| --- | --- | --- |
| `lie.u8` | uint8 | 0 out-of-grid, 1 tee, 2 fairway, 3 rough, 4 bunker, 5 green, 6 water, 7 ob |
| `value.f32` | float32 | expected strokes to hole out from the cell centre with the cell's own lie; NaN for out-of-grid |
| `club.u8` | uint8 | index into `meta.clubs`; 255 for terminal or out-of-grid |
| `dir.u8` | uint8 | index into `meta.directions_deg`; 255 for terminal or out-of-grid |

Grid to lat/lon: `x_east = x cos(rot) - y sin(rot)`, `y_north = x sin(rot) + y cos(rot)` with `rot = rotation_deg` in radians, then `lat = origin.lat + y_north / 111320`, `lon = origin.lon + x_east / (111320 cos(origin.lat))`. Exact enough over 600 m. Both halves implement this and are tested against the same three fixture points in `docs/fixtures/geo_points.json`.

## Part index

Solver (branch `part/0x-...`): see `solver/CLAUDE.md`.

| # | File | Module |
| --- | --- | --- |
| 01 | `docs/parts/01-geometry.md` | `solver/caddie/geometry.py` |
| 02 | `docs/parts/02-dispersion.md` | `solver/caddie/dispersion.py` |
| 03 | `docs/parts/03-putting.md` | `solver/caddie/putting.py` |
| 04 | `docs/parts/04-mdp.md` | `solver/caddie/mdp.py` |
| 05 | `docs/parts/05-value-iteration.md` | `solver/caddie/value_iteration.py` |
| 06 | `docs/parts/06-online.md` | `solver/caddie/online.py` |
| 07 | `docs/parts/07-evaluate.md` | `solver/caddie/evaluate.py` |
| 08 | `docs/parts/08-export-cli.md` | `solver/caddie/export.py`, `cli.py` |

App (branch `part/1x-...`): see `app/CLAUDE.md`.

| # | File | Module |
| --- | --- | --- |
| 09 | `docs/parts/09-grid-geo.md` | `app/src/lib/grid.ts`, `geo.ts` |
| 10 | `docs/parts/10-hole-map.md` | `app/src/components/HoleMap.tsx` |
| 11 | `docs/parts/11-ball-marker-lie.md` | `BallMarker.tsx`, `LieButtons.tsx`, store |
| 12 | `docs/parts/12-shot-rollout-worker.md` | `app/src/lib/shot.ts`, `rollout.ts`, `rollout.worker.ts` |
| 13 | `docs/parts/13-caddie-panel-playitout.md` | `CaddiePanel.tsx`, `PlayItOut.tsx` |
| 14 | `docs/parts/14-pwa-gps-deploy.md` | GPS hook, PWA config, Vercel |

Build order: 01, 02, 03, 04, 05, 08 (solver can produce a bundle) then 09, 10, 11, 13 (M1 app) then 06, 07, 12, 14 (online step, evaluation, M2). Hole order: 10, 11, 12.

Repo: https://github.com/draygada/caddie (private). Python 3.12, Node 20. Handicap 15. Driver is always hit off a tee on the simulator; every other club off the mat.

## Course material map

| Chapter | Where |
| --- | --- |
| 4.1 maximum likelihood | `dispersion.py` |
| 7.1 MDP definition, 7.5 value iteration, Eq 7.16 | `mdp.py`, `value_iteration.py` |
| 8.4 bilinear interpolation, Alg 8.6 | `online.py`, `grid.ts` |
| 9.2 rollout lookahead, Alg 9.1 | `online.py`, `rollout.ts` |
| 14.1 performance metrics, 14.3 robustness | `evaluate.py` |
