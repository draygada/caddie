# app/ rules

Vite + React 18 + TypeScript, strict mode. Read the root `CLAUDE.md` first.

## Setup

```
cd app
npm install
npm run dev          # http://localhost:5173
npm test             # vitest
npm run build
```

Dependencies: react, react-dom, maplibre-gl, zustand, tailwindcss. Dev: vitest, @testing-library/react, vite-plugin-pwa (part 14 only). Nothing else without saying why in the PR.

## Conventions

- `src/lib/` is pure TypeScript with no React and no DOM except `fetch`. Everything in it is unit-tested.
- `src/components/` is React. Components read from the Zustand store and never fetch directly; loading lives in `src/lib/loader.ts` (part 09).
- One store, `src/store.ts`, created in part 11. Shape is fixed there; other parts add fields only where their part file says.
- Units: meters everywhere in `lib/` and the store. Convert to yards only inside a component's render.
- Grid coordinates match the solver: `x` right, `y` toward the pin, cell `(r, c)` centre at `((c + 0.5) * cell_m, (r + 0.5) * cell_m)`. Row 0 is the tee end.
- Typed arrays: `lie: Uint8Array`, `value: Float32Array`, `club: Uint8Array`, `dir: Uint8Array`, each length `rows * cols`, index `r * cols + c`.
- Randomness in `lib/shot.ts` uses a seedable PRNG (mulberry32) so tests are deterministic and so Python and TS can be compared on the same seed via the fixture in `docs/fixtures/shot_samples.json`.
- No `any`. No default exports except components. Tailwind for layout; no CSS files beyond `index.css`.
- Satellite tiles: Esri World Imagery, `https://server.arcgisonline.com/ArcGIS/rest/services/World_Imagery/MapServer/tile/{z}/{y}/{x}`, attribution "Esri, Maxar, Earthstar Geographics". Max zoom 19.

## Data

`public/data/player.json` and `public/data/<hole>/<mode>/{meta.json, lie.u8, value.f32, club.u8, dir.u8}` are produced by the solver's `export.py` and committed. The app never writes them. Until the solver exists, part 09 ships a hand-made fixture bundle for a 10 x 10 toy hole in `public/data/toy/drop/`.

## Store shape (fixed in part 11)

```ts
type State = {
  hole: 10 | 11 | 12 | 'toy';
  mode: 'mulligan' | 'drop' | 'replay';
  tee: string;                      // key into meta.tees, default 'black'
  player: Player | null;
  bundle: HoleBundle | null;        // meta + typed arrays
  ball: { x: number; y: number } | null;     // grid meters
  lieOverride: Lie | null;
  gps: { x: number; y: number; accuracy_m: number } | null;   // part 14
  recommendation: Recommendation | null;     // from policy grid (M1) or worker (M2)
  setHole, setMode, setTee, setBall, setLieOverride, setGps, setRecommendation
};
```

## Definition of done per part

All slices committed, `npm test` green, `npm run build` clean with no TypeScript errors, and the part's "Done when" line satisfied in the browser.
