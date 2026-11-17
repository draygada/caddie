# Part 15: shot logging and on-course learning

Branch `part/15-course-learning`. Scope: `app/src/lib/learn.ts`, `app/src/lib/shotLog.ts`, `app/src/components/ShotLogger.tsx`, `app/src/components/LearnBadge.tsx`, the store slice for the log, their tests; in the solver, `load_course_log` in `solver/caddie/dispersion.py`, a `--course-log` flag on `fit` in `cli.py`, and `solver/tests/test_dispersion.py`. Depends on parts 02, 12, 14.

## Purpose

Let the player record what they actually hit and where the ball finished, then use those shots to update their club distributions during the round. This is the stretch goal the data contract already reserved: the conjugate posterior in `player.json` `stats` is updated one shot at a time with the same rule the offline fit uses (Ch 4.2), and the rollout plans with the updated player. Acting on a model while learning it from your own play is model-based reinforcement learning with a Bayesian model (Ch 15 and 16).

## Recording a shot

- **Hit button.** Pressed while standing at the ball. It records the position (GPS fix if GPS is on, else the ball marker), its accuracy, the lie, the club (defaults to the recommended club, one tap to change), the aim (defaults to the recommended aim) and a timestamp. The previous shot, if any, ends here.
- **Finish buttons.** "On the green" closes the last shot at the current position. "Penalty" closes it as a water or OB shot, which is logged but never learned from.
- **Corrections.** Every logged end point can be dragged on the map; a drag sets accuracy to 0 (the player placed it).
- **Storage.** The log persists in `localStorage` through the Zustand persist middleware, so a closed tab or a dead signal loses nothing. One log per round, keyed by date and hole.

## From a logged shot to an observation

For a shot from S to E with aim bearing A, club c and landing lie at E:

```
total     = |E - S|
lateral   = signed distance of E from the aim line through S along A (positive = right)
theta_obs = atan2(lateral, total along A)
carry_est = total - mu_r(c) x roll multiplier of the lie at E
lateral'  = carry_est x tan(theta_obs)        # so update_club_stats' atan2(lateral', carry) recovers theta_obs
update_club_stats(stats_c, carry_est, total, lateral')
```

The course only shows where the ball stopped, so carry is estimated by subtracting the club's mean roll; this mixes roll noise into the carry variance, and the PR says so. A shot is skipped (logged, not learned) when either end has GPS accuracy worse than `MAX_LEARN_ACCURACY_M = 10`, when it was a penalty, when it started on the green, or when the aim was changed by more than 30 degrees from the recommendation after the shot (the player was not aiming where the log says).

Clubs whose `stats` is null in `player.json` (interpolated clubs) start from `statsFromParams(params, kappa = 5)`, a prior worth 5 pseudo-shots centred on the current point estimates, the same weight as the offline prior.

## Interfaces

```ts
// learn.ts (pure, no React)
export function updateNig(s: NIG, x: number): NIG
export function updateIg(s: IG, theta: number): IG
export function updateClubStats(s: ClubStats, carry: number, total: number, lateral: number): ClubStats
export function paramsFromStats(s: ClubStats, p: number): ClubParams
export function statsFromParams(c: ClubParams, kappa?: number): ClubStats
export function learnedPlayer(base: Player, observations: Observation[]): Player

// shotLog.ts
export interface LoggedShot { start: XY; end: XY | null; startAcc: number; endAcc: number | null; lie: Lie; club: string; aimDeg: number; t: number; outcome: 'normal' | 'penalty' | 'green' }
export function toObservation(b: HoleBundle, player: Player, s: LoggedShot): Observation | null   // null when skipped, with the reason
export function exportLog(log: LoggedShot[]): Blob                                                  // JSON download
```

```python
# dispersion.py
def load_course_log(path: Path, hole: Hole) -> dict[str, list[tuple[float, float, float]]]   # club -> (carry_est, total, lateral') with the same skip rules
# cli: fit --course-log PATH [--course-log PATH ...] folds these after the simulator shots
```

## Slices

1. **learn.ts.** Port of the part 02 updates. Test: reproduces every step of `docs/fixtures/stats_updates.json` to 1e-9.
2. **statsFromParams.** Round trip: `paramsFromStats(statsFromParams(c), c.p)` returns `c`'s point estimates to 1e-9.
3. **Observation.** `toObservation` on hand-built shots: straight 150 m on fairway, 10 m right, penalty, poor accuracy, aim changed. Each gives the expected numbers or the expected skip reason.
4. **Log store and persistence.** Hit, finish and drag actions; reload restores the log (jsdom localStorage).
5. **ShotLogger UI.** Hit button, club chips with the recommended club preselected, finish buttons, logged shots drawn as thin lines on the map with draggable ends. 44 px targets; usable one-handed.
6. **Learning in the rollout.** A "Use my course shots" toggle (off by default for the demo). When on, the worker receives `learnedPlayer` and the badge shows "Learned from N shots". The value grid is not re-solved; the badge says so in its tooltip.
7. **Export and offline refit.** Download the log as JSON; `fit --course-log` folds it into the offline fit. Test: a log of 20 synthetic shots moves the posterior the same amount in Python and TS.
8. **Landing prompt (optional).** With GPS on, if the player has stayed within 5 m for 20 s at least 20 m from the last Hit, show a "Ball here?" prompt that records a Hit on tap. Never records without a tap.

## Done when

On the course, a full hole logged with Hit and finish buttons, exported, and folded into `fit --course-log` gives a player whose changed clubs are exactly the clubs hit.

## Pitfalls

- Phone GPS error (often 5 to 10 m) is close to the dispersion being learned; that is why poor fixes are skipped and drags are trusted.
- The aim is assumed, not observed. If the player ignores the recommendation without updating the aim, aiming error is learned as dispersion.
- `p` and the lie multipliers are not learned (root contract). Mishits on the course widen `sigma_d` instead.
- Do not let learning change the stored `player.json`; the learned player lives in the log and is recomputed on load.
