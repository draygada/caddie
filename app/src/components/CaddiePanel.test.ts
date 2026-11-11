import { describe, expect, it } from 'vitest'

import { aimOffsetYd, aimText, distanceToPinM, toYards } from './CaddiePanel'
import { clubDisplayName } from '../lib/tokens'
import { readToyBundle, toyPlayerDoc } from '../lib/toyFiles'

describe('toYards', () => {
  it('converts metres to yards (1 yd = 0.9144 m)', () => {
    expect(toYards(0.9144)).toBeCloseTo(1, 9)
    expect(toYards(100)).toBeCloseTo(109.361, 3)
    expect(toYards(0)).toBe(0)
  })
})

describe('aimText', () => {
  it('reads a negative offset as left of the pin and positive as right, in yards', () => {
    expect(aimText(-12.4)).toBe('Aim 12 yards left of the pin')
    expect(aimText(8)).toBe('Aim 8 yards right of the pin')
    expect(aimText(1.2)).toBe('Aim 1 yard right of the pin')
  })
  it('says at the pin within half a yard', () => {
    expect(aimText(0)).toBe('Aim at the pin')
    expect(aimText(-0.4)).toBe('Aim at the pin')
  })
})

describe('aimOffsetYd', () => {
  const player = toyPlayerDoc()
  it('is the lateral offset at the carry: carry * tan(dir), in yards, scaled by the lie', () => {
    expect(aimOffsetYd(player, 'test7i', 2, 0)).toBe(0)
    expect(aimOffsetYd(player, 'test7i', 2, 10)).toBeCloseTo(toYards(25 * Math.tan((10 * Math.PI) / 180)), 9)
    expect(aimOffsetYd(player, 'test7i', 3, -10)).toBeCloseTo(-toYards(22.5 * Math.tan((10 * Math.PI) / 180)), 9)
  })
  it('is 0 for a club the player does not have', () => {
    expect(aimOffsetYd(player, 'nope', 2, 30)).toBe(0)
  })
})

describe('clubDisplayName', () => {
  it('names clubs as on the sticks', () => {
    expect(clubDisplayName('driver')).toBe('Driver')
    expect(clubDisplayName('3w')).toBe('3 wood')
    expect(clubDisplayName('5h')).toBe('5 hybrid')
    expect(clubDisplayName('7i')).toBe('7 iron')
    expect(clubDisplayName('pw')).toBe('Pitching wedge')
    expect(clubDisplayName('sw')).toBe('Sand wedge')
    expect(clubDisplayName('sw70')).toBe('Sand wedge, 70 yd')
    expect(clubDisplayName('test7i')).toBe('Test 7 iron')
  })
})

describe('distanceToPinM', () => {
  it('is the Euclidean distance from the ball to meta.pin_xy', () => {
    const b = readToyBundle()
    expect(distanceToPinM(b.meta, { x: 27.5, y: 2.5 })).toBeCloseTo(45, 9)
    expect(distanceToPinM(b.meta, { x: 27.5, y: 47.5 })).toBe(0)
  })
})
