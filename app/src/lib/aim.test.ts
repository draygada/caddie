import { describe, expect, it } from 'vitest'

import { clubForDistance, meanTotalM, resolveAim } from './aim'
import { testBundle } from './testBundle'
import type { ClubParams, Player } from './types'

function club(mu_c: number, mu_r: number): ClubParams {
  return { mu_c, sigma_theta_deg: 5, sigma_d: 0.06, p: 0.05, mu_r, sigma_r: 2, sampled: true, stats: null }
}

const player: Player = {
  handicap: 15,
  clubs: { driver: club(210, 20), '5h': club(165, 10), '7i': club(140, 5), sw: club(85, 2) },
  club_order: ['driver', '5h', '7i', 'sw'],
  lie: {
    tee: { carry: 1, sigma: 1, roll: 1 },
    fairway: { carry: 1, sigma: 1, roll: 1 },
    rough: { carry: 0.9, sigma: 1.3, roll: 0.5 },
    bunker: { carry: 0.8, sigma: 1.6, roll: 0 },
  },
  putting: { distance_m: [1], expected_putts: [1.5] },
}

/** A 100 m wide, 400 m long strip with the pin straight up the middle. */
const b = testBundle({}, { rows: 80, cols: 20, pin_xy: [50, 380] })
const ball = { x: 50, y: 20 }

describe('meanTotalM', () => {
  it('is carry plus roll, each scaled by the lie the ball is hit from', () => {
    expect(meanTotalM(player, '7i', 2)).toBe(145)
    expect(meanTotalM(player, '7i', 3)).toBeCloseTo(140 * 0.9 + 5 * 0.5, 9)
    expect(meanTotalM(player, '7i', 4)).toBeCloseTo(112, 9)
    expect(meanTotalM(player, '7i', 8)).toBeCloseTo(140 * 0.9 + 5 * 0.5, 9) // trees play as rough
  })
})

describe('clubForDistance', () => {
  it('picks the club whose mean total is closest to the distance', () => {
    expect(clubForDistance(player, 2, 150)).toBe('7i')
    expect(clubForDistance(player, 2, 170)).toBe('5h')
    expect(clubForDistance(player, 2, 60)).toBe('sw')
  })

  it('offers the driver only on the tee', () => {
    expect(clubForDistance(player, 1, 240)).toBe('driver')
    expect(clubForDistance(player, 2, 240)).toBe('5h')
    expect(clubForDistance(player, 3, 400)).toBe('5h')
  })
})

describe('resolveAim', () => {
  const rec = { club: '5h', dir_deg: -4 }

  it('with the target untouched it is the caddie\'s aim: same club, same direction, target at the club\'s mean total', () => {
    const a = resolveAim(b, player, ball, 2, rec, null, null)
    expect(a.custom).toBe(false)
    expect(a.club).toBe('5h')
    expect(a.dir_deg).toBe(-4)
    expect(a.toTargetM).toBeCloseTo(175, 9)
    expect(a.target.x).toBeCloseTo(50 + 175 * Math.sin((-4 * Math.PI) / 180), 9)
    expect(a.target.y).toBeCloseTo(20 + 175 * Math.cos((-4 * Math.PI) / 180), 9)
    expect(a.toPinM).toBeCloseTo(Math.hypot(50 - a.target.x, 380 - a.target.y), 9)
  })

  it('a moved target sets the direction and picks the club for its distance', () => {
    const a = resolveAim(b, player, ball, 2, rec, { x: 70, y: 160 }, null)
    expect(a.custom).toBe(true)
    expect(a.toTargetM).toBeCloseTo(Math.hypot(20, 140), 9)
    expect(a.club).toBe('7i')
    expect(a.dir_deg).toBeCloseTo((Math.atan2(20, 140) * 180) / Math.PI, 9) // the pin is straight ahead
    expect(a.toPinM).toBeCloseTo(Math.hypot(20, 220), 9)
    expect(a.target).toEqual({ x: 70, y: 160 })
  })

  it('a chosen club wins over the automatic one, with or without a moved target', () => {
    expect(resolveAim(b, player, ball, 2, rec, { x: 70, y: 160 }, 'sw').club).toBe('sw')
    const a = resolveAim(b, player, ball, 2, rec, null, '7i')
    expect(a.club).toBe('7i')
    expect(a.custom).toBe(true)
    expect(a.dir_deg).toBe(-4)
    expect(a.toTargetM).toBeCloseTo(145, 9)
    expect(resolveAim(b, player, ball, 2, rec, null, '5h').custom).toBe(false) // the caddie's own club
  })

  it('ignores a chosen club the player cannot use here', () => {
    expect(resolveAim(b, player, ball, 2, rec, null, 'driver').club).toBe('5h')
    expect(resolveAim(b, player, ball, 2, rec, null, 'putter').club).toBe('5h')
    expect(resolveAim(b, player, ball, 1, rec, null, 'driver').club).toBe('driver')
  })
})
