# Part 09: grid.ts, geo.ts, loader.ts

Branch `part/09-grid-geo`. Scope: `app/src/lib/grid.ts`, `app/src/lib/geo.ts`, `app/src/lib/loader.ts`, `app/src/lib/types.ts`, tests, and the Vite project scaffold (`npm create vite@latest` React + TS, Tailwind, vitest).

## Purpose

Load a hole bundle into typed arrays, look values up at continuous positions (nearest cell and bilinear, Ch 8.4), and convert between grid meters and lat/lon. Pure TypeScript, no React.

## Types (`types.ts`)

```ts
export type Lie = 0 | 1 | 2 | 3 | 4 | 5 | 6 | 7;
export type Mode = 'mulligan' | 'drop' | 'replay';
export interface NIG { m: number; kappa: number; alpha: number; beta: number }
export interface IG { alpha: number; beta: number }
export interface ClubStats { n: number; carry: NIG; theta: IG; roll: NIG }
export interface ClubParams { mu_c: number; sigma_theta_deg: number; sigma_d: number; p: number; mu_r: number; sigma_r: number; sampled: boolean; stats: ClubStats | null }   // stats carried through, unused until part 15
export interface Player { handicap: number; clubs: Record<string, ClubParams>; club_order: string[]; lie: Record<'tee'|'fairway'|'rough'|'bunker', {carry: number; sigma: number; roll: number}>; putting: { distance_m: number[]; expected_putts: number[] } }
export interface Meta { hole: number; par: number; penalty_mode: Mode; rows: number; cols: number; cell_m: number; origin: {lat: number; lon: number}; rotation_deg: number; tee_xy: [number, number]; tees: Record<string, [number, number]>; pin_xy: [number, number]; clubs: string[]; directions_deg: number[]; polygons: Record<string, [number, number][][]> }
export interface HoleBundle { meta: Meta; lie: Uint8Array; value: Float32Array; club: Uint8Array; dir: Uint8Array }
export interface XY { x: number; y: number }
```

## Interfaces

```ts
// grid.ts
export function cellOf(b: HoleBundle, p: XY): { r: number; c: number; i: number }      // clamped to the grid
export function centreOf(b: HoleBundle, r: number, c: number): XY
export function lieAt(b: HoleBundle, p: XY): Lie
export function valueNearest(b: HoleBundle, p: XY): number
export function valueBilinear(b: HoleBundle, p: XY): number       // Alg 8.6 on cell centres; NaN neighbours replaced by nearest finite of the four
export function policyAt(b: HoleBundle, p: XY): { club: string; dir_deg: number } | null   // null on terminal/OUT (255)
export function distance(a: XY, b: XY): number

// geo.ts
export function gridToLonLat(m: Meta, p: XY): { lon: number; lat: number }
export function lonLatToGrid(m: Meta, lon: number, lat: number): XY
export function gridCorners(m: Meta): [[number, number], [number, number], [number, number], [number, number]]   // lon/lat of the 4 grid corners, order TL, TR, BR, BL as MapLibre image sources expect

// loader.ts
export async function loadPlayer(base = '/data'): Promise<Player>
export async function loadBundle(hole: number | 'toy', mode: Mode, base = '/data'): Promise<HoleBundle>
   // fetch meta.json, then the four binaries as ArrayBuffer -> typed arrays; assert lengths equal rows*cols
```

## Slices

1. **Scaffold.** Vite React TS project, Tailwind, vitest configured, `npm test` runs an empty suite. ESLint with the strict TS preset.
2. **Types and cellOf/centreOf.** Tests on a 10 x 10, 5 m meta: `cellOf({x: 12, y: 47})` is `(r 9, c 2)`; clamping at the edges.
3. **valueNearest and policyAt.** Using the toy bundle in `public/data/toy/drop/` (committed by solver part 08; if absent, write a hand-made one with a linear value field). 255 returns null.
4. **valueBilinear.** Value field equal to y: any point returns its y to 1e-6. Corner with NaN neighbours falls back without NaN.
5. **geo.** Round trip to 1e-6 degrees; the three points in `docs/fixtures/geo_points.json` match to 0.5 m; `gridCorners` ordering verified against `rotation_deg = 0` (TL is the max-y, min-x corner).
6. **loader.** Mocked fetch returns the toy files; lengths asserted; throws a clear error on a missing file.

## Done when

`npm test` green; `loadBundle('toy', 'drop')` resolves in the dev server console with `meta.rows * meta.cols === value.length`.

## Pitfalls

- `Float32Array` from `fetch().arrayBuffer()` requires byte offset 0 and a length divisible by 4; `response.arrayBuffer()` gives that. Little-endian matches the solver on x86 and ARM.
- Rotation sign must match `geometry.py` exactly; the fixture points are the arbiter.
