import { describe, expect, it } from 'vitest'

import fixture from '../../../docs/fixtures/shot_samples.json'
import { cellOf } from './grid'
import { mulberry32 } from './rng'
import { expectedPutts, sampleShot } from './shot'
import { readToyBundle, toyPlayerDoc } from './toyFiles'
import type { Lie, Mode } from './types'

const b = readToyBundle()
const player = toyPlayerDoc()

describe('sampleShot parity with docs/fixtures/shot_samples.json', () => {
  it('reproduces the first 20 resting points to 1e-3', () => {
    const rng = mulberry32(fixture.seed)
    const from = { x: fixture.from[0], y: fixture.from[1] }
    for (let k = 0; k < fixture.landings.length; k++) {
      const s = sampleShot(b, player, from, 2, fixture.club.name, fixture.dir_deg, fixture.mode as Mode, rng)
      expect(s.x).toBeCloseTo(fixture.landings[k][0], 3)
      expect(s.y).toBeCloseTo(fixture.landings[k][1], 3)
      expect(s.lie).toBe(fixture.landing_lies[k] as Lie)
    }
  })

  it('consumes seven uniforms per shot (theta 2, mixture 1, carry 2, roll 2)', () => {
    let calls = 0
    const rng = () => {
      calls += 1
      return 0.5
    }
    sampleShot(b, player, { x: 25, y: 25 }, 2, 'test7i', 10, 'replay', rng)
    expect(calls).toBe(7)
  })

  it('throws for an unknown club', () => {
    expect(() => sampleShot(b, player, { x: 25, y: 25 }, 2, 'nope', 0, 'replay', mulberry32(1))).toThrow(/nope/)
  })
})

describe('expectedPutts', () => {
  it('interpolates the player putting table and extrapolates linearly beyond it', () => {
    const p = {
      ...player,
      putting: { distance_m: [1, 2, 3, 4, 6, 8, 10, 15, 25], expected_putts: [1.31, 1.648, 1.855, 1.929, 2.066, 2.199, 2.32, 2.559, 2.817] },
    }
    expect(expectedPutts(p, 1)).toBeCloseTo(1.31, 9)
    expect(expectedPutts(p, 1.5)).toBeCloseTo((1.31 + 1.648) / 2, 9)
    expect(expectedPutts(p, 25)).toBeCloseTo(2.817, 9)
    const slope = (2.817 - 2.559) / 10
    expect(expectedPutts(p, 35)).toBeCloseTo(2.817 + slope * 10, 9)
    expect(expectedPutts(p, 0)).toBeCloseTo(1.31, 9) // clamped below the first node
  })

  it('is flat for the toy player', () => {
    expect(expectedPutts(player, 3)).toBe(1.5)
    expect(expectedPutts(player, 40)).toBe(1.5)
  })
})

describe('terrain rules (part 04 slice 5 on the toy bundle)', () => {
  // A deterministic rng for one shot (7 draws): every normal is 0 (u1 = 0 gives
  // sqrt(-2 ln 1) = 0) and the mixture uniform is 0.5, above p, so no mishit.
  const meanShot = () => {
    const vals = [0, 0, 0.5, 0, 0, 0, 0]
    let k = 0
    return () => vals[k++ % vals.length]
  }

  it('a straight shot lands at the mean carry along the aim', () => {
    // from (12.5, 2.5) aiming straight up +y (column 2 has no bunker): carry 25, roll 2
    const from = { x: 12.5, y: 2.5 }
    const bearing = (Math.atan2(27.5 - 12.5, 47.5 - 2.5) * 180) / Math.PI
    const s = sampleShot(b, player, from, 2, 'test7i', -bearing, 'replay', meanShot())
    expect(s.x).toBeCloseTo(12.5, 9)
    expect(s.y).toBeCloseTo(2.5 + 25 + 2, 9)
    expect(s.lie).toBe(2)
    expect(s.reward).toBe(-1)
    expect(s.next).toEqual({ x: s.x, y: s.y })
  })

  it('water: mulligan returns to the origin at -1, replay at -2, drop goes to the tee-side cell at -2', () => {
    // from (2.5, 12.5) in column 0, the mean shot lands in water row 7 (y 35 to 40): carry 25 up the
    // pin bearing from column 0 drifts right, so aim left of the pin to stay in column 0
    const from = { x: 2.5, y: 12.5 }
    const bearing = (Math.atan2(27.5 - 2.5, 47.5 - 12.5) * 180) / Math.PI
    const dir = -bearing // absolute aim straight up +y
    const m = sampleShot(b, player, from, 2, 'test7i', dir, 'mulligan', meanShot())
    expect(m.lie).toBe(6)
    expect(m.reward).toBe(-1)
    expect(m.next).toEqual(from)
    const r = sampleShot(b, player, from, 2, 'test7i', dir, 'replay', meanShot())
    expect(r.reward).toBe(-2)
    expect(r.next).toEqual(from)
    const d = sampleShot(b, player, from, 2, 'test7i', dir, 'drop', meanShot())
    expect(d.reward).toBe(-2)
    expect(d.next.y).toBeLessThan(35) // tee side of the water row
    expect([2, 3]).toContain(b.lie[cellOf(b, d.next).i])
  })

  it('OB: the ball off the grid or in the OB column follows the same three rules', () => {
    // from (42.5, 2.5) aiming right into the OB column 9 (x >= 45)
    const from = { x: 42.5, y: 2.5 }
    const bearing = (Math.atan2(27.5 - 42.5, 47.5 - 2.5) * 180) / Math.PI
    const dir = 60 - bearing // absolute aim 60 deg right of +y
    const m = sampleShot(b, player, from, 2, 'test7i', dir, 'mulligan', meanShot())
    expect(m.lie).toBe(7)
    expect(m.reward).toBe(-1)
    expect(m.next).toEqual(from)
    const r = sampleShot(b, player, from, 2, 'test7i', dir, 'replay', meanShot())
    expect(r.reward).toBe(-2)
    expect(r.next).toEqual(from)
    const d = sampleShot(b, player, from, 2, 'test7i', dir, 'drop', meanShot())
    expect(d.reward).toBe(-2)
    const lie = b.lie[cellOf(b, d.next).i]
    expect(lie).toBeGreaterThanOrEqual(1)
    expect(lie).toBeLessThanOrEqual(5)
    expect(d.next.x).toBeLessThan(45)
  })

  it('beyond the far edge reads as OB too', () => {
    const s = sampleShot(b, player, { x: 27.5, y: 42.5 }, 2, 'test7i', 0, 'replay', meanShot())
    expect(s.y).toBeGreaterThan(50)
    expect(s.lie).toBe(7)
    expect(s.reward).toBe(-2)
  })

  it('bunker landings do not roll and the rough shortens carry', () => {
    // bunker at (5, 4): centre (22.5, 27.5). From (22.5, 2.5) straight up: carry 25 -> (22.5, 27.5)
    const from = { x: 22.5, y: 2.5 }
    const bearing = (Math.atan2(27.5 - 22.5, 47.5 - 2.5) * 180) / Math.PI
    const s = sampleShot(b, player, from, 2, 'test7i', -bearing, 'replay', meanShot())
    expect(s.lie).toBe(4)
    expect(s.y).toBeCloseTo(27.5, 6) // roll multiplier 0 in the bunker
    // from the rough the carry is 22.5, which is still the bunker cell (y 25 to 30), so no roll
    const rough = sampleShot(b, player, from, 3, 'test7i', -bearing, 'replay', meanShot())
    expect(rough.lie).toBe(4)
    expect(rough.y).toBeCloseTo(2.5 + 25 * 0.9, 6)
    // from (22.5, 12.5) in the rough the same shot clears the bunker and rolls 2 x 0.5
    const clear = sampleShot(b, player, { x: 22.5, y: 12.5 }, 3, 'test7i', -((Math.atan2(5, 35) * 180) / Math.PI), 'replay', meanShot())
    expect(clear.lie).toBe(2)
    expect(clear.y).toBeCloseTo(12.5 + 25 * 0.9 + 2 * 0.5, 6)
  })
})
