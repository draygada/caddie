/**
 * The generative shot model, mirroring solver/caddie/online.py `sample_landing` (and
 * mdp.step_batch) for one draw. Draw order per shot: theta normal, mixture uniform,
 * carry normal, roll normal. docs/fixtures/shot_samples.json is the parity fixture.
 */
import { cellOf, centreOf } from './grid'
import { normal } from './rng'
import type { HoleBundle, Lie, LieName, Mode, Player, XY } from './types'

/** Mishit mixture mean, fixed in the solver (dispersion.MISHIT_MEAN). */
export const MISHIT_MEAN = -2

export interface Landing {
  x: number
  y: number
  lie: Lie
  reward: number
  /** Where the ball plays from after the terrain rule. */
  next: XY
}

const FROM_LIE_NAME: Partial<Record<Lie, LieName>> = {
  1: 'tee',
  2: 'fairway',
  3: 'rough',
  4: 'bunker',
  5: 'fairway',
}

function rollMultiplier(player: Player, landingLie: Lie): number {
  switch (landingLie) {
    case 1:
      return player.lie.tee.roll
    case 2:
      return player.lie.fairway.roll
    case 3:
      return player.lie.rough.roll
    case 4:
      return player.lie.bunker.roll
    case 5:
      return 1
    default:
      return 0
  }
}

/** Bearing from `p` to the pin in degrees, 0 along +y, positive to the right. */
export function pinBearingDeg(b: HoleBundle, p: XY): number {
  const [px, py] = b.meta.pin_xy
  return (Math.atan2(px - p.x, py - p.y) * 180) / Math.PI
}

/** Flat index and lie at `p`; outside the grid or an OUT cell reads as OB (7). */
export function locate(b: HoleBundle, p: XY): { i: number; lie: Lie; outside: boolean } {
  const { rows, cols, cell_m } = b.meta
  const r = Math.floor(p.y / cell_m)
  const c = Math.floor(p.x / cell_m)
  const outside = r < 0 || r >= rows || c < 0 || c >= cols
  const { i } = cellOf(b, p)
  const raw = b.lie[i] as Lie
  const lie: Lie = outside || raw === 0 ? 7 : raw
  return { i, lie, outside: outside || raw === 0 }
}

/**
 * Drop cell for a water landing: the nearest fairway or rough cell at or below the
 * water cell's row (the tee side), as geometry.compute_drop_index.
 */
export function waterDropCell(b: HoleBundle, waterIndex: number): number {
  const { rows, cols } = b.meta
  const wr = Math.floor(waterIndex / cols)
  const wc = waterIndex % cols
  let best = -1
  let bestD = Infinity
  for (let r = 0; r <= Math.min(wr, rows - 1); r++)
    for (let c = 0; c < cols; c++) {
      const lie = b.lie[r * cols + c]
      if (lie !== 2 && lie !== 3) continue
      const d = (r - wr) ** 2 + (c - wc) ** 2
      if (d < bestD) {
        bestD = d
        best = r * cols + c
      }
    }
  if (best < 0) throw new Error(`water cell ${waterIndex} has no tee-side fairway or rough cell`)
  return best
}

/** Drop cell for an OB landing: the nearest tee, fairway, rough, bunker or green cell, as mdp.ob_drop_lookup. */
export function obDropCell(b: HoleBundle, index: number): number {
  const { rows, cols } = b.meta
  const ir = Math.floor(index / cols)
  const ic = index % cols
  let best = -1
  let bestD = Infinity
  for (let r = 0; r < rows; r++)
    for (let c = 0; c < cols; c++) {
      const lie = b.lie[r * cols + c]
      if (lie < 1 || lie > 5) continue
      const d = (r - ir) ** 2 + (c - ic) ** 2
      if (d < bestD) {
        bestD = d
        best = r * cols + c
      }
    }
  if (best < 0) throw new Error('grid has no playable cell')
  return best
}

export function sampleShot(
  b: HoleBundle,
  player: Player,
  from: XY,
  fromLie: Lie,
  club: string,
  dir_deg: number,
  mode: Mode,
  rng: () => number,
): Landing {
  const params = player.clubs[club]
  if (!params) throw new Error(`player has no club ${club}`)
  const mult = player.lie[FROM_LIE_NAME[fromLie] ?? 'fairway']
  const thetaZ = normal(rng)
  const u = rng()
  const xZ = normal(rng)
  const rollZ = normal(rng)
  const xmix = u < params.p ? xZ + MISHIT_MEAN : xZ
  const theta = params.sigma_theta_deg * mult.sigma * thetaZ
  const carry = params.mu_c * mult.carry * (1 + params.sigma_d * mult.sigma * xmix)
  const bearing = pinBearingDeg(b, from)
  const a = ((bearing + dir_deg + theta) * Math.PI) / 180
  const land = { x: from.x + carry * Math.sin(a), y: from.y + carry * Math.cos(a) }
  const landLie = locate(b, land).lie
  const roll = (params.mu_r + params.sigma_r * rollZ) * mult.roll * rollMultiplier(player, landLie)
  const ua = ((bearing + dir_deg) * Math.PI) / 180
  const to = { x: land.x + roll * Math.sin(ua), y: land.y + roll * Math.cos(ua) }
  const final = locate(b, to)
  const water = final.lie === 6
  const ob = final.lie === 7
  let reward = -1
  let next: XY = to
  if (water || ob) {
    reward = mode === 'mulligan' ? -1 : -2
    if (mode === 'drop') {
      const target = water ? waterDropCell(b, final.i) : obDropCell(b, final.i)
      next = centreOf(b, Math.floor(target / b.meta.cols), target % b.meta.cols)
    } else {
      next = { x: from.x, y: from.y }
    }
  }
  return { x: to.x, y: to.y, lie: final.lie, reward, next }
}

/** Expected putts from `d_m` on the player's putting table: linear inside, clamped below, extrapolated beyond. */
export function expectedPutts(player: Player, d_m: number): number {
  const xs = player.putting.distance_m
  const ys = player.putting.expected_putts
  const n = xs.length
  if (n === 0) throw new Error('player.putting is empty')
  if (n === 1 || d_m <= xs[0]) return ys[0]
  if (d_m >= xs[n - 1]) {
    const slope = (ys[n - 1] - ys[n - 2]) / (xs[n - 1] - xs[n - 2])
    return ys[n - 1] + slope * (d_m - xs[n - 1])
  }
  let k = 0
  while (xs[k + 1] < d_m) k++
  const t = (d_m - xs[k]) / (xs[k + 1] - xs[k])
  return ys[k] + t * (ys[k + 1] - ys[k])
}
