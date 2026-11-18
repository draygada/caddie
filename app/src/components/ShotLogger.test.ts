import { describe, expect, it } from 'vitest'

import type { LoggedShot } from '../lib/shotLog'
import { testMeta } from '../lib/testBundle'
import { endHandles, shotLabel, shotLineFeatures } from './ShotLogger'

function shot(over: Partial<LoggedShot> = {}): LoggedShot {
  return { start: { x: 10, y: 5 }, end: { x: 10, y: 35 }, startAcc: 0, endAcc: 0, lie: 2, club: '7i', aimDeg: 0, t: 1, outcome: 'normal', ...over }
}

describe('shotLineFeatures', () => {
  const meta = testMeta()

  it('draws one line per finished shot, start to end', () => {
    const fc = shotLineFeatures(meta, [shot(), shot({ start: { x: 10, y: 35 }, end: { x: 20, y: 45 }, outcome: 'green' })], null)
    expect(fc.features).toHaveLength(2)
    expect(fc.features[0].geometry.coordinates).toHaveLength(2)
    expect(fc.features[0].properties.open).toBe(false)
  })

  it('draws the open shot from its start to the ball, and nothing for it without a ball', () => {
    const log = [shot({ end: null, endAcc: null })]
    expect(shotLineFeatures(meta, log, null).features).toHaveLength(0)
    const fc = shotLineFeatures(meta, log, { x: 12, y: 30 })
    expect(fc.features).toHaveLength(1)
    expect(fc.features[0].properties.open).toBe(true)
  })

  it('skips the open shot while the ball has not left its start', () => {
    expect(shotLineFeatures(meta, [shot({ end: null, endAcc: null })], { x: 10, y: 5 }).features).toHaveLength(0)
  })
})

describe('endHandles', () => {
  it('gives every finished end a drag handle except the one under the ball', () => {
    const log = [shot(), shot({ start: { x: 10, y: 35 }, end: { x: 20, y: 45 } }), shot({ start: { x: 20, y: 45 }, end: null, endAcc: null })]
    expect(endHandles(log, { x: 20, y: 45 })).toEqual([0])
    expect(endHandles(log, { x: 1, y: 1 })).toEqual([0, 1])
    expect(endHandles(log, null)).toEqual([0, 1])
  })
})

describe('shotLabel', () => {
  it('names the club and the distance in yards once the shot is finished', () => {
    expect(shotLabel(shot({ end: { x: 10, y: 5 + 91.44 } }), 0)).toBe('Shot 1: 7 iron, 100 yd')
    expect(shotLabel(shot({ end: null, endAcc: null, club: 'driver' }), 2)).toBe('Shot 3: Driver, in the air')
    expect(shotLabel(shot({ outcome: 'penalty', end: { x: 10, y: 5 + 91.44 } }), 0)).toBe('Shot 1: 7 iron, penalty')
  })
})
