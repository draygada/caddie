import { describe, expect, it } from 'vitest'

import { HOME_TAGLINE, MODES_ON_HOME } from './Home'

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
      expect(text).not.toMatch(/!|—|–| - /)
      expect(text.length).toBeGreaterThan(0)
    }
  })
})
