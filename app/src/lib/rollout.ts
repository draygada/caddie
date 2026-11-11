/**
 * Rollout lookahead (Ch 9.2) at a continuous point, matching solver/caddie/online.py
 * `recommend`: one sampled shot per draw for every candidate action, then the value grid
 * at the landing by bilinear interpolation (expected putts when the landing is on the
 * green). Candidate clubs are those with mu_c <= 1.3 x distance to the pin, the shortest
 * club always kept. The pin baseline (direction 0, longest club that reaches) uses the
 * same draws, so the comparison is paired.
 */
import { distance, valueBilinear } from './grid'
import { mulberry32 } from './rng'
import { expectedPutts, sampleShot } from './shot'
import type { HoleBundle, Lie, Mode, Player, XY } from './types'

export const CANDIDATE_CARRY_FACTOR = 1.3

export interface RolloutResult {
  club: string
  dir_deg: number
  expected_strokes: number
  baseline_pin_strokes: number
  /** strokes-to-go per (club, direction), row-major clubs x dirs, NaN where pruned */
  q: Float32Array
}

/** Clubs worth evaluating from `from`: mu_c <= 1.3 x distance to the pin, shortest always kept. */
export function candidateClubs(b: HoleBundle, player: Player, from: XY): number[] {
  const pin = { x: b.meta.pin_xy[0], y: b.meta.pin_xy[1] }
  const d = distance(from, pin)
  const mus = player.club_order.map((c) => player.clubs[c].mu_c)
  const keep = mus.map((mu, i) => (mu <= CANDIDATE_CARRY_FACTOR * d ? i : -1)).filter((i) => i >= 0)
  if (keep.length === 0) keep.push(mus.indexOf(Math.min(...mus)))
  return keep
}

/** Leaf value at a landing: expected putts on the green, else the interpolated grid value. */
function leafValue(b: HoleBundle, player: Player, p: XY, lie: Lie): number {
  if (lie === 5) {
    const pin = { x: b.meta.pin_xy[0], y: b.meta.pin_xy[1] }
    return expectedPutts(player, distance(p, pin))
  }
  const v = valueBilinear(b, p)
  return Number.isFinite(v) ? v : NaN
}

/** Mean strokes-to-go of one action over `draws` fresh shots from one seed. */
function actionValue(
  b: HoleBundle,
  player: Player,
  from: XY,
  lie: Lie,
  club: string,
  dir_deg: number,
  mode: Mode,
  m: number,
  seed: number,
): number {
  const rng = mulberry32(seed)
  let sum = 0
  for (let j = 0; j < m; j++) {
    const s = sampleShot(b, player, from, lie, club, dir_deg, mode, rng)
    const next = s.next
    const nextLie = s.reward === -1 ? s.lie : lieOfNext(b, next)
    sum += -s.reward + leafValue(b, player, next, nextLie)
  }
  return sum / m
}

function lieOfNext(b: HoleBundle, p: XY): Lie {
  const { cols, cell_m } = b.meta
  const r = Math.floor(p.y / cell_m)
  const c = Math.floor(p.x / cell_m)
  return b.lie[r * cols + c] as Lie
}

export function recommend(
  b: HoleBundle,
  player: Player,
  from: XY,
  lie: Lie,
  mode: Mode,
  m = 100,
  seed = 1,
): RolloutResult {
  if (lie === 5 || lie < 1 || lie > 5) throw new Error(`no shot from lie ${lie}`)
  const dirs = b.meta.directions_deg
  const nClubs = player.club_order.length
  const q = new Float32Array(nClubs * dirs.length).fill(NaN)
  let best = Infinity
  let bestClub = -1
  let bestDir = -1
  for (const ci of candidateClubs(b, player, from)) {
    const club = player.club_order[ci]
    for (let di = 0; di < dirs.length; di++) {
      const v = actionValue(b, player, from, lie, club, dirs[di], mode, m, seed)
      q[ci * dirs.length + di] = v
      if (v < best) {
        best = v
        bestClub = ci
        bestDir = di
      }
    }
  }
  if (bestClub < 0) throw new Error('no finite action value')

  const pin = { x: b.meta.pin_xy[0], y: b.meta.pin_xy[1] }
  const d = distance(from, pin)
  const mus = player.club_order.map((c) => player.clubs[c].mu_c)
  let baseCi = -1
  for (let i = 0; i < mus.length; i++) if (mus[i] <= d && (baseCi < 0 || mus[i] > mus[baseCi])) baseCi = i
  if (baseCi < 0) baseCi = mus.indexOf(Math.min(...mus))
  const zero = dirs.indexOf(0)
  const stored = q[baseCi * dirs.length + zero]
  const baseline = Number.isFinite(stored)
    ? stored
    : actionValue(b, player, from, lie, player.club_order[baseCi], 0, mode, m, seed)

  return {
    club: player.club_order[bestClub],
    dir_deg: dirs[bestDir],
    expected_strokes: best,
    baseline_pin_strokes: baseline,
    q,
  }
}
