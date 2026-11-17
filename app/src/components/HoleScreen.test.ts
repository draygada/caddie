import { describe, expect, it } from 'vitest'

import { testMeta } from '../lib/testBundle'
import { EMPTY_BALL_TEXT, holeLine, nextHole, panelParts } from './HoleScreen'

describe('panelParts (part 21)', () => {
  it('Simulate has Play it out and nothing that needs the course', () => {
    expect(panelParts('simulate')).toEqual({ logger: false, learn: false, playItOut: true, gps: false })
  })

  it('Play has GPS, the shot logger and the learn switch, and no Play it out', () => {
    expect(panelParts('play')).toEqual({ logger: true, learn: true, playItOut: false, gps: true })
  })

  it('the empty panel never tells a Simulate user to turn on GPS', () => {
    expect(EMPTY_BALL_TEXT.simulate).toBe('Tap the map to place the ball')
    expect(EMPTY_BALL_TEXT.simulate).not.toMatch(/GPS/)
    expect(EMPTY_BALL_TEXT.play).toMatch(/Finding you/)
  })
})

describe('the hole line in the panel (replaces the top bar)', () => {
  it('reads hole, par, yardage from the chosen tee, and the tees', () => {
    const meta = testMeta({ hole: 11, par: 4, tees: { black: [80, 55], white: [80, 95] }, pin_xy: [80, 55 + 342 * 0.9144] })
    expect(holeLine(meta, 'black')).toBe('Hole 11 · Par 4 · 342 yd · Black tees')
    expect(holeLine(meta, 'white')).toBe(`Hole 11 · Par 4 · ${Math.round(342 - 40 / 0.9144)} yd · White tees`)
  })
})

describe('nextHole', () => {
  it('goes 10, 11, 12 and stops', () => {
    expect(nextHole(10)).toBe(11)
    expect(nextHole(11)).toBe(12)
    expect(nextHole(12)).toBeNull()
    expect(nextHole('toy')).toBeNull()
  })
})
