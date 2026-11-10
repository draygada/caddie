import { describe, expect, it } from 'vitest'

import { colourScale, paintHeatmap, STOPS } from './heatmap'
import { readToyBundle } from './toyFiles'

type RGBA = [number, number, number, number]

describe('colourScale', () => {
  const scale = colourScale(4)
  const first = STOPS[0]
  const last = STOPS[STOPS.length - 1]

  it('has a 6-stop ramp', () => {
    expect(STOPS).toHaveLength(6)
    for (const s of STOPS) expect(s).toHaveLength(3)
  })

  it('maps par - 1 to the first stop and par + 3 to the last, fully opaque', () => {
    expect(scale(3)).toEqual([...first, 255] as RGBA)
    expect(scale(7)).toEqual([...last, 255] as RGBA)
  })

  it('clamps outside the domain', () => {
    expect(scale(0)).toEqual(scale(3))
    expect(scale(12)).toEqual(scale(7))
  })

  it('interpolates in between', () => {
    const mid = scale(5)
    expect(mid[3]).toBe(255)
    expect(mid).not.toEqual(scale(3))
    expect(mid).not.toEqual(scale(7))
    // halfway along the domain is exactly the middle of the ramp: between stops 2 and 3
    const s2 = STOPS[2]
    const s3 = STOPS[3]
    for (let k = 0; k < 3; k++) expect(mid[k]).toBe(Math.round((s2[k] + s3[k]) / 2))
  })

  it('hits each stop at equal spacing across the domain', () => {
    // domain width 4 over 5 gaps: stops at 3, 3.8, 4.6, 5.4, 6.2, 7
    STOPS.forEach((stop, k) => expect(scale(3 + 0.8 * k)).toEqual([...stop, 255] as RGBA))
  })

  it('returns alpha 0 for NaN', () => {
    expect(scale(NaN)[3]).toBe(0)
  })

  it('follows par', () => {
    expect(colourScale(3)(2)).toEqual([...first, 255] as RGBA)
    expect(colourScale(5)(8)).toEqual([...last, 255] as RGBA)
  })
})

/** Minimal 2d context: enough for putImageData / getImageData round trips. */
class FakeContext {
  data: Uint8ClampedArray
  constructor(
    readonly width: number,
    readonly height: number,
  ) {
    this.data = new Uint8ClampedArray(width * height * 4)
  }
  createImageData(w: number, h: number) {
    return { width: w, height: h, data: new Uint8ClampedArray(w * h * 4), colorSpace: 'srgb' as const }
  }
  putImageData(img: { width: number; height: number; data: Uint8ClampedArray }, dx: number, dy: number) {
    for (let y = 0; y < img.height; y++)
      for (let x = 0; x < img.width; x++) {
        const s = (y * img.width + x) * 4
        const d = ((y + dy) * this.width + (x + dx)) * 4
        this.data.set(img.data.subarray(s, s + 4), d)
      }
  }
  getImageData(sx: number, sy: number, w: number, h: number) {
    const out = new Uint8ClampedArray(w * h * 4)
    for (let y = 0; y < h; y++)
      for (let x = 0; x < w; x++) {
        const s = ((y + sy) * this.width + (x + sx)) * 4
        out.set(this.data.subarray(s, s + 4), (y * w + x) * 4)
      }
    return { width: w, height: h, data: out, colorSpace: 'srgb' as const }
  }
  clearRect() {
    this.data.fill(0)
  }
}

class FakeCanvas {
  width = 0
  height = 0
  ctx: FakeContext | null = null
  getContext(kind: string) {
    if (kind !== '2d') return null
    this.ctx ??= new FakeContext(this.width, this.height)
    return this.ctx
  }
}

function pixel(canvas: FakeCanvas, x: number, y: number): RGBA {
  const d = canvas.getContext('2d')?.getImageData(x, y, 1, 1).data
  if (!d) throw new Error('no context')
  return [d[0], d[1], d[2], d[3]]
}

describe('paintHeatmap', () => {
  const b = readToyBundle()
  const scale = colourScale(b.meta.par)

  it('paints one pixel per cell with row 0 at the bottom', () => {
    const canvas = new FakeCanvas()
    paintHeatmap(b, canvas as unknown as HTMLCanvasElement, scale)
    expect([canvas.width, canvas.height]).toEqual([b.meta.cols, b.meta.rows])
    // bottom-left pixel (0, 9) is cell (0, 0); top-left pixel (0, 0) is cell (9, 0)
    expect(pixel(canvas, 0, 9)).toEqual(scale(b.value[0]))
    expect(pixel(canvas, 0, 0)).toEqual(scale(b.value[9 * b.meta.cols]))
    // the pin cell (9, 5) is pixel (5, 0): 1.5 strokes, the bright end
    expect(pixel(canvas, 5, 0)).toEqual(scale(1.5))
    expect(pixel(canvas, 5, 0)).toEqual([...STOPS[0], 255] as RGBA)
  })

  it('leaves NaN cells transparent', () => {
    const canvas = new FakeCanvas()
    paintHeatmap(b, canvas as unknown as HTMLCanvasElement, scale)
    expect(pixel(canvas, 9, 5)[3]).toBe(0) // OB column
    expect(pixel(canvas, 0, 2)[3]).toBe(0) // water cell (7, 0) is pixel (0, 2)
    expect(pixel(canvas, 4, 2)[3]).toBe(255) // fairway (7, 4) next to it
  })

  it('matches the whole grid pixel by pixel', () => {
    const canvas = new FakeCanvas()
    paintHeatmap(b, canvas as unknown as HTMLCanvasElement, scale)
    for (let r = 0; r < b.meta.rows; r++)
      for (let c = 0; c < b.meta.cols; c++)
        expect(pixel(canvas, c, b.meta.rows - 1 - r)).toEqual(scale(b.value[r * b.meta.cols + c]))
  })
})
