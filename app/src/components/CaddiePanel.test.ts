import { describe, expect, it } from 'vitest'

import { aimText, distanceToPinM, toYards } from './CaddiePanel'
import { readToyBundle } from '../lib/toyFiles'

describe('toYards', () => {
  it('converts metres to yards (1 yd = 0.9144 m)', () => {
    expect(toYards(0.9144)).toBeCloseTo(1, 9)
    expect(toYards(100)).toBeCloseTo(109.361, 3)
    expect(toYards(0)).toBe(0)
  })
})

describe('aimText', () => {
  it('reads negative directions as left of the pin and positive as right', () => {
    expect(aimText(-12)).toBe('12 deg left of pin')
    expect(aimText(8)).toBe('8 deg right of pin')
  })
  it('says at the pin for 0', () => {
    expect(aimText(0)).toBe('at the pin')
  })
})

describe('distanceToPinM', () => {
  it('is the Euclidean distance from the ball to meta.pin_xy', () => {
    const b = readToyBundle()
    expect(distanceToPinM(b.meta, { x: 27.5, y: 2.5 })).toBeCloseTo(45, 9)
    expect(distanceToPinM(b.meta, { x: 27.5, y: 47.5 })).toBe(0)
  })
})
