# Part 13: CaddiePanel.tsx, PlayItOut.tsx

Branch `part/13-caddie-panel-playitout`. Scope: `app/src/components/CaddiePanel.tsx`, `app/src/components/PlayItOut.tsx`, `app/src/components/AimArrow.tsx`, `app/src/lib/simulate.ts`, tests for `simulate.ts`. Depends on parts 11 and 12 (`shot.ts`).

## Purpose

The recommendation display and the play-it-out demo: one animated sequence, then a histogram of 1,000 simulated scores from the current ball position.

## Interfaces

```ts
// simulate.ts
export interface Shot { from: XY; to: XY; club: string; dir_deg: number; lie: Lie; reward: number }
export function playOut(b: HoleBundle, player: Player, from: XY, lie: Lie, mode: Mode, rng): { shots: Shot[]; strokes: number }
   // follow policyAt (nearest cell) until a green cell, then add expectedPutts rounded by sampling: 1 putt with prob make, else 2, else 3 (use the make curve from expectedPutts inverse: p1 = 2 - E, clamped)
   // cap at 12 shots
export function histogram(b, player, from, lie, mode, n = 1000, seed = 7): Map<number, number>   // strokes -> count

// AimArrow.tsx
export function AimArrow({ map }): JSX.Element
   // a GeoJSON line layer from the ball along dir_deg for the recommended club's mu_c, with a small dispersion ellipse (1 sigma) at the end

// CaddiePanel.tsx
export function CaddiePanel(): JSX.Element
   // reads recommendation, ball, bundle, player
   // shows: club (large), aim as "12 deg left of pin" with the arrow on the map, "Expected strokes from here: 3.4", and below it "Aim at pin with <club>: 3.7" when baseline_pin_strokes exists
   // distances to pin in yards; a Play it out button

// PlayItOut.tsx
export function PlayItOut(): JSX.Element
   // on click: playOut once; animate the ball marker hopping shot to shot, 600 ms each, drawing the path as a dashed line; then show the score for that sequence
   // then histogram(n = 1000) rendered as bars (par - 2 .. par + 4, overflow bins), mean and p(blow-up) under it
   // Reset clears the path
```

## Slices

1. **playOut.** Toy bundle: ends within 12 shots, strokes between 2 and 10, deterministic for a seed.
2. **histogram.** 1000 runs on the toy bundle: counts sum to 1000; mean within 0.3 of `valueNearest` at the start point.
3. **CaddiePanel.** Renders club, aim text, expected strokes from the store; yards conversion tested.
4. **AimArrow.** Line layer follows the recommendation; ellipse sized from `sigma_theta` and `sigma_d`.
5. **Animation.** Marker hops along `shots`; path drawn; score shown.
6. **Histogram view.** Bars and summary line; updates when the ball moves and the button is pressed again.

## Done when

From the hole 11 tee: press Play it out, watch a drive, an approach, and putts, see "4" or "5", then a histogram centred near the expected strokes shown in the panel.

## Pitfalls

- The histogram's mean should match the panel's expected strokes to within ~0.3; a larger gap means `shot.ts` and the solver's `step_batch` disagree, go back to part 12 slice 2.
- Animate with `requestAnimationFrame` interpolation between `from` and `to`, not setInterval.
