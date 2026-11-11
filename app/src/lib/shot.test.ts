import { describe, expect, it } from 'vitest'

import fixture from '../../../docs/fixtures/shot_samples.json'
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
