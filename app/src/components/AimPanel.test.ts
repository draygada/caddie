import { describe, expect, it } from 'vitest'

import { aimLineText, chipText, shareText } from './AimPanel'

describe('aim block copy (part 22)', () => {
  it('reads the two distances in yards', () => {
    expect(aimLineText({ toTargetM: 137.16, toPinM: 91.44 })).toBe('150 yd to your target, then 100 yd to the pin')
  })

  it('lists where the shots finish, largest first, and leaves out what never happens', () => {
    expect(shareText({ fairway: 0.62, rough: 0.25, bunker: 0.05, green: 0, penalty: 0.08 })).toBe(
      'Fairway 62% · Rough 25% · Penalty 8% · Bunker 5%',
    )
    expect(shareText({ fairway: 0, rough: 0.004, bunker: 0, green: 0.996, penalty: 0 })).toBe('Green 100%')
  })
})

describe('chipText', () => {
  it('is what is stamped on the club', () => {
    expect(['driver', '7i', 'pw', 'sw50', '3w'].map(chipText)).toEqual(['Driver', '7i', 'PW', 'SW 50', '3w'])
  })
})
