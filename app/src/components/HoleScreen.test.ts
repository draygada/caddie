import { describe, expect, it } from 'vitest'

import { EMPTY_BALL_TEXT, panelParts } from './HoleScreen'

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
