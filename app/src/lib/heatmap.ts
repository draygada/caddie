/**
 * Strokes-to-go heatmap: the warm six-stop ramp from docs/design.md section 5 and a
 * one-pixel-per-cell painter. Pure TypeScript; the canvas is passed in.
 */
import type { HoleBundle } from './types'

export type RGB = [number, number, number]
export type RGBA = [number, number, number, number]

/**
 * Dark blue, teal, yellow, orange, red: few strokes cool and dark, many strokes hot.
 * Must match --h0 to --h5 in index.css, which the legend reads.
 */
export const STOPS: readonly RGB[] = [
  [29, 43, 83],
  [46, 111, 158],
  [95, 184, 155],
  [232, 212, 90],
  [240, 138, 36],
  [179, 38, 30],
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

type Canvas2D = OffscreenCanvas | HTMLCanvasElement

/**
 * One pixel per cell. Row 0 (the tee end) is the BOTTOM row of the canvas, so the
 * image lines up with `gridCorners` (TL, TR, BR, BL) when used as a MapLibre image source.
 */
export function paintHeatmap(b: HoleBundle, canvas: Canvas2D, scale: ColourScale): void {
  const { rows, cols } = b.meta
  canvas.width = cols
  canvas.height = rows
  const ctx = canvas.getContext('2d') as
    | (CanvasRenderingContext2D | OffscreenCanvasRenderingContext2D)
    | null
  if (!ctx) throw new Error('canvas has no 2d context')
  const img = ctx.createImageData(cols, rows)
  const px = img.data
  for (let r = 0; r < rows; r++) {
    const y = rows - 1 - r
    for (let c = 0; c < cols; c++) {
      const [red, green, blue, alpha] = scale(b.value[r * cols + c])
      const o = (y * cols + c) * 4
      px[o] = red
      px[o + 1] = green
      px[o + 2] = blue
      px[o + 3] = alpha
    }
  }
  ctx.putImageData(img, 0, 0)
}

/** PNG data URL of the heatmap, for `map.addSource('heat', {type: 'image', url})`. Browser only. */
export function heatmapDataUrl(b: HoleBundle): string {
  const canvas = document.createElement('canvas')
  paintHeatmap(b, canvas, colourScale(b.meta.par))
  return canvas.toDataURL('image/png')
}

/** CSS linear-gradient of the ramp for the legend bar. */
export function rampGradientCss(): string {
  const stops = STOPS.map((s, k) => `rgb(${s[0]} ${s[1]} ${s[2]}) ${(100 * k) / (STOPS.length - 1)}%`)
  return `linear-gradient(90deg, ${stops.join(', ')})`
}
