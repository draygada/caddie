/**
 * Strokes-to-go heatmap: a viridis-like ramp and a one-pixel-per-cell painter.
 * Pure TypeScript; the canvas is passed in.
 */
import type { HoleBundle } from './types'

export type RGB = [number, number, number]
export type RGBA = [number, number, number, number]

/** Viridis, bright end first: few strokes bright yellow, many strokes dark purple. */
export const STOPS: readonly RGB[] = [
  [253, 231, 37],
  [122, 209, 81],
  [34, 168, 132],
  [42, 120, 142],
  [65, 68, 135],
  [68, 1, 84],
]

/** Colour for a strokes-to-go value on the domain [par - 1, par + 3], clamped; NaN is transparent. */
export function colourScale(par: number): (strokes: number) => RGBA {
  const lo = par - 1
  const hi = par + 3
  const gaps = STOPS.length - 1
  return (strokes: number): RGBA => {
    if (Number.isNaN(strokes)) return [0, 0, 0, 0]
    const t = Math.min(Math.max((strokes - lo) / (hi - lo), 0), 1) * gaps
    const k = Math.min(Math.floor(t), gaps - 1)
    const f = t - k
    const a = STOPS[k]
    const b = STOPS[k + 1]
    return [
      Math.round(a[0] + (b[0] - a[0]) * f),
      Math.round(a[1] + (b[1] - a[1]) * f),
      Math.round(a[2] + (b[2] - a[2]) * f),
      255,
    ]
  }
}

export type ColourScale = ReturnType<typeof colourScale>
export type { HoleBundle }
