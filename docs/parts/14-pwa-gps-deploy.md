# Part 14: GPS, PWA, deploy (Milestone 2)

Branch `part/14-pwa-gps-deploy`. Scope: `app/src/hooks/useGps.ts`, `app/src/components/GpsBadge.tsx`, `app/vite.config.ts` (PWA plugin), `app/public/manifest.webmanifest`, `vercel.json`, `.github/workflows/ci.yml`. Depends on parts 11 and 12.

## Purpose

Make the app usable on the course: live position, accuracy indicator, lie override already built, rollout in the worker, offline cache, and a public URL.

## Interfaces

```ts
// useGps.ts
export function useGps(enabled: boolean): void
   // navigator.geolocation.watchPosition({ enableHighAccuracy: true, maximumAge: 2000, timeout: 10000 })
   // on each fix: setGps({ ...lonLatToGrid(meta, lon, lat), accuracy_m: coords.accuracy }); if the fix is inside the grid and the user has not dragged the ball in 10 s, setBall(same)
   // sets useStore.useWorker = true while enabled
   // on error: setGps(null) and surface the error text in GpsBadge

// GpsBadge.tsx
export function GpsBadge(): JSX.Element
   // toggle button "GPS" on/off; shows accuracy in meters; draws an accuracy circle layer around the ball when gps is set
```

PWA: `vite-plugin-pwa` with `registerType: 'autoUpdate'`, precache the app shell and `public/data/**`, runtime cache the Esri tile URL pattern with `CacheFirst`, 500 entries, 30 days. Manifest: name "Caddie", display standalone, portrait, icons 192 and 512.

Tile pre-warm: on first load of a hole, fetch the tiles covering `gridCorners` at zooms 16 to 18 so they are cached before walking out (roughly 100 to 200 tiles per hole).

Vercel: project root `app/`, build `npm run build`, output `dist/`. `vercel.json` adds `Cache-Control: public, max-age=31536000, immutable` for `/data/**`.

CI: GitHub Actions on PR: `uv run pytest` in `solver/`, `npm ci && npm test && npm run build` in `app/`.

## Slices

1. **useGps.** Mocked `navigator.geolocation`: fixes flow into the store; error path sets null.
2. **Follow rule.** A drag within the last 10 s blocks GPS from moving the ball; test with fake timers.
3. **GpsBadge and accuracy circle.** Visible toggle; circle radius equals `accuracy_m` in meters on the map (use a GeoJSON polygon approximation of a circle, 32 points).
4. **PWA config.** `npm run build` emits `sw.js` and the manifest; Lighthouse PWA audit passes installable.
5. **Tile pre-warm.** After bundle load, tiles for the three zooms are requested; verify count in the Network panel; cache hit on reload with the network disabled.
6. **Deploy and CI.** Vercel preview on PR, production on main; CI workflow green.

## Done when

On a phone with airplane mode on, after one online load: open the home-screen app, GPS on, walk 20 m, the ball moves, the recommendation updates, lie buttons work.

## Pitfalls

- iOS Safari requires HTTPS and a user gesture before `watchPosition` resolves; the GPS toggle is that gesture.
- Airplane mode disables GPS on some Android phones; test with Wi-Fi and mobile data off instead.
- `maximumAge: 0` drains the battery; 2000 ms is fine for walking pace.
