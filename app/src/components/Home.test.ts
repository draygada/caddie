import { describe, expect, it } from 'vitest'

import { testBundle } from '../lib/testBundle'
import { HOME_TAGLINE, MODES_ON_HOME, SETUP_HOLES, startBlocked, teeLabel } from './Home'

describe('home page (part 21)', () => {
  it('offers exactly the two modes, simulate first', () => {
    expect(MODES_ON_HOME.map((m) => m.screen)).toEqual(['simulate', 'play'])
    expect(MODES_ON_HOME.map((m) => m.title)).toEqual(['Simulate a hole', 'Play with GPS'])
  })

  it('says where each mode is used and that Play asks for location', () => {
    expect(MODES_ON_HOME[0].where).toBe('At a desk')
    expect(MODES_ON_HOME[1].where).toBe('On the course')
    expect(MODES_ON_HOME[1].body).toMatch(/location/)
    expect(MODES_ON_HOME[0].body).not.toMatch(/location|GPS/)
  })

  it('keeps to the copy rules: no exclamation marks, no dashes as punctuation', () => {
    for (const text of [HOME_TAGLINE, ...MODES_ON_HOME.flatMap((m) => [m.title, m.body, m.where])]) {
      const dashes = new RegExp(`!|${String.fromCharCode(0x2014)}|${String.fromCharCode(0x2013)}| - `)
      expect(text).not.toMatch(dashes)
      expect(text.length).toBeGreaterThan(0)
    }
  })
})

describe('setup step (part 21)', () => {
  it('offers holes 10, 11 and 12 only', () => {
    expect(SETUP_HOLES).toEqual([10, 11, 12])
  })

  it('names tees as a golfer would', () => {
    expect(teeLabel('black')).toBe('Black')
    expect(teeLabel('white')).toBe('White')
  })

  it('blocks Start until the chosen hole has loaded, and says why', () => {
    const b = testBundle({}, { hole: 11 })
    expect(startBlocked(b, 11, null)).toBeNull()
    expect(startBlocked(testBundle({}, { hole: '11' as unknown as number }), 11, null)).toBeNull() // as the solver writes it
    expect(startBlocked(null, 11, null)).toBe('Loading hole 11')
    expect(startBlocked(b, 12, null)).toBe('Loading hole 12') // the old hole is still in the store
    expect(startBlocked(null, 12, 'fetch /data/12/drop/meta.json: 404')).toBe('Hole 12 is not ready yet')
  })
})
