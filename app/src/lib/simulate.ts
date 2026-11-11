/**
 * Play-it-out: one simulated sequence from a point under the grid policy (part 13), and a
 * histogram of many. Mirrors solver/caddie/online.py `sample_sequence`; the shot model is
 * shot.ts, so the histogram mean should match the value grid within about 0.3 strokes.
 */
import { distance, lieAt, policyAt } from './grid'
import { mulberry32 } from './rng'
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

/** Strokes-to-hole-out counts over `n` play-outs from one seed: strokes -> count. */
export function histogram(
  b: HoleBundle,
  player: Player,
  from: XY,
  lie: Lie,
  mode: Mode,
  n = 1000,
  seed = 7,
): Map<number, number> {
  const rng = mulberry32(seed)
  const counts = new Map<number, number>()
  for (let k = 0; k < n; k++) {
    const { strokes } = playOut(b, player, from, lie, mode, rng)
    counts.set(strokes, (counts.get(strokes) ?? 0) + 1)
  }
  return counts
}

/** Mean of a histogram. */
export function histogramMean(h: Map<number, number>): number {
  let n = 0
  let sum = 0
  for (const [strokes, count] of h) {
    n += count
    sum += strokes * count
  }
  return n === 0 ? NaN : sum / n
}

// --- animation (slice 5) ----------------------------------------------------------------------

export const MS_PER_SHOT = 600

export interface AnimationFrame {
  /** index of the shot in flight or just finished; -1 for no shots */
  index: number
  pos: XY | null
  done: boolean
}

function smoothstep(t: number): number {
  const u = Math.min(Math.max(t, 0), 1)
  return u * u * (3 - 2 * u)
}

/** Ball position `elapsedMs` into an animation of `shots`, `msPerShot` each, eased in and out. */
export function animationPosition(shots: Shot[], elapsedMs: number, msPerShot = MS_PER_SHOT): AnimationFrame {
  if (shots.length === 0) return { index: -1, pos: null, done: true }
  const total = shots.length * msPerShot
  if (elapsedMs >= total) {
    const last = shots[shots.length - 1]
    return { index: shots.length - 1, pos: { x: last.to.x, y: last.to.y }, done: true }
  }
  const index = Math.min(Math.floor(elapsedMs / msPerShot), shots.length - 1)
  const t = smoothstep((elapsedMs - index * msPerShot) / msPerShot)
  const s = shots[index]
  return {
    index,
    pos: { x: s.from.x + (s.to.x - s.from.x) * t, y: s.from.y + (s.to.y - s.from.y) * t },
    done: false,
  }
}

// --- histogram view (slice 6) -------------------------------------------------------------------

export interface HistogramBin {
  label: string
  count: number
  isPar: boolean
}

/** Bars for par - 2 .. par + 4 with overflow bins `<par-2` and `>par+4`. */
export function histogramBins(h: Map<number, number>, par: number): HistogramBin[] {
  const lo = par - 2
  const hi = par + 4
  const bins: HistogramBin[] = [{ label: `<${lo}`, count: 0, isPar: false }]
  for (let s = lo; s <= hi; s++) bins.push({ label: String(s), count: h.get(s) ?? 0, isPar: s === par })
  bins.push({ label: `>${hi}`, count: 0, isPar: false })
  for (const [strokes, count] of h) {
    if (strokes < lo) bins[0].count += count
    else if (strokes > hi) bins[bins.length - 1].count += count
  }
  return bins
}

/** Share of play-outs at or above par + 3 (double bogey or worse); NaN for an empty histogram. */
export function blowUpShare(h: Map<number, number>, par: number): number {
  let n = 0
  let bad = 0
  for (const [strokes, count] of h) {
    n += count
    if (strokes >= par + 3) bad += count
  }
  return n === 0 ? NaN : bad / n
}
