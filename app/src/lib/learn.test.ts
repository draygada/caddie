import { readFileSync } from 'node:fs'
import { dirname, join } from 'node:path'
import { fileURLToPath } from 'node:url'

import { describe, expect, it } from 'vitest'

import { updateClubStats, updateIg, updateNig } from './learn'
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
