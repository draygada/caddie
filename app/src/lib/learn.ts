/**
 * On-course learning (part 15): the TypeScript port of the conjugate updates in
 * solver/caddie/dispersion.py (Ch 4.2). Pure, no React. docs/fixtures/stats_updates.json
 * is the parity fixture.
 */
import type { ClubParams, ClubStats, IG, NIG } from './types'

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

/** Weight of the prior for a club with no stored stats, in pseudo-shots (the offline prior's weight). */
export const PRIOR_KAPPA = 5

function nigSd(s: NIG): number {
  return Math.sqrt(s.beta / (s.alpha - 1))
}

/** Posterior means as club parameters, as `params_from_stats` in the solver. `p` is not learned. */
export function paramsFromStats(s: ClubStats, p: number): ClubParams {
  const mu_c = s.carry.m
  return {
    mu_c,
    sigma_theta_deg: Math.sqrt(s.theta.beta / (s.theta.alpha - 1)),
    sigma_d: nigSd(s.carry) / mu_c,
    p,
    mu_r: s.roll.m,
    sigma_r: nigSd(s.roll),
    sampled: true,
    stats: s,
  }
}

/**
 * A prior worth `kappa` pseudo-shots centred on a club's point estimates, for clubs whose
 * `stats` is null (interpolated clubs). alpha = kappa / 2, and each beta is chosen so that
 * `paramsFromStats` returns the same point estimates.
 */
export function statsFromParams(c: ClubParams, kappa = PRIOR_KAPPA): ClubStats {
  const alpha = kappa / 2
  const scale = alpha - 1
  return {
    n: 0,
    carry: { m: c.mu_c, kappa, alpha, beta: scale * (c.sigma_d * c.mu_c) ** 2 },
    theta: { alpha, beta: scale * c.sigma_theta_deg ** 2 },
    roll: { m: c.mu_r, kappa, alpha, beta: scale * c.sigma_r ** 2 },
  }
}
