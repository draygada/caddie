# Part 12: shot.ts, rollout.ts, rollout.worker.ts

Branch `part/12-shot-rollout-worker`. Scope: `app/src/lib/rng.ts`, `app/src/lib/shot.ts`, `app/src/lib/rollout.ts`, `app/src/workers/rollout.worker.ts`, tests. Depends on solver part 06's fixture `docs/fixtures/shot_samples.json`.

## Purpose

The generative shot model in TypeScript (used by play-it-out in part 13 and by the on-course recommendation in M2), the rollout lookahead (Ch 9.2) matching `online.py`, and a Web Worker so it runs off the main thread.

## Interfaces

```ts
// rng.ts
export function mulberry32(seed: number): () => number          // uniform [0, 1)
export function normal(rng: () => number): number               // Box-Muller

// shot.ts
export interface Landing { x: number; y: number; lie: Lie; reward: number; next: XY }   // next = after terrain rule
export function sampleShot(b: HoleBundle, player: Player, from: XY, fromLie: Lie, club: string, dir_deg: number, mode: Mode, rng: () => number): Landing
   // mirrors mdp.step_batch for one draw:
   // theta = sigma_theta * lieMult.sigma * normal; X = rng() < p ? normal - 2 : normal
   // carry = mu_c * lieMult.carry * (1 + sigma_d * lieMult.sigma * X)
   // b = atan2(pin.x - from.x, pin.y - from.y) (bearing to the pin); land = from + carry * (sin(b+dir+theta), cos(b+dir+theta)); landing lie from lieAt
   // roll = (mu_r + sigma_r * normal) * lieMult.roll(from) * rollMult(landingLie); final = land + roll * aimUnit
   // terrain rule by mode exactly as part 04; drop uses the nearest fairway/rough cell on the tee side (computed on the fly with a small search since drop_index is not shipped)
export function expectedPutts(player: Player, d_m: number): number

// rollout.ts
export interface RolloutResult { club: string; dir_deg: number; expected_strokes: number; baseline_pin_strokes: number; q: Float32Array /* clubs x dirs */ }
export function recommend(b: HoleBundle, player: Player, from: XY, lie: Lie, mode: Mode, m = 100, seed = 1): RolloutResult
   // for each club (prune mu_c > 1.3 * dist to pin) and each of the 91 directions: Q = mean over m of (reward + valueBilinear(next)); terminal next uses expectedPutts
   // baseline: dir 0 with the longest club whose mu_c <= dist to pin

// rollout.worker.ts
// message in: { bundle (structured-cloned once, cached), player, from, lie, mode, m, seed, requestId }
// message out: { requestId, result }
// drops stale results: only the latest requestId is posted back
```

## Slices

1. **rng.** mulberry32(42) first three values match the Python fixture's documented uniforms (write them into `shot_samples.json` from Python using the same algorithm; the Python side ships a tiny mulberry32 too, see part 06 slice 5).
2. **sampleShot parity.** Toy club from (25, 25), dir 10, seed 42: first 20 landing points match `shot_samples.json` to 1e-3.
3. **Terrain rules.** Water and OB cells on the toy bundle: mulligan, drop, replay behave as in part 04 slice 5.
4. **recommend parity.** On the toy bundle at a cell centre with m = 400, club and direction equal `policyAt` for 9 of 10 sampled cells.
5. **Worker.** Vite worker import (`new Worker(new URL('../workers/rollout.worker.ts', import.meta.url), {type: 'module'})`); request/response round trip in a test with a mocked worker; stale request dropped.
6. **Store wiring.** When `useStore.getState().useWorker` is true (set by part 14), ball or lie changes post to the worker and the response becomes the `Recommendation` with `source: 'worker'`; otherwise the grid lookup from part 11 stays.

## Done when

In the dev server with `useWorker` forced true, dragging the ball updates the club and expected strokes within 200 ms with no frame drops in the Performance panel.

## Pitfalls

- Python's `arctan2` and JS `Math.atan2` agree; `Math.sin` of degrees does not, convert to radians once.
- Keep `bundle` out of every message after the first; structured-cloning 100 KB per drag is what causes jank, not the math.
