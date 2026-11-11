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

/**
 * Bilinear interpolation of the value grid at `p` (Alg 8.6), using the four cell
 * centres around `p`. Points beyond the outermost centres are clamped to them. A NaN
 * neighbour takes the value of the nearest finite neighbour of the four; the result is
 * NaN only when all four are NaN.
 */
export function valueBilinear(b: HoleBundle, p: XY): number {
  const { rows, cols, cell_m } = b.meta
  // continuous cell coordinates where integer k is the centre of row/col k
  const u = Math.min(Math.max(p.x / cell_m - 0.5, 0), cols - 1)
  const v = Math.min(Math.max(p.y / cell_m - 0.5, 0), rows - 1)
  const c0 = Math.min(Math.floor(u), cols - 2)
  const r0 = Math.min(Math.floor(v), rows - 2)
  const a = u - c0 // weight toward c0 + 1
  const g = v - r0 // weight toward r0 + 1

  const idx = [r0 * cols + c0, r0 * cols + c0 + 1, (r0 + 1) * cols + c0, (r0 + 1) * cols + c0 + 1]
  const w = [(1 - a) * (1 - g), a * (1 - g), (1 - a) * g, a * g]
  const vals = idx.map((i) => b.value[i])

  let nearestFinite = NaN
  let best = Infinity
  for (let k = 0; k < 4; k++) {
    if (!Number.isFinite(vals[k])) continue
    const dc = (k % 2) - a
    const dr = Math.floor(k / 2) - g
    const d = dc * dc + dr * dr
    if (d < best) {
      best = d
      nearestFinite = vals[k]
    }
  }
  if (!Number.isFinite(nearestFinite)) return NaN

  let sum = 0
  for (let k = 0; k < 4; k++) sum += w[k] * (Number.isFinite(vals[k]) ? vals[k] : nearestFinite)
  return sum
}
