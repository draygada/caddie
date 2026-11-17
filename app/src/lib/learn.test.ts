import { readFileSync } from 'node:fs'
import { dirname, join } from 'node:path'
import { fileURLToPath } from 'node:url'

import { describe, expect, it } from 'vitest'

import { learnedPlayer, paramsFromStats, PRIOR_KAPPA, statsFromParams, updateClubStats, updateIg, updateNig } from './learn'
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

describe('learnedPlayer', () => {
  const base = toyPlayerDoc()
  const id = base.club_order[0]
  const c = base.clubs[id]
  const two: typeof base = {
    ...base,
    club_order: ['a', 'b'],
    clubs: { a: { ...c, stats: fx.prior, sampled: true }, b: { ...c, stats: null, sampled: false } },
  }

  it('returns the base player itself when there is nothing to learn from', () => {
    expect(learnedPlayer(base, [])).toBe(base)
  })

  it('changes exactly the clubs that were hit and never mutates the base', () => {
    const before = JSON.stringify(two)
    const out = learnedPlayer(two, [{ club: 'a', carry: 212.4, total: 231, lateral: -8.2 }])
    expect(JSON.stringify(two)).toBe(before)
    expect(out.clubs.b).toBe(two.clubs.b)
    expect(out.clubs.a.stats).toEqual(fx.after[0])
    expect(out.clubs.a.mu_c).toBeCloseTo(fx.after[0].carry.m, 12)
    expect(out.clubs.a.p).toBe(c.p)
    expect(out.lie).toBe(two.lie)
    expect(out.putting).toBe(two.putting)
  })

  it('folds every observation in order', () => {
    const obs = fx.observations.map(([carry, total, lateral]) => ({ club: 'a', carry, total, lateral }))
    expectStats(learnedPlayer(two, obs).clubs.a.stats as ClubStats, fx.after[4])
  })

  it('starts an interpolated club from a 5 pseudo-shot prior on its point estimates and keeps it marked interpolated', () => {
    const out = learnedPlayer(two, [{ club: 'b', carry: c.mu_c + 6, total: c.mu_c + 6 + c.mu_r, lateral: 0 }])
    expect(out.clubs.b.sampled).toBe(false)
    expect(out.clubs.b.stats?.n).toBe(1)
    expect(out.clubs.b.mu_c).toBeCloseTo(c.mu_c + 1, 9) // one shot against five pseudo-shots
    expect(out.clubs.b.mu_r).toBeCloseTo(c.mu_r, 9)
    expect(out.clubs.b.sigma_theta_deg).toBeLessThan(c.sigma_theta_deg) // a dead straight shot
    expect(out.clubs.a).toBe(two.clubs.a)
  })

  it('ignores observations for clubs the player does not carry', () => {
    expect(learnedPlayer(two, [{ club: 'putter', carry: 1, total: 1, lateral: 0 }])).toBe(two)
  })
})
