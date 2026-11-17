import { describe, expect, it } from 'vitest'

import type { Aim } from '../lib/aim'
import { testMeta } from '../lib/testBundle'
import { aimFeatures, restLabel, targetLabel } from './AimTarget'

const aim: Aim = { club: '7i', dir_deg: 3, target: { x: 30, y: 40 }, toTargetM: 137.16, toPinM: 91.44, custom: true }

describe('labels on the map (part 22)', () => {
  it('the target reads the club and the distance to it; the second line reads what is left', () => {
    expect(targetLabel(aim)).toBe('7 iron · 150 yd')
    expect(restLabel(aim)).toBe('100 yd to pin')
  })
})

describe('aimFeatures', () => {
  const meta = testMeta()
  const ball = { x: 27.5, y: 2.5 }

  it('draws the aim line, the line on to the pin, and one dot per finish', () => {
    const finishes = [
      { x: 29, y: 38, penalty: false },
      { x: 33, y: 41, penalty: false },
      { x: 47, y: 30, penalty: true },
    ]
    const fc = aimFeatures(meta, ball, aim, finishes)
    const kinds = fc.features.map((f) => f.properties.kind)
    expect(kinds.filter((k) => k === 'aim')).toHaveLength(1)
    expect(kinds.filter((k) => k === 'rest')).toHaveLength(1)
    expect(kinds.filter((k) => k === 'dot')).toHaveLength(3)
    expect(fc.features.filter((f) => f.properties.penalty)).toHaveLength(1)
  })

  it('is empty with no aim', () => {
    expect(aimFeatures(meta, ball, null, []).features).toEqual([])
  })
})
