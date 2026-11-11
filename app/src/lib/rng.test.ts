import { describe, expect, it } from 'vitest'

import fixture from '../../../docs/fixtures/shot_samples.json'
import { mulberry32, normal } from './rng'

describe('mulberry32', () => {
  it('matches the Python fixture uniforms for seed 42', () => {
    const rng = mulberry32(fixture.seed)
    expect([rng(), rng(), rng()]).toEqual(fixture.uniforms)
  })

  it('is deterministic per seed and uniform in [0, 1)', () => {
    const a = mulberry32(7)
    const b = mulberry32(7)
    const xs = Array.from({ length: 2000 }, () => a())
    expect(Array.from({ length: 2000 }, () => b())).toEqual(xs)
    expect(xs.every((u) => u >= 0 && u < 1)).toBe(true)
    const mean = xs.reduce((s, u) => s + u, 0) / xs.length
    expect(mean).toBeGreaterThan(0.45)
    expect(mean).toBeLessThan(0.55)
    expect(mulberry32(8)()).not.toBe(xs[0])
  })
})

describe('normal', () => {
  it('is Box-Muller consuming exactly two uniforms per call', () => {
    let calls = 0
    const rng = () => {
      calls += 1
      return 0.5
    }
    const z = normal(rng)
    expect(calls).toBe(2)
    expect(z).toBeCloseTo(Math.sqrt(-2 * Math.log(0.5)) * Math.cos(Math.PI), 12)
  })

  it('has roughly zero mean and unit variance', () => {
    const rng = mulberry32(1)
    const zs = Array.from({ length: 20000 }, () => normal(rng))
    const mean = zs.reduce((s, z) => s + z, 0) / zs.length
    const variance = zs.reduce((s, z) => s + (z - mean) ** 2, 0) / zs.length
    expect(Math.abs(mean)).toBeLessThan(0.03)
    expect(variance).toBeGreaterThan(0.95)
    expect(variance).toBeLessThan(1.05)
  })
})
