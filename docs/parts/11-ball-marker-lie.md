# Part 11: store.ts, BallMarker.tsx, LieButtons.tsx

Branch `part/11-ball-marker-lie`. Scope: `app/src/store.ts`, `app/src/components/BallMarker.tsx`, `app/src/components/LieButtons.tsx`, tests for the store.

## Purpose

The single Zustand store (shape in `app/CLAUDE.md`), placing the ball by click or drag, and the lie override row. Recommendation in M1 is a direct `policyAt` lookup written into the store whenever ball or lie changes.

## Interfaces

```ts
// store.ts
export const useStore = create<State>()(...)
   // actions: setHole(h), setMode(m), setTee(name), setBall(p | null), setLieOverride(l | null), setGps(g | null), setRecommendation(r | null)
   // setTee also sets ball to meta.tees[name] when ball is null or currently equals another tee
   // derived in a subscriber (not in render): whenever ball, lieOverride, or bundle changes and no worker is active (M1), setRecommendation(policyAt(bundle, ball) + valueNearest) -> Recommendation
export interface Recommendation { club: string; dir_deg: number; expected_strokes: number; baseline_pin_strokes?: number; source: 'grid' | 'worker' }

// BallMarker.tsx
export function BallMarker({ map }: { map: maplibregl.Map }): JSX.Element
   // click on the map -> setBall(lonLatToGrid(meta, e.lngLat)); ignore clicks outside the grid
   // draggable maplibregl.Marker; drag end -> setBall
   // when gps is set and the user has not dragged in the last 10 s, the marker follows gps (part 14 sets gps)

// LieButtons.tsx
export function LieButtons(): JSX.Element
   // three toggle buttons: Fairway, Rough, Bunker; a fourth "Auto" clears the override
   // highlighted button = lieOverride ?? lieAt(bundle, ball)
```

## Slices

1. **Store.** Create with the fixed shape; test that `setBall` updates `ball` and nothing else.
2. **Derived recommendation.** Subscriber writes a `Recommendation` with `source: 'grid'` on ball change; test with the toy bundle.
3. **Marker on click.** Click sets the ball; marker appears at the clicked lon/lat; clicking outside the grid does nothing.
4. **Drag.** Drag end updates the ball; marker and store agree.
5. **LieButtons.** Rendered under the map; pressing Rough sets `lieOverride = 3`; Auto clears it; the highlighted button follows `lieAt` when no override.

## Done when

Click the tee on hole 11: the store holds a ball position, a club, a direction and a number; press Rough and the highlight moves.

## Pitfalls

- Keep `policyAt` lookups out of React render; the subscriber pattern (`useStore.subscribe`) avoids recomputing on every repaint.
- Marker `draggable: true` fires `drag` constantly; only act on `dragend`.
