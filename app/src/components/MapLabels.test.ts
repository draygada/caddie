import { describe, expect, it } from 'vitest'

import { aimLabel, pinLabel } from './MapLabels'
import type { Player } from '../lib/types'

const player = {
  clubs: { driver: { mu_c: 220, sigma_theta_deg: 4, sigma_d: 0.05, p_mishit: 0.05 } },
  lie: {
    tee: { carry: 1, sigma: 1 },
    fairway: { carry: 1, sigma: 1 },
    rough: { carry: 0.9, sigma: 1.2 },
    bunker: { carry: 0.8, sigma: 1.4 },
  },
} as unknown as Player

describe('pinLabel', () => {
  it('is the distance to the pin in whole yards', () => {
    expect(pinLabel(91.44)).toBe('100 yd')
    expect(pinLabel(312.7)).toBe('342 yd')
  })
})

describe('aimLabel', () => {
  it('names the club and its carry from this lie in yards', () => {
    expect(aimLabel(player, 'driver', 2)).toBe('Driver · 241 yd')
    expect(aimLabel(player, 'driver', 3)).toBe('Driver · 217 yd')
  })
  it('is null for a club the player does not have', () => {
    expect(aimLabel(player, 'test7i', 2)).toBeNull()
  })
})
