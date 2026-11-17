/**
 * The aim block of the caddie panel (part 22): the club chips, the two distances, where 200
 * shots with this club and aim finish, and the caddie's own pick to compare against.
 */
import { allowedClubs } from '../lib/aim'
import { lieAt } from '../lib/grid'
import type { FinishKind } from '../lib/rollout'
import { clubDisplayName } from '../lib/tokens'
import { currentAim, currentOutcome, useStore } from '../store'
import { toYards } from './CaddiePanel'

export function aimLineText(aim: { toTargetM: number; toPinM: number }): string {
  return `${Math.round(toYards(aim.toTargetM))} yd to your target, then ${Math.round(toYards(aim.toPinM))} yd to the pin`
}

const KIND_LABEL: Record<FinishKind, string> = { fairway: 'Fairway', rough: 'Rough', bunker: 'Bunker', green: 'Green', penalty: 'Penalty' }

/** "Fairway 62% · Rough 25% · Penalty 8%": largest first, anything under half a percent left out. */
export function shareText(share: Record<FinishKind, number>): string {
  return (Object.keys(share) as FinishKind[])
    .filter((k) => share[k] >= 0.005)
    .sort((a, b) => share[b] - share[a])
    .map((k) => `${KIND_LABEL[k]} ${Math.round(share[k] * 100)}%`)
    .join(' · ')
}

/** Short chip text: the club id as stamped on the stick ("7i", "PW", "SW 50"). */
export function chipText(id: string): string {
  const m = /^(sw|pw|lw|gw)(\d+)$/.exec(id)
  if (m) return `${m[1].toUpperCase()} ${m[2]}`
  if (id === 'driver') return 'Driver'
  return /^(sw|pw|lw|gw)$/.test(id) ? id.toUpperCase() : id
}

const CHIP = 'num flex h-11 shrink-0 items-center rounded-lg px-3 text-caption font-medium transition-colors'

function useAimState() {
  const bundle = useStore((s) => s.bundle)
  const player = useStore((s) => s.player)
  const ball = useStore((s) => s.ball)
  const lieOverride = useStore((s) => s.lieOverride)
  const recommendation = useStore((s) => s.recommendation)
  const aim = useStore(currentAim)
  if (!bundle || !player || !ball || !aim || !recommendation) return null
  return { player, lie: lieOverride ?? lieAt(bundle, ball), recommendation, aim }
}

/** The club chips: always visible, one tap to try another club. The dot marks the caddie's pick. */
export function AimChips() {
  const st = useAimState()
  const setAimClub = useStore((s) => s.setAimClub)
  if (!st) return null
  const { player, lie, recommendation, aim } = st
  return (
    <div className="-mx-4 flex gap-2 overflow-x-auto px-4" role="radiogroup" aria-label="Club" data-testid="aim-chips">
      {allowedClubs(player, lie).map((id) => (
        <button
          key={id}
          type="button"
          role="radio"
          aria-checked={id === aim.club}
          aria-label={clubDisplayName(id) + (id === recommendation.club ? " (the caddie's pick)" : '')}
          className={`${CHIP} ${id === aim.club ? 'bg-ink text-surface' : 'border border-line bg-surface-2 text-ink'}`}
          onClick={() => setAimClub(id)}
        >
          {chipText(id)}
          {id === recommendation.club && <span className="ml-1 h-1.5 w-1.5 rounded-full bg-rec" aria-hidden="true" />}
        </button>
      ))}
    </div>
  )
}

/** Back to the caddie's club and aim; shown only while the aim is the player's own. */
export function CaddiePick() {
  const st = useAimState()
  const resetAim = useStore((s) => s.resetAim)
  if (!st || !st.aim.custom) return null
  const { recommendation } = st
  return (
    <div className="flex items-center justify-between gap-3" data-testid="caddie-pick">
      <span className="num min-w-0 text-caption text-ink-2">
        The caddie's pick: {clubDisplayName(recommendation.club)}, {recommendation.expected_strokes.toFixed(1)} expected
      </span>
      <button
        type="button"
        className="h-12 shrink-0 rounded-lg border border-line bg-surface-2 px-3 text-caption font-medium text-ink"
        onClick={resetAim}
      >
        Use it
      </button>
    </div>
  )
}

/** The two distances in words and where the 200 shots finish; lives in the expanded panel. */
export function AimDetails() {
  const st = useAimState()
  const outcome = useStore(currentOutcome)
  if (!st) return null
  return (
    <div className="flex flex-col gap-1" data-testid="aim-panel">
      <p className="num text-body text-ink" data-testid="aim-line">
        {aimLineText(st.aim)}
      </p>
      {outcome && (
        <p className="num text-caption text-ink-2" data-testid="aim-share">
          Where 200 shots finish: {shareText(outcome.share)}
        </p>
      )}
    </div>
  )
}
