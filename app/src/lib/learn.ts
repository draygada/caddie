/**
 * On-course learning (part 15): the TypeScript port of the conjugate updates in
 * solver/caddie/dispersion.py (Ch 4.2). Pure, no React. docs/fixtures/stats_updates.json
 * is the parity fixture.
 */
import type { ClubStats, IG, NIG } from './types'

/** Normal with unknown mean and variance: one observation `x`. */
export function updateNig(s: NIG, x: number): NIG {
  const kappa = s.kappa + 1
  return {
    m: (s.kappa * s.m + x) / kappa,
    kappa,
    alpha: s.alpha + 0.5,
    beta: s.beta + (s.kappa * (x - s.m) ** 2) / (2 * kappa),
  }
}

/** Variance of a zero-mean normal: one observed angle `theta` in degrees. */
export function updateIg(s: IG, theta: number): IG {
  return { alpha: s.alpha + 0.5, beta: s.beta + theta ** 2 / 2 }
}

/** Fold one shot in: carry, total and lateral in meters, as `update_club_stats` in the solver. */
export function updateClubStats(s: ClubStats, carry: number, total: number, lateral: number): ClubStats {
  const theta = (Math.atan2(lateral, carry) * 180) / Math.PI
  return {
    n: s.n + 1,
    carry: updateNig(s.carry, carry),
    theta: updateIg(s.theta, theta),
    roll: updateNig(s.roll, total - carry),
  }
}
