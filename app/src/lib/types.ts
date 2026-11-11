/** Types for the data contract in the root CLAUDE.md. Pure TypeScript, no React. */

export type Lie = 0 | 1 | 2 | 3 | 4 | 5 | 6 | 7
export type Mode = 'mulligan' | 'drop' | 'replay'

export interface NIG {
  m: number
  kappa: number
  alpha: number
  beta: number
}
export interface IG {
  alpha: number
  beta: number
}
export interface ClubStats {
  n: number
  carry: NIG
  theta: IG
  roll: NIG
}
/** `stats` is carried through unused until part 15. */
export interface ClubParams {
  mu_c: number
  sigma_theta_deg: number
  sigma_d: number
  p: number
  mu_r: number
  sigma_r: number
  sampled: boolean
  stats: ClubStats | null
}
export type LieName = 'tee' | 'fairway' | 'rough' | 'bunker'
export interface LieMultipliers {
  carry: number
  sigma: number
  roll: number
}
export interface Player {
  handicap: number
  clubs: Record<string, ClubParams>
  club_order: string[]
  lie: Record<LieName, LieMultipliers>
  putting: { distance_m: number[]; expected_putts: number[] }
}

/** `meta.json`. `hole` is `'toy'` for the fixture bundle the solver's `all --holes toy` writes. */
export interface Meta {
  hole: number | 'toy'
  par: number
  penalty_mode: Mode
  rows: number
  cols: number
  cell_m: number
  origin: { lat: number; lon: number }
  rotation_deg: number
  tee_xy: [number, number]
  tees: Record<string, [number, number]>
  pin_xy: [number, number]
  clubs: string[]
  directions_deg: number[]
  polygons: Record<string, [number, number][][]>
}

/** Typed arrays of length `rows * cols`, index `r * cols + c`. */
export interface HoleBundle {
  meta: Meta
  lie: Uint8Array
  value: Float32Array
  club: Uint8Array
  dir: Uint8Array
}

export interface XY {
  x: number
  y: number
}
