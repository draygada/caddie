/** Hand-made bundles for tests: a 10 x 10, 5 m grid with pluggable arrays. */
import type { HoleBundle, Meta } from './types'

export const ROWS = 10
export const COLS = 10
export const CELL_M = 5

export function testMeta(over: Partial<Meta> = {}): Meta {
  const directions_deg: number[] = []
  for (let d = -90; d <= 90; d += 2) directions_deg.push(d)
  return {
    hole: 'toy',
    par: 3,
    penalty_mode: 'drop',
    rows: ROWS,
    cols: COLS,
    cell_m: CELL_M,
    origin: { lat: 0, lon: 0 },
    rotation_deg: 0,
    tee_xy: [27.5, 2.5],
    tees: { black: [27.5, 2.5] },
    pin_xy: [27.5, 47.5],
    clubs: ['test7i'],
    directions_deg,
    polygons: { fairway: [], green: [], bunker: [], water: [], ob: [], tee: [], rough: [] },
    ...over,
  }
}

export function testBundle(over: Partial<HoleBundle> = {}, metaOver: Partial<Meta> = {}): HoleBundle {
  const n = ROWS * COLS
  return {
    meta: testMeta(metaOver),
    lie: new Uint8Array(n).fill(2),
    value: new Float32Array(n).fill(3),
    club: new Uint8Array(n),
    dir: new Uint8Array(n).fill(45),
    ...over,
  }
}
