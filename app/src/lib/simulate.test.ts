import { describe, expect, it } from 'vitest'

import { valueNearest } from './grid'
import { mulberry32 } from './rng'
import {
  animationPosition,
  blowUpShare,
  histogram,
  histogramBins,
  histogramMean,
  MAX_SHOTS,
  playOut,
  samplePutts,
  type Shot,
} from './simulate'
import { readToyBundle, toyPlayerDoc } from './toyFiles'

const b = readToyBundle()
const player = toyPlayerDoc()
const tee = { x: b.meta.tee_xy[0], y: b.meta.tee_xy[1] }

describe('playOut', () => {
  it('ends within 12 shots with strokes between 2 and 10, following the grid policy', () => {
    const rng = mulberry32(11)
    for (let k = 0; k < 200; k++) {
      const { shots, strokes } = playOut(b, player, tee, 2, 'drop', rng)
      expect(shots.length).toBeGreaterThanOrEqual(1)
      expect(shots.length).toBeLessThanOrEqual(MAX_SHOTS)
      expect(strokes).toBeGreaterThanOrEqual(2)
      expect(strokes).toBeLessThanOrEqual(10)
      expect(Number.isInteger(strokes)).toBe(true)
      expect(shots[0].from).toEqual(tee)
      expect(shots[0].club).toBe('test7i')
      for (const s of shots) expect([-1, -2]).toContain(s.reward)
    }
  })

  it('is deterministic for a seed', () => {
    const a = playOut(b, player, tee, 2, 'replay', mulberry32(5))
    const c = playOut(b, player, tee, 2, 'replay', mulberry32(5))
    expect(a).toEqual(c)
    const d = playOut(b, player, tee, 2, 'replay', mulberry32(6))
    expect(d.shots.map((s) => s.to)).not.toEqual(a.shots.map((s) => s.to))
  })

  it('counts penalties: strokes = shots + penalties + putts', () => {
    const { shots, strokes } = playOut(b, player, tee, 2, 'replay', mulberry32(21))
    const penalties = shots.reduce((n, s) => n + (s.reward === -2 ? 1 : 0), 0)
    expect(strokes).toBeGreaterThanOrEqual(shots.length + penalties)
  })

  it('from the green it is zero shots and only putts', () => {
    const { shots, strokes } = playOut(b, player, { x: b.meta.pin_xy[0], y: b.meta.pin_xy[1] }, 5, 'drop', mulberry32(1))
    expect(shots).toEqual([])
    expect([1, 2, 3]).toContain(strokes)
  })
})

describe('samplePutts', () => {
  it('holes in one with probability 2 - E, clamped, else 2, else 3', () => {
    // E = 1.5 everywhere on the toy player: p1 = 0.5
    let ones = 0
    const rng = mulberry32(2)
    for (let k = 0; k < 4000; k++) if (samplePutts(1.5, rng) === 1) ones += 1
    expect(ones / 4000).toBeGreaterThan(0.45)
    expect(ones / 4000).toBeLessThan(0.55)
    expect(samplePutts(1.0, () => 0.999)).toBe(1) // p1 clamps to 1
    expect(samplePutts(2.6, () => 0.0)).toBe(2) // p1 clamps to 0: 2 or 3; u = 0 gives 2
    expect(samplePutts(2.6, () => 0.99)).toBe(3)
  })

  it('has mean close to E for E in [1, 2]', () => {
    const rng = mulberry32(3)
    let sum = 0
    for (let k = 0; k < 4000; k++) sum += samplePutts(1.3, rng)
    expect(sum / 4000).toBeCloseTo(1.3, 1)
  })
})

describe('histogram', () => {
  it('counts sum to n and the mean is within 0.3 of valueNearest at the start', () => {
    const h = histogram(b, player, tee, 2, 'drop', 1000, 7)
    let n = 0
    let sum = 0
    for (const [strokes, count] of h) {
      n += count
      sum += strokes * count
      expect(Number.isInteger(strokes)).toBe(true)
    }
    expect(n).toBe(1000)
    expect(Math.abs(sum / n - valueNearest(b, tee))).toBeLessThan(0.3)
  })

  it('is deterministic for a seed', () => {
    const a = histogram(b, player, tee, 2, 'drop', 200, 7)
    const c = histogram(b, player, tee, 2, 'drop', 200, 7)
    expect([...a.entries()].sort()).toEqual([...c.entries()].sort())
  })
})

describe('animationPosition (slice 5)', () => {
  const shots: Shot[] = [
    { from: { x: 0, y: 0 }, to: { x: 10, y: 0 }, club: 'a', dir_deg: 0, lie: 2, reward: -1 },
    { from: { x: 10, y: 0 }, to: { x: 10, y: 20 }, club: 'a', dir_deg: 0, lie: 2, reward: -1 },
  ]

  it('interpolates within the current shot and reports the completed ones', () => {
    expect(animationPosition(shots, 0, 600)).toEqual({ index: 0, pos: { x: 0, y: 0 }, done: false })
    expect(animationPosition(shots, 300, 600)).toEqual({ index: 0, pos: { x: 5, y: 0 }, done: false })
    expect(animationPosition(shots, 900, 600)).toEqual({ index: 1, pos: { x: 10, y: 10 }, done: false })
  })

  it('is done at the last shot end and clamps beyond it', () => {
    expect(animationPosition(shots, 1200, 600)).toEqual({ index: 1, pos: { x: 10, y: 20 }, done: true })
    expect(animationPosition(shots, 5000, 600)).toEqual({ index: 1, pos: { x: 10, y: 20 }, done: true })
    expect(animationPosition([], 0, 600)).toEqual({ index: -1, pos: null, done: true })
  })

  it('eases in and out: slow off the club face and slow into the landing', () => {
    const quarter = animationPosition(shots, 150, 600).pos
    const threeQuarter = animationPosition(shots, 450, 600).pos
    expect(quarter?.x).toBeLessThan(2.5)
    expect(10 - (threeQuarter?.x ?? 0)).toBeLessThan(2.5)
  })
})

describe('histogram bins and blow-up (slice 6)', () => {
  const h = new Map<number, number>([
    [2, 10],
    [3, 200],
    [4, 400],
    [5, 250],
    [6, 90],
    [7, 30],
    [8, 15],
    [11, 5],
  ])

  it('bins par - 2 to par + 4 with overflow bins at both ends', () => {
    const bins = histogramBins(h, 4)
    expect(bins.map((b) => b.label)).toEqual(['<2', '2', '3', '4', '5', '6', '7', '8', '>8'])
    expect(bins.map((b) => b.count)).toEqual([0, 10, 200, 400, 250, 90, 30, 15, 5])
    expect(bins.reduce((s, b) => s + b.count, 0)).toBe(1000)
    expect(bins[3].isPar).toBe(true)
  })

  it('puts scores below par - 2 in the low overflow bin', () => {
    const bins = histogramBins(new Map([[1, 3], [2, 4]]), 4)
    expect(bins[0].count).toBe(3)
    expect(bins[1].count).toBe(4)
  })

  it('blow-up is the share at or above par + 3', () => {
    expect(blowUpShare(h, 4)).toBeCloseTo((30 + 15 + 5) / 1000, 9)
    expect(blowUpShare(new Map(), 4)).toBeNaN()
  })

  it('histogramMean averages the counts', () => {
    expect(histogramMean(h)).toBeCloseTo((20 + 600 + 1600 + 1250 + 540 + 210 + 120 + 55) / 1000, 9)
  })
})
