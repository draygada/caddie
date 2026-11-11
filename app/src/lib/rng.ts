/**
 * Seedable randomness shared with the solver's online.py so Python and TypeScript can
 * be compared on the same seed (docs/fixtures/shot_samples.json).
 */

/** mulberry32: a 32-bit generator; the returned function gives uniforms in [0, 1). */
export function mulberry32(seed: number): () => number {
  let a = seed >>> 0
  return () => {
    a = (a + 0x6d2b79f5) >>> 0
    let t = a
    t = Math.imul(t ^ (t >>> 15), t | 1)
    t ^= t + Math.imul(t ^ (t >>> 7), t | 61)
    return ((t ^ (t >>> 14)) >>> 0) / 4294967296
  }
}

/** Standard normal by Box-Muller, always consuming two uniforms: sqrt(-2 ln(1 - u1)) cos(2 pi u2). */
export function normal(rng: () => number): number {
  const u1 = rng()
  const u2 = rng()
  return Math.sqrt(-2 * Math.log(1 - u1)) * Math.cos(2 * Math.PI * u2)
}
