# Part 22: aim where you want

Branch `part/22-aim-target` (on top of part 21). Scope: `app/src/lib/aim.ts`, `app/src/components/AimTarget.tsx`, `app/src/components/AimPanel.tsx`, the `target` and `aimClub` fields in `app/src/store.ts`, an exported `actionOutcome` in `rollout.ts`, a first-shot override in `simulate.ts`, and the call sites in `HoleMap.tsx`, `BallMarker.tsx`, `CaddiePanel.tsx`, `ShotLogger.tsx`, `PlayItOut.tsx`; their tests. Depends on parts 12, 13, 15, 21.

## Purpose

Until now the app only showed the caddie's aim. A golfer wants to point at a spot, as in 18Birdies, and read two numbers: how far it is to that spot, and how far it leaves to the pin. This part adds a target the player can move, in both modes, and shows what is likely to happen from the player's own club distributions if they hit at it.

## Behaviour

- **The target.** A ring on the map. It starts on the caddie's aim. Tapping the map or dragging the ring moves it; from then on the aim is the player's. "Use the caddie's aim" puts it back.
- **Two distances.** A line from the ball to the target and a second line from the target to the pin, each with its distance in yards at its midpoint.
- **The club.** By default the club whose mean total distance from this lie (carry plus roll) is closest to the target distance, tee-only clubs only on the tee. A row of club chips changes it. With the target untouched, the club is the caddie's.
- **What is likely.** For the current club and aim the app draws 200 shots from the player's distribution and shows where they finish as dots on the map (penalty shots in red), the share that finish on the fairway, in the rough, in a bunker, on the green, or in a penalty, and the expected strokes to hole out (one stroke plus the grid value where each ball finishes, the same quantity the rollout uses). The caddie's club and expected strokes stay visible beside it for comparison.
- **Simulate.** The ball is on the chosen tee and cannot be moved; a tap always moves the target. "Play it out" hits the first shot with the player's club and aim, then follows the caddie.
- **Play.** The ball is the GPS fix (still draggable as a correction). A tap moves the target, except when there is no ball yet, when it places the ball. Hit logs the shot with the current club and aim; `recAimDeg` keeps the caddie's aim, so the 30 degree rule of part 15 now has something to compare.
- **Staleness.** The target returns to the caddie's aim when the hole changes or the ball moves more than 15 m from where it was when the target was set.

## Interfaces

```ts
// store.ts
// State gains: target: XY | null (null = the caddie's aim); aimClub: string | null (null = automatic)
// setTarget(p: XY | null), setAimClub(club: string | null), resetAim()

// aim.ts (pure)
export const TARGET_RESET_M = 15
export function meanTotalM(player: Player, club: string, lie: Lie): number
export function clubForDistance(player: Player, lie: Lie, distM: number): string
export interface Aim { club: string; dir_deg: number; target: XY; toTargetM: number; toPinM: number; custom: boolean }
export function resolveAim(b: HoleBundle, player: Player, ball: XY, lie: Lie, rec: { club: string; dir_deg: number }, target: XY | null, aimClub: string | null): Aim

// rollout.ts
export interface ActionOutcome { expected: number; finishes: { x: number; y: number; penalty: boolean }[]; share: Record<'fairway' | 'rough' | 'bunker' | 'green' | 'penalty', number> }
export function actionOutcome(b, player, from, lie, club, dir_deg, mode, n?, seed?): ActionOutcome

// simulate.ts
export function playOut(b, player, from, lie, mode, rng, first?: { club: string; dir_deg: number }): PlayOut
```

## Slices

1. **Store.** `target`, `aimClub`, their setters, `resetAim`, and the staleness rule. Test.
2. **aim.ts.** `meanTotalM`, `clubForDistance`, `resolveAim`. Test by hand-built cases: untouched target equals the caddie's aim; a target 150 m out picks the 150 m club; the driver is never picked off the fairway.
3. **Outcome.** `actionOutcome`: shares sum to 1, the expected value equals the rollout's action value on the same seed, a shot aimed at water has a penalty share above zero.
4. **Play it out from the player's aim.** `playOut` and the histogram take the first action.
5. **Map.** The ring, the two lines with their distances, the dots. A tap moves the target.
6. **Panel.** The aim block: club chips, the two distances, the outcome shares, the caddie's pick with "Use the caddie's aim". Hit logs the current aim.

## Done when

On hole 11 in Simulate: tap a spot in the fairway, read the distance to it and from it to the pin, see the dots spread around it, change the club and watch the dots and the expected strokes change, press Play it out and see the first shot go that way.

## Pitfalls

- The expected strokes for the player's aim come from the stored value grid at the finish points, so they are optimistic: they assume the caddie's play after this shot.
- A target far beyond the longest club still picks the longest club; the dots show the truth.
- Two hundred shots on the main thread is cheap (the worker does tens of thousands); do not route it through the worker.
- The old `AimArrow` and `MapLabels` components are replaced by `AimTarget`; their pure helpers stay.
