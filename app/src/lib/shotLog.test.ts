import { readFileSync } from 'node:fs'
import { dirname, join } from 'node:path'
import { fileURLToPath } from 'node:url'

import { describe, expect, it } from 'vitest'

import { learnedPlayer, updateClubStats } from './learn'
import {
  DWELL_MS,
  DWELL_RADIUS_M,
  exportFileName,
  exportLog,
  type LoggedShot,
  MAX_AIM_CHANGE_DEG,
  MAX_LEARN_ACCURACY_M,
  MIN_SHOT_M,
  shouldPromptLanding,
  skipReason,
  toObservation,
  updateDwell,
} from './shotLog'
import { testBundle } from './testBundle'
import { readToyBundle } from './toyFiles'
import type { ClubParams, ClubStats, HoleBundle, Player } from './types'

/** A 50 m wide, 250 m long strip: fairway, with a rough column on the right and a green row at the far end. */
function strip(): HoleBundle {
  const rows = 50
  const cols = 10
  const lie = new Uint8Array(rows * cols).fill(2)
  for (let r = 0; r < rows; r++) lie[r * cols + 9] = 3
  for (let c = 0; c < cols; c++) lie[49 * cols + c] = 5
  return testBundle(
    { lie, value: new Float32Array(rows * cols), club: new Uint8Array(rows * cols), dir: new Uint8Array(rows * cols) },
    { rows, cols, pin_xy: [27.5, 247.5] },
  )
}

const CLUB = { mu_c: 140, sigma_theta_deg: 5, sigma_d: 0.06, p: 0.05, mu_r: 6, sigma_r: 2, sampled: true, stats: null }
const player: Player = {
  handicap: 15,
  clubs: { '7i': CLUB },
  club_order: ['7i'],
  lie: {
    tee: { carry: 1, sigma: 1, roll: 1 },
    fairway: { carry: 1, sigma: 1, roll: 1 },
    rough: { carry: 0.9, sigma: 1.3, roll: 0.5 },
    bunker: { carry: 0.8, sigma: 1.6, roll: 0 },
  },
  putting: { distance_m: [1], expected_putts: [1.5] },
}

function shot(over: Partial<LoggedShot> = {}): LoggedShot {
  return {
    start: { x: 22.5, y: 12.5 },
    end: { x: 22.5, y: 162.5 },
    startAcc: 4,
    endAcc: 5,
    lie: 2,
    club: '7i',
    aimDeg: 0,
    recAimDeg: 0,
    t: 1,
    outcome: 'normal',
    ...over,
  }
}

describe('toObservation', () => {
  const b = strip()

  it('straight 150 m on the fairway: carry is total less the mean roll, no lateral', () => {
    const o = toObservation(b, player, shot())
    expect(o).not.toBeNull()
    expect(o?.club).toBe('7i')
    expect(o?.total).toBeCloseTo(150, 9)
    expect(o?.carry).toBeCloseTo(144, 9)
    expect(o?.lateral).toBeCloseTo(0, 9)
  })

  it('10 m right: update_club_stats recovers the observed angle', () => {
    const o = toObservation(b, player, shot({ end: { x: 32.5, y: 162.5 } }))
    if (!o) throw new Error('skipped')
    const total = Math.hypot(10, 150)
    const theta = Math.atan2(10, 150)
    expect(o.total).toBeCloseTo(total, 9)
    expect(o.carry).toBeCloseTo(total - 6, 9)
    expect(o.lateral).toBeCloseTo((total - 6) * Math.tan(theta), 9)
    expect(o.lateral).toBeGreaterThan(0)
    const prior = { n: 0, carry: { m: 140, kappa: 5, alpha: 2.5, beta: 100 }, theta: { alpha: 2.5, beta: 0 }, roll: { m: 6, kappa: 5, alpha: 2.5, beta: 6 } }
    const after = updateClubStats(prior, o.carry, o.total, o.lateral)
    expect(after.theta.beta).toBeCloseTo(((theta * 180) / Math.PI) ** 2 / 2, 9)
    expect(after.roll.m).toBeCloseTo(6, 9)
  })

  it('measures left and right against the aim line, not the grid', () => {
    // Aimed 90 degrees (along +x) from the left edge; the ball finishes 3 m up the hole: left of the line.
    const o = toObservation(b, player, shot({ start: { x: 2.5, y: 100 }, end: { x: 42.5, y: 103 }, aimDeg: 90, recAimDeg: 90 }))
    expect(o?.lateral).toBeLessThan(0)
  })

  it('uses the roll multiplier of the lie where the ball stopped', () => {
    const rough = toObservation(b, player, shot({ end: { x: 47.5, y: 162.5 } }))
    expect(rough?.carry).toBeCloseTo(Math.hypot(25, 150) - 6 * 0.5, 9)
    const stored = toObservation(b, player, shot({ endLie: 4 }))
    expect(stored?.carry).toBeCloseTo(150, 9) // bunker: no roll, and the stored lie wins over the grid
    const green = toObservation(b, player, shot({ end: { x: 22.5, y: 247.5 }, outcome: 'green' }))
    expect(green?.carry).toBeCloseTo(235 - 6, 9)
  })

  it('skips a penalty shot', () => {
    const s = shot({ outcome: 'penalty' })
    expect(skipReason(b, player, s)).toBe('penalty')
    expect(toObservation(b, player, s)).toBeNull()
  })

  it('skips when either end has accuracy worse than 10 m; a dragged end (0) is trusted', () => {
    expect(MAX_LEARN_ACCURACY_M).toBe(10)
    expect(skipReason(b, player, shot({ endAcc: 10.5 }))).toBe('accuracy')
    expect(skipReason(b, player, shot({ startAcc: 25 }))).toBe('accuracy')
    expect(skipReason(b, player, shot({ startAcc: 10, endAcc: 0 }))).toBeNull()
  })

  it('skips when the aim was moved more than 30 degrees off the recommendation', () => {
    expect(MAX_AIM_CHANGE_DEG).toBe(30)
    expect(skipReason(b, player, shot({ aimDeg: 31 }))).toBe('aim')
    expect(skipReason(b, player, shot({ aimDeg: -30 }))).toBeNull()
    expect(skipReason(b, player, shot({ aimDeg: 175, recAimDeg: -175, end: { x: 22.5, y: 2 }, start: { x: 22.5, y: 152 } }))).toBeNull()
  })

  it('skips a shot that started on the green, one still open, and an unknown club', () => {
    expect(skipReason(b, player, shot({ lie: 5 }))).toBe('green')
    expect(skipReason(b, player, shot({ end: null, endAcc: null }))).toBe('open')
    expect(skipReason(b, player, shot({ club: 'putter' }))).toBe('club')
  })

  it('skips a shot too short to leave a carry after the mean roll, or one that went backwards', () => {
    expect(skipReason(b, player, shot({ end: { x: 22.5, y: 17.5 } }))).toBe('short')
    expect(skipReason(b, player, shot({ end: { x: 22.5, y: 2.5 } }))).toBe('short')
  })
})

// --- slice 7: parity with the solver's load_course_log and fold_course_shots -------------------

interface CourseFixture {
  player: Player
  log: { version: number; hole: string; shots: LoggedShot[] }
  skipped: Record<string, string>
  observations: Record<string, [number, number, number][]>
  after: Record<string, ClubStats>
  learned: Record<string, ClubParams>
}

const COURSE = JSON.parse(
  readFileSync(join(dirname(fileURLToPath(import.meta.url)), '..', '..', '..', 'docs', 'fixtures', 'course_log.json'), 'utf8'),
) as CourseFixture

describe('docs/fixtures/course_log.json: 20 synthetic shots, Python and TypeScript agree', () => {
  const toy = readToyBundle()
  const { player, log } = COURSE

  it('skips the same shots for the same reasons', () => {
    expect(log.shots).toHaveLength(20)
    log.shots.forEach((s, k) => expect(skipReason(toy, player, s) ?? undefined).toBe(COURSE.skipped[String(k)]))
  })

  it('gives the same observations to 1e-9', () => {
    const got: Record<string, [number, number, number][]> = {}
    for (const s of log.shots) {
      const o = toObservation(toy, player, s)
      if (o) (got[o.club] ??= []).push([o.carry, o.total, o.lateral])
    }
    expect(Object.keys(got).sort()).toEqual(Object.keys(COURSE.observations).sort())
    for (const [club, rows] of Object.entries(COURSE.observations)) {
      expect(got[club]).toHaveLength(rows.length)
      rows.forEach((row, k) => row.forEach((v, j) => expect(Math.abs(got[club][k][j] - v)).toBeLessThan(1e-9)))
    }
  })

  it('moves the posterior the same amount, and only for the clubs hit', () => {
    const obs = log.shots.map((s) => toObservation(toy, player, s)).filter((o) => o !== null)
    const learned = learnedPlayer(player, obs)
    for (const [club, want] of Object.entries(COURSE.after)) {
      const got = learned.clubs[club].stats
      if (!got) throw new Error(`${club} has no stats`)
      expect(got.n).toBe(want.n)
      for (const k of ['m', 'kappa', 'alpha', 'beta'] as const) {
        expect(Math.abs(got.carry[k] - want.carry[k])).toBeLessThan(1e-9)
        expect(Math.abs(got.roll[k] - want.roll[k])).toBeLessThan(1e-9)
      }
      expect(Math.abs(got.theta.beta - want.theta.beta)).toBeLessThan(1e-9)
      for (const k of ['mu_c', 'sigma_theta_deg', 'sigma_d', 'p', 'mu_r', 'sigma_r'] as const)
        expect(Math.abs(learned.clubs[club][k] - COURSE.learned[club][k])).toBeLessThan(1e-9)
      expect(learned.clubs[club].sampled).toBe(COURSE.learned[club].sampled)
    }
    const changed = player.club_order.filter((c) => learned.clubs[c] !== player.clubs[c])
    expect(changed.sort()).toEqual(Object.keys(COURSE.after).sort())
    expect(learned.clubs.test5i).toBe(player.clubs.test5i)
  })
})

describe('exportLog', () => {
  it('is a JSON download the solver can read back: version, hole and the shots as logged', async () => {
    const blob = exportLog(COURSE.log.shots, 'toy')
    expect(blob.type).toBe('application/json')
    expect(JSON.parse(await blob.text())).toEqual(COURSE.log)
  })

  it('names the file by round', () => {
    expect(exportFileName('2026-11-17:11')).toBe('caddie-log-2026-11-17-hole-11.json')
  })
})

describe('landing prompt (slice 8)', () => {
  const hit = { x: 20, y: 10 }

  it('tracks how long the player has stayed within 5 m of one spot', () => {
    let d = updateDwell(null, { x: 20, y: 100 }, 1000)
    expect(d).toEqual({ anchor: { x: 20, y: 100 }, since: 1000 })
    d = updateDwell(d, { x: 23, y: 103 }, 9000) // 4.2 m away: still here
    expect(d.since).toBe(1000)
    d = updateDwell(d, { x: 20, y: 106 }, 12000) // 6 m from the anchor: walking again
    expect(d).toEqual({ anchor: { x: 20, y: 106 }, since: 12000 })
  })

  it('prompts after 20 s still, at least 20 m from the last Hit, while that shot is open', () => {
    expect(DWELL_RADIUS_M).toBe(5)
    expect(DWELL_MS).toBe(20_000)
    expect(MIN_SHOT_M).toBe(20)
    const d = { anchor: { x: 20, y: 100 }, since: 1000 }
    expect(shouldPromptLanding(d, hit, 20_999)).toBe(false)
    expect(shouldPromptLanding(d, hit, 21_000)).toBe(true)
    expect(shouldPromptLanding({ anchor: { x: 20, y: 29 }, since: 1000 }, hit, 60_000)).toBe(false) // 19 m
    expect(shouldPromptLanding(d, null, 60_000)).toBe(false) // no open shot
    expect(shouldPromptLanding(null, hit, 60_000)).toBe(false) // no fix
  })
})
