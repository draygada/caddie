/**
 * The shot log (part 15): what the player hit, from where to where, and how one logged shot
 * becomes an observation for `updateClubStats`. Pure, no React.
 */
import { lieAt } from './grid'
import type { Observation } from './learn'
import { rollMultiplier } from './shot'
import type { HoleBundle, Lie, Player, XY } from './types'

export type Outcome = 'normal' | 'penalty' | 'green'

/**
 * One shot. Positions are grid meters; accuracies are the GPS accuracy in meters, 0 when the
 * player placed the point by hand. `aimDeg` is a grid bearing (0 along +y, positive to the
 * right), not an offset from the pin line, so a shot stands on its own.
 */
export interface LoggedShot {
  start: XY
  end: XY | null
  startAcc: number
  endAcc: number | null
  /** The lie the shot was played from. */
  lie: Lie
  club: string
  aimDeg: number
  t: number
  outcome: Outcome
  /** The recommended aim when Hit was pressed; `aimDeg` starts equal to it. */
  recAimDeg?: number
  /** The lie where the ball stopped, stored so a shot can be learned from on another hole. */
  endLie?: Lie
}

export type SkipReason = 'open' | 'penalty' | 'green' | 'club' | 'accuracy' | 'aim' | 'short'

/** A fix worse than this at either end is logged but not learned from. */
export const MAX_LEARN_ACCURACY_M = 10
/** An aim moved further than this from the recommendation is not trusted. */
export const MAX_AIM_CHANGE_DEG = 30

export const SKIP_TEXT: Record<SkipReason, string> = {
  open: 'not finished',
  penalty: 'penalty',
  green: 'putt',
  club: 'unknown club',
  accuracy: 'poor GPS',
  aim: 'aim changed',
  short: 'too short',
}

function angleBetweenDeg(a: number, b: number): number {
  const d = (((a - b) % 360) + 540) % 360 - 180
  return Math.abs(d)
}

interface Parts {
  total: number
  carry: number
  lateral: number
}

function parts(b: HoleBundle, player: Player, s: LoggedShot): Parts | null {
  const club = player.clubs[s.club]
  if (!s.end || !club) return null
  const a = (s.aimDeg * Math.PI) / 180
  const dx = s.end.x - s.start.x
  const dy = s.end.y - s.start.y
  const along = dx * Math.sin(a) + dy * Math.cos(a)
  const across = dx * Math.cos(a) - dy * Math.sin(a) // positive is right of the aim line
  const total = Math.hypot(dx, dy)
  const carry = total - club.mu_r * rollMultiplier(player, s.endLie ?? lieAt(b, s.end))
  if (along <= 0 || carry <= 0) return null
  // tan(theta_obs) = across / along, so atan2(lateral, carry) in updateClubStats recovers theta_obs.
  return { total, carry, lateral: (carry * across) / along }
}

/** Why a logged shot is not learned from, or null when it is. */
export function skipReason(b: HoleBundle, player: Player, s: LoggedShot): SkipReason | null {
  if (!s.end || s.endAcc === null) return 'open'
  if (s.outcome === 'penalty') return 'penalty'
  if (s.lie === 5) return 'green'
  if (!player.clubs[s.club]) return 'club'
  if (s.startAcc > MAX_LEARN_ACCURACY_M || s.endAcc > MAX_LEARN_ACCURACY_M) return 'accuracy'
  if (s.recAimDeg !== undefined && angleBetweenDeg(s.aimDeg, s.recAimDeg) > MAX_AIM_CHANGE_DEG) return 'aim'
  if (!parts(b, player, s)) return 'short'
  return null
}

/**
 * The observation a logged shot gives: carry estimated as total less the club's mean roll on
 * the lie where the ball stopped. Null when the shot is skipped; `skipReason` says why.
 */
export function toObservation(b: HoleBundle, player: Player, s: LoggedShot): Observation | null {
  if (skipReason(b, player, s)) return null
  const p = parts(b, player, s)
  return p ? { club: s.club, ...p } : null
}
