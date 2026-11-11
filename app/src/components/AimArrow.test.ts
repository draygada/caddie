import { describe, expect, it } from 'vitest'

import { aimGeometry, pinBearingDeg } from './AimArrow'
import { readToyBundle, toyPlayerDoc } from '../lib/toyFiles'

const b = readToyBundle()
const player = toyPlayerDoc()
const tee = { x: b.meta.tee_xy[0], y: b.meta.tee_xy[1] }

describe('pinBearingDeg', () => {
  it('is 0 straight up the +y axis toward the pin and positive to the right', () => {
    expect(pinBearingDeg(b.meta, tee)).toBeCloseTo(0, 9)
    expect(pinBearingDeg(b.meta, { x: 27.5 - 45, y: 2.5 })).toBeCloseTo(45, 9)
    expect(pinBearingDeg(b.meta, { x: 27.5 + 45, y: 2.5 })).toBeCloseTo(-45, 9)
  })
})

describe('aimGeometry', () => {
  it('draws the line from the ball along pin bearing + dir_deg for mu_c of the club', () => {
    const g = aimGeometry(b.meta, player, tee, 2, { club: 'test7i', dir_deg: 0 })
    expect(g.line[0]).toEqual([tee.x, tee.y])
    expect(g.line[1][0]).toBeCloseTo(tee.x, 9)
    expect(g.line[1][1]).toBeCloseTo(tee.y + 25, 9)
    const right = aimGeometry(b.meta, player, tee, 2, { club: 'test7i', dir_deg: 90 })
    expect(right.line[1][0]).toBeCloseTo(tee.x + 25, 9)
    expect(right.line[1][1]).toBeCloseTo(tee.y, 9)
  })

  it('sizes the 1 sigma ellipse from sigma_theta and sigma_d, scaled by the lie', () => {
    const fw = aimGeometry(b.meta, player, tee, 2, { club: 'test7i', dir_deg: 0 })
    // lateral semi-axis = mu_c * tan(sigma_theta), along = mu_c * sigma_d
    expect(fw.lateral_m).toBeCloseTo(25 * Math.tan((4 * Math.PI) / 180), 9)
    expect(fw.along_m).toBeCloseTo(25 * 0.05, 9)
    const rough = aimGeometry(b.meta, player, tee, 3, { club: 'test7i', dir_deg: 0 })
    expect(rough.lateral_m).toBeCloseTo(25 * 0.9 * Math.tan((4 * 1.3 * Math.PI) / 180), 9)
    expect(rough.along_m).toBeCloseTo(25 * 0.9 * 0.05 * 1.3, 9)
    expect(rough.line[1][1]).toBeCloseTo(tee.y + 25 * 0.9, 9)
  })

  it('returns a closed ellipse ring centred on the line end', () => {
    const g = aimGeometry(b.meta, player, tee, 2, { club: 'test7i', dir_deg: 0 })
    expect(g.ellipse.length).toBeGreaterThan(16)
    expect(g.ellipse[0]).toEqual(g.ellipse[g.ellipse.length - 1])
    const cx = g.ellipse.slice(0, -1).reduce((s, p) => s + p[0], 0) / (g.ellipse.length - 1)
    const cy = g.ellipse.slice(0, -1).reduce((s, p) => s + p[1], 0) / (g.ellipse.length - 1)
    expect(cx).toBeCloseTo(g.line[1][0], 6)
    expect(cy).toBeCloseTo(g.line[1][1], 6)
    const xs = g.ellipse.map((p) => p[0])
    const ys = g.ellipse.map((p) => p[1])
    expect(Math.max(...xs) - Math.min(...xs)).toBeCloseTo(2 * g.lateral_m, 6)
    expect(Math.max(...ys) - Math.min(...ys)).toBeCloseTo(2 * g.along_m, 6)
  })

  it('throws for a club the player does not have', () => {
    expect(() => aimGeometry(b.meta, player, tee, 2, { club: 'nope', dir_deg: 0 })).toThrow(/nope/)
  })
})
