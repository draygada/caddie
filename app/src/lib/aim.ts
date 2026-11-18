/**
 * The player's own aim (part 22): a target they move on the map, the club that reaches it,
 * and the two distances a golfer reads off a course app. Pure, no React.
 */
import { TEE_ONLY_CLUBS } from './rollout'
import { pinBearingDeg } from './shot'
import type { HoleBundle, Lie, LieName, Player, XY } from './types'

/** The aim returns to the caddie's once the ball has moved this far from where it was set. */
export const TARGET_RESET_M = 15

const LIE_NAMES: Partial<Record<Lie, LieName>> = { 1: 'tee', 2: 'fairway', 3: 'rough', 4: 'bunker', 5: 'fairway', 8: 'rough' }

/** Clubs the player may hit from `lie`: tee-only clubs only on the tee (part 17). */
export function allowedClubs(player: Player, lie: Lie): string[] {
  const bag = player.club_order.filter((id) => lie === 1 || !TEE_ONLY_CLUBS.includes(id))
  return bag.length > 0 ? bag : player.club_order
}

/** Where a club finishes on average from `lie`: mean carry plus mean roll, with that lie's multipliers. */
export function meanTotalM(player: Player, club: string, lie: Lie): number {
  const c = player.clubs[club]
  if (!c) throw new Error(`player has no club ${club}`)
  const mult = player.lie[LIE_NAMES[lie] ?? 'fairway']
  return c.mu_c * mult.carry + c.mu_r * mult.roll
}

/** The allowed club whose mean total from `lie` is closest to `distM`. */
export function clubForDistance(player: Player, lie: Lie, distM: number): string {
  let best = ''
  let gap = Infinity
  for (const id of allowedClubs(player, lie)) {
    const g = Math.abs(meanTotalM(player, id, lie) - distM)
    if (g < gap) {
      gap = g
      best = id
    }
  }
  return best
}

export interface Aim {
  club: string
  /** Offset from the pin line in degrees, positive to the right, as the solver's actions. */
  dir_deg: number
  target: XY
  toTargetM: number
  /** From the target to the pin. */
  toPinM: number
  /** False while this is exactly the caddie's club and aim. */
  custom: boolean
}

/**
 * The aim in force. With `target` null it is the caddie's direction, and the target sits at
 * the club's mean total along it. A moved target sets the direction, and the club is the
 * one for that distance unless the player chose one (`aimClub`) they may hit from here.
 */
export function resolveAim(
  b: HoleBundle,
  player: Player,
  ball: XY,
  lie: Lie,
  rec: { club: string; dir_deg: number },
  target: XY | null,
  aimClub: string | null,
): Aim {
  const [px, py] = b.meta.pin_xy
  const chosen = aimClub !== null && allowedClubs(player, lie).includes(aimClub) ? aimClub : null
  if (target === null) {
    const club = chosen ?? rec.club
    const toTargetM = meanTotalM(player, club, lie)
    const a = ((pinBearingDeg(b, ball) + rec.dir_deg) * Math.PI) / 180
    const at = { x: ball.x + toTargetM * Math.sin(a), y: ball.y + toTargetM * Math.cos(a) }
    return { club, dir_deg: rec.dir_deg, target: at, toTargetM, toPinM: Math.hypot(px - at.x, py - at.y), custom: club !== rec.club }
  }
  const toTargetM = Math.hypot(target.x - ball.x, target.y - ball.y)
  const bearing = (Math.atan2(target.x - ball.x, target.y - ball.y) * 180) / Math.PI
  const dir_deg = ((bearing - pinBearingDeg(b, ball) + 540) % 360) - 180
  return {
    club: chosen ?? clubForDistance(player, lie, toTargetM),
    dir_deg,
    target: { x: target.x, y: target.y },
    toTargetM,
    toPinM: Math.hypot(px - target.x, py - target.y),
    custom: true,
  }
}
