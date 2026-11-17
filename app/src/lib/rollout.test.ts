import { describe, expect, it } from 'vitest'

import { cellOf, centreOf, policyAt, valueNearest } from './grid'
import { mulberry32 } from './rng'
import { candidateClubs, recommend, TEE_ONLY_CLUBS } from './rollout'
import { readToyBundle, toyPlayerDoc } from './toyFiles'
import type { Lie, Player } from './types'

const b = readToyBundle()
const player = toyPlayerDoc()

function samplePlayableCells(n: number, seed: number): number[] {
  const playable: number[] = []
  for (let i = 0; i < b.lie.length; i++) if (b.lie[i] >= 1 && b.lie[i] <= 4) playable.push(i)
  const rng = mulberry32(seed)
  const out: number[] = []
  while (out.length < n) {
    const i = playable[Math.floor(rng() * playable.length)]
    if (!out.includes(i)) out.push(i)
  }
  return out
}

describe('recommend parity with the policy grid (toy bundle, m = 400)', () => {
  const cells = samplePlayableCells(10, 3).map((i) => ({
    i,
    p: centreOf(b, Math.floor(i / b.meta.cols), i % b.meta.cols),
    lie: b.lie[i] as Lie,
  }))

  it('agrees with the grid up to ties: same club, grid direction within 0.05 of the best, value within 0.35', () => {
    for (const { i, p, lie } of cells) {
      const r = recommend(b, player, p, lie, 'drop', 400, i)
      const grid = policyAt(b, p)
      expect(grid).not.toBeNull()
      if (!grid) return
      expect(r.club).toBe(grid.club)
      const ci = player.club_order.indexOf(r.club)
      const di = b.meta.directions_deg.indexOf(grid.dir_deg)
      expect(r.q[ci * b.meta.directions_deg.length + di] - r.expected_strokes).toBeLessThan(0.05)
      expect(Math.abs(r.expected_strokes - valueNearest(b, p))).toBeLessThan(0.35)
    }
  })

  // Part file band: exact direction match for 9 of 10 cells. The toy hole has direction
  // ties (Q equal to 3 decimals), so fresh draws pick another tied direction for about
  // 3 of 10 cells, as in solver part 06. Strict expected failure until Diego decides.
  it.fails('returns the grid direction for 9 of 10 sampled cells', () => {
    let hits = 0
    for (const { i, p, lie } of cells) {
      const r = recommend(b, player, p, lie, 'drop', 400, i)
      if (r.dir_deg === policyAt(b, p)?.dir_deg) hits += 1
    }
    expect(hits).toBeGreaterThanOrEqual(9)
  })

  it('q covers clubs x directions and the best entry is the recommendation', () => {
    const r = recommend(b, player, { x: 27.5, y: 2.5 }, 2, 'drop', 100, 1)
    expect(r.q.length).toBe(player.club_order.length * b.meta.directions_deg.length)
    let best = Infinity
    for (const v of r.q) if (Number.isFinite(v) && v < best) best = v
    expect(r.expected_strokes).toBeCloseTo(best, 5) // q is Float32
    expect(r.baseline_pin_strokes).toBeGreaterThanOrEqual(r.expected_strokes - 1e-9)
    expect(b.meta.directions_deg).toContain(r.dir_deg)
  })

  it('is deterministic for a seed', () => {
    const a = recommend(b, player, { x: 12, y: 17 }, 2, 'replay', 50, 5)
    const c = recommend(b, player, { x: 12, y: 17 }, 2, 'replay', 50, 5)
    expect(Array.from(a.q)).toEqual(Array.from(c.q))
    const d = recommend(b, player, { x: 12, y: 17 }, 2, 'replay', 50, 6)
    expect(Array.from(d.q)).not.toEqual(Array.from(a.q))
  })

  it('a lie override costs more from the rough than from the fairway', () => {
    const fw = recommend(b, player, { x: 12, y: 17 }, 2, 'drop', 400, 2)
    const rough = recommend(b, player, { x: 12, y: 17 }, 3, 'drop', 400, 2)
    expect(rough.expected_strokes).toBeGreaterThan(fw.expected_strokes)
    expect(cellOf(b, { x: 12, y: 17 }).i).toBeGreaterThan(0)
  })
})

describe('tee-only driver (part 17)', () => {
  const toy = readToyBundle()
  const base = toyPlayerDoc()
  const bag: Player = {
    ...base,
    clubs: {
      driver: { ...base.clubs.test7i, mu_c: 30 },
      test7i: base.clubs.test7i,
    },
    club_order: ['driver', 'test7i'],
  }
  const far = { x: 27.5, y: 2.5 } // 45 m from the pin: both clubs pass the 1.3 x distance rule

  it('lists the driver from a tee lie only', () => {
    expect(TEE_ONLY_CLUBS).toEqual(['driver'])
    expect(candidateClubs(toy, bag, far, 1)).toEqual([0, 1])
    for (const lie of [2, 3, 4] as Lie[]) expect(candidateClubs(toy, bag, far, lie)).toEqual([1])
  })

  it('keeps the shortest club when the driver was the only candidate', () => {
    const onlyDriver: Player = { ...bag, clubs: { driver: bag.clubs.driver }, club_order: ['driver'] }
    expect(candidateClubs(toy, onlyDriver, far, 2)).toEqual([0])
  })

  it('leaves a bag without a driver alone', () => {
    expect(candidateClubs(toy, base, far, 2)).toEqual(candidateClubs(toy, base, far, 1))
  })

  it('recommend never returns the driver off the fairway, and plays trees as rough', () => {
    const fairway = recommend(toy, bag, far, 2, 'drop', 20, 1)
    expect(fairway.club).toBe('test7i')
    const tee = recommend(toy, bag, far, 1, 'drop', 20, 1)
    expect(['driver', 'test7i']).toContain(tee.club)
    expect(recommend(toy, bag, far, 8, 'drop', 20, 1)).toEqual(recommend(toy, bag, far, 3, 'drop', 20, 1))
  })
})
