/**
 * Grid lookups on a hole bundle (Ch 8.4). Cell (r, c) has its centre at
 * ((c + 0.5) cell_m, (r + 0.5) cell_m); row 0 is the tee end.
 */
import type { HoleBundle, Lie, XY } from './types'

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

/** 255 in `club.u8` and `dir.u8` marks a terminal or out-of-grid cell with no action. */
export const NO_ACTION = 255

export function lieAt(b: HoleBundle, p: XY): Lie {
  return b.lie[cellOf(b, p).i] as Lie
}

/** Strokes-to-go of the containing cell; NaN where the cell is not a state. */
export function valueNearest(b: HoleBundle, p: XY): number {
  return b.value[cellOf(b, p).i]
}

/** The optimal club and aim at `p`, or null on terminal and out-of-grid cells. */
export function policyAt(b: HoleBundle, p: XY): { club: string; dir_deg: number } | null {
  const { i } = cellOf(b, p)
  const club = b.club[i]
  const dir = b.dir[i]
  if (club === NO_ACTION || dir === NO_ACTION) return null
  const name = b.meta.clubs[club]
  const dir_deg = b.meta.directions_deg[dir]
  if (name === undefined || dir_deg === undefined) {
    throw new Error(`cell ${i}: club ${club} or dir ${dir} outside meta tables`)
  }
  return { club: name, dir_deg }
}
