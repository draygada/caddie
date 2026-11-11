/**
 * Play-it-out: one simulated sequence from a point under the grid policy (part 13), and a
 * histogram of many. Mirrors solver/caddie/online.py `sample_sequence`; the shot model is
 * shot.ts, so the histogram mean should match the value grid within about 0.3 strokes.
 */
import { distance, lieAt, policyAt } from './grid'
import { expectedPutts, sampleShot } from './shot'
import type { HoleBundle, Lie, Mode, Player, XY } from './types'

export const MAX_SHOTS = 12

export interface Shot {
  from: XY
  to: XY
  club: string
  dir_deg: number
  /** lie where the ball came to rest (7 for OB or off the hole) */
  lie: Lie
  reward: number
}

/**
 * Whole putts from an expected-putts value: one putt with probability `2 - E` (clamped to
 * [0, 1]), otherwise two, with a three-putt share so the mean stays near E above 2.
 */
export function samplePutts(expected: number, rng: () => number): number {
  const p1 = Math.min(Math.max(2 - expected, 0), 1)
  const u = rng()
  if (u < p1) return 1
  // among the misses, three-putt with probability (E - 2 + p1) / (1 - p1) clamped
  const p3 = Math.min(Math.max((expected - 2 + p1) / Math.max(1 - p1, 1e-9), 0), 1)
  const v = (u - p1) / Math.max(1 - p1, 1e-9)
  return v < 1 - p3 ? 2 : 3
}

export interface PlayOut {
  shots: Shot[]
  /** strokes to hole out: shots plus penalties plus putts */
  strokes: number
}

function lieAfter(b: HoleBundle, p: XY): Lie {
  return lieAt(b, p)
}

/** Follow `policyAt` (nearest cell) from `from` until a green cell, then sample the putts. */
export function playOut(b: HoleBundle, player: Player, from: XY, lie: Lie, mode: Mode, rng: () => number): PlayOut {
  const shots: Shot[] = []
  let pos = { x: from.x, y: from.y }
  let currentLie: Lie = lie
  let strokes = 0
  const pin = { x: b.meta.pin_xy[0], y: b.meta.pin_xy[1] }
  for (let k = 0; k < MAX_SHOTS && currentLie !== 5; k++) {
    const policy = policyAt(b, pos)
    if (!policy) break // off the hole with no action: stop
    const s = sampleShot(b, player, pos, currentLie, policy.club, policy.dir_deg, mode, rng)
    shots.push({ from: pos, to: { x: s.x, y: s.y }, club: policy.club, dir_deg: policy.dir_deg, lie: s.lie, reward: s.reward })
    strokes += -s.reward
    pos = s.next
    currentLie = s.reward === -1 ? s.lie : lieAfter(b, pos)
    if (currentLie < 1 || currentLie > 5) currentLie = lieAfter(b, pos)
  }
  if (currentLie === 5) strokes += samplePutts(expectedPutts(player, distance(pos, pin)), rng)
  return { shots, strokes }
}
