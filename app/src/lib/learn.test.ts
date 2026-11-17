import { readFileSync } from 'node:fs'
import { dirname, join } from 'node:path'
import { fileURLToPath } from 'node:url'

import { describe, expect, it } from 'vitest'

import { paramsFromStats, PRIOR_KAPPA, statsFromParams, updateClubStats, updateIg, updateNig } from './learn'
import { toyPlayerDoc } from './toyFiles'
import type { ClubStats } from './types'

interface Fixture {
  prior: ClubStats
  observations: [number, number, number][]
  after: ClubStats[]
}

const FIXTURE = join(dirname(fileURLToPath(import.meta.url)), '..', '..', '..', 'docs', 'fixtures', 'stats_updates.json')
const fx = JSON.parse(readFileSync(FIXTURE, 'utf8')) as Fixture

function expectStats(got: ClubStats, want: ClubStats) {
  expect(got.n).toBe(want.n)
  for (const k of ['m', 'kappa', 'alpha', 'beta'] as const) {
    expect(Math.abs(got.carry[k] - want.carry[k])).toBeLessThan(1e-9)
    expect(Math.abs(got.roll[k] - want.roll[k])).toBeLessThan(1e-9)
  }
  expect(Math.abs(got.theta.alpha - want.theta.alpha)).toBeLessThan(1e-9)
  expect(Math.abs(got.theta.beta - want.theta.beta)).toBeLessThan(1e-9)
}

describe('conjugate updates (port of solver dispersion.py)', () => {
  it('reproduces every step of docs/fixtures/stats_updates.json to 1e-9', () => {
    expect(fx.observations).toHaveLength(5)
    let s = fx.prior
    fx.observations.forEach(([carry, total, lateral], k) => {
      s = updateClubStats(s, carry, total, lateral)
      expectStats(s, fx.after[k])
    })
  })

  it('does not mutate its input', () => {
    const before = JSON.stringify(fx.prior)
    updateClubStats(fx.prior, 200, 215, 5)
    expect(JSON.stringify(fx.prior)).toBe(before)
  })

  it('updateNig moves the mean by 1 / (kappa + 1) of the gap', () => {
    const s = updateNig({ m: 100, kappa: 4, alpha: 2, beta: 10 }, 110)
    expect(s).toEqual({ m: 102, kappa: 5, alpha: 2.5, beta: 10 + (4 * 100) / 10 })
  })

  it('updateIg adds half a shot and half the squared angle', () => {
    expect(updateIg({ alpha: 2.5, beta: 10 }, 4)).toEqual({ alpha: 3, beta: 18 })
  })
})

describe('statsFromParams and paramsFromStats', () => {
  const player = toyPlayerDoc()

  it('round trips every club to its point estimates to 1e-9', () => {
    for (const id of player.club_order) {
      const c = player.clubs[id]
      const back = paramsFromStats(statsFromParams(c), c.p)
      for (const k of ['mu_c', 'sigma_theta_deg', 'sigma_d', 'mu_r', 'sigma_r', 'p'] as const)
        expect(Math.abs(back[k] - c[k])).toBeLessThan(1e-9)
    }
  })

  it('is a prior worth kappa pseudo-shots, 5 by default, with no shots counted', () => {
    const c = player.clubs[player.club_order[0]]
    const s = statsFromParams(c)
    expect(s.n).toBe(0)
    expect(s.carry.kappa).toBe(PRIOR_KAPPA)
    expect(s.roll.kappa).toBe(5)
    expect(s.carry.alpha).toBe(2.5)
    expect(statsFromParams(c, 8).carry.kappa).toBe(8)
    expect(statsFromParams(c, 8).theta.alpha).toBe(4)
  })

  it('matches the solver on the fixture: posterior means after five shots', () => {
    const p = paramsFromStats(fx.after[4], 0.1)
    const s = fx.after[4]
    expect(p.mu_c).toBe(s.carry.m)
    expect(p.sigma_d).toBeCloseTo(Math.sqrt(s.carry.beta / (s.carry.alpha - 1)) / s.carry.m, 12)
    expect(p.sigma_theta_deg).toBeCloseTo(Math.sqrt(s.theta.beta / (s.theta.alpha - 1)), 12)
    expect(p.sigma_r).toBeCloseTo(Math.sqrt(s.roll.beta / (s.roll.alpha - 1)), 12)
    expect(p.p).toBe(0.1)
    expect(p.stats).toBe(s)
  })
})
