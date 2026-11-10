# Part 10: HoleMap.tsx

Branch `part/10-hole-map`. Scope: `app/src/components/HoleMap.tsx`, `app/src/lib/heatmap.ts`, `app/src/App.tsx` (map mounted, hole and mode pickers), tests for `heatmap.ts`.

## Purpose

Satellite map of the hole, rotated tee-at-bottom, with the hole polygons and the strokes-to-go heatmap drawn over it.

## Interfaces

```ts
// heatmap.ts (pure)
export function colourScale(par: number): (strokes: number) => [number, number, number, number]
   // viridis-like 6-stop ramp, domain [par - 1, par + 3], clamped, NaN -> transparent
export function paintHeatmap(b: HoleBundle, canvas: OffscreenCanvas | HTMLCanvasElement, scale): void
   // one pixel per cell, row 0 at the BOTTOM of the canvas (tee end) so the image source corner order matches gridCorners
export function heatmapDataUrl(b: HoleBundle): string

// HoleMap.tsx
export function HoleMap(): JSX.Element
   // props none; reads bundle, hole, mode from the store (part 11 adds the store; until then use a local useState with the toy bundle)
   // on bundle change: fit bounds to gridCorners, set bearing to meta.rotation_deg so +y points up the screen
   // layers, bottom to top: esri raster tiles; 'heat' image source (opacity 0.55); polygons as a GeoJSON fill layer by lie (fairway, green, bunker, water, ob, tee) with low opacity and 1 px outlines; pin and the SELECTED tee (store.tee) as circle layers
   // children: BallMarker (part 11) rendered inside the map container
```

## Slices

1. **colourScale.** par 4: 3 strokes maps to the first stop, 7 to the last, 5 in between; NaN alpha 0.
2. **paintHeatmap.** Toy bundle painted to a 10 x 10 canvas; pixel (0, 9) (bottom-left) corresponds to cell (0, 0). Test by reading back `getImageData`.
3. **Map mounts.** MapLibre with the Esri raster source, attribution, max zoom 19. Renders in the dev server centered on the toy meta's origin.
4. **Heatmap image source.** Added with `map.addSource('heat', {type: 'image', url, coordinates: gridCorners(meta)})`; re-added on bundle change. Visually aligned with the polygons.
5. **Polygons and markers.** GeoJSON built from `meta.polygons` via `gridToLonLat`; fills per lie; pin and tee circles.
6. **Bearing and fit.** `map.setBearing(meta.rotation_deg)` then `fitBounds` on the corners with padding; the tee is at the bottom of the viewport on load.
7. **Pickers.** Hole (10, 11, 12, toy), mode (mulligan, drop, replay), and tee box (from `meta.tees`) selects in a top bar; hole or mode reloads the bundle; tee only moves the tee marker and the default ball position.

## Done when

Hole 11 (or toy until the solver exists) shows satellite imagery with the creek polygon in blue, the heatmap over it, and the tee at the bottom.

## Pitfalls

- MapLibre image source coordinates are `[TL, TR, BR, BL]` in lon/lat; if the heatmap looks mirrored, the canvas row order or the corner order is flipped, not the data.
- Re-adding an image source: `map.getSource('heat')?.updateImage({url, coordinates})` exists; use it rather than remove and add.
