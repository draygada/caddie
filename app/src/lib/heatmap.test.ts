import { describe, expect, it } from 'vitest'

import { colourScale, STOPS } from './heatmap'

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
