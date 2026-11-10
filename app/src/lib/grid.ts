/**
 * Grid lookups on a hole bundle (Ch 8.4). Cell (r, c) has its centre at
 * ((c + 0.5) cell_m, (r + 0.5) cell_m); row 0 is the tee end.
 */
import type { HoleBundle, XY } from './types'

export interface Cell {
  r: number
  c: number
  i: number
}

function clampIndex(k: number, n: number): number {
  return k < 0 ? 0 : k >= n ? n - 1 : k
}

/** The cell containing `p`, clamped to the grid for points outside it. */
export function cellOf(b: HoleBundle, p: XY): Cell {
  const { rows, cols, cell_m } = b.meta
  const c = clampIndex(Math.floor(p.x / cell_m), cols)
  const r = clampIndex(Math.floor(p.y / cell_m), rows)
  return { r, c, i: r * cols + c }
}

export function centreOf(b: HoleBundle, r: number, c: number): XY {
  const { cell_m } = b.meta
  return { x: (c + 0.5) * cell_m, y: (r + 0.5) * cell_m }
}

export function distance(a: XY, b: XY): number {
  return Math.hypot(a.x - b.x, a.y - b.y)
}
