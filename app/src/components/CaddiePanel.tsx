/**
 * The caddie panel: a bottom sheet on a phone (collapsed shows the detected lie and the
 * three numbers; expanded adds the aim description) and a 360 px column
 * docked right on wider screens. Reads the store only. The Play it out button lives in
 * PlayItOut (part 13 slices 5 and 6) and mounts in the expanded area.
 */
import { type ReactNode, useState } from 'react'

import { lieAt, valueNearest } from '../lib/grid'
import { clubDisplayName, MODE_LABEL } from '../lib/tokens'
import type { Lie, LieName, Meta, Player, XY } from '../lib/types'
import { currentAim, currentOutcome, useStore } from '../store'
import { AimChips, AimDetails, CaddiePick } from './AimPanel'
import { LearnBadge } from './LearnBadge'
import { PlayItOut } from './PlayItOut'
import { ExportLogButton, ShotLogger } from './ShotLogger'

export const M_PER_YD = 0.9144

export function toYards(m: number): number {
  return m / M_PER_YD
}

export function distanceToPinM(meta: Meta, ball: XY): number {
  return Math.hypot(meta.pin_xy[0] - ball.x, meta.pin_xy[1] - ball.y)
}

const LIE_NAMES: Partial<Record<Lie, LieName>> = { 1: 'tee', 2: 'fairway', 3: 'rough', 4: 'bunker', 5: 'fairway' }

/** Lateral offset of the aim point from the pin line at the club's carry, in yards. Negative is left. */
export function aimOffsetYd(player: Player, club: string, lie: Lie, dir_deg: number): number {
  const params = player.clubs[club]
  if (!params) return 0
  const mult = player.lie[LIE_NAMES[lie] ?? 'fairway']
  const carry = params.mu_c * mult.carry
  return toYards(carry * Math.tan((dir_deg * Math.PI) / 180))
}

/** "Aim 8 yards left of the pin", "Aim 1 yard right of the pin", or "Aim at the pin". */
export function aimText(offsetYd: number): string {
  const n = Math.round(Math.abs(offsetYd))
  if (n === 0) return 'Aim at the pin'
  const side = offsetYd < 0 ? 'left' : 'right'
  return `Aim ${n} ${n === 1 ? 'yard' : 'yards'} ${side} of the pin`
}

const LIE_WORDS: Record<Lie, string> = {
  0: 'off the hole',
  1: 'on the tee',
  2: 'in the fairway',
  3: 'in the rough',
  4: 'in a bunker',
  5: 'on the green',
  6: 'in the water',
  7: 'out of bounds',
  8: 'in the trees',
}

/** The detected lie as one read-only line. Since part 21 the lie is never chosen by hand. */
export function lieLine(lie: Lie): string {
  return `Ball is ${LIE_WORDS[lie]}`
}

function Figure({ label, value, unit, accent }: { label: string; value: string; unit?: string; accent?: boolean }) {
  return (
    <div className="flex min-w-0 flex-col gap-1">
      <span className="label">{label}</span>
      <span
        className={`num text-big leading-none ${accent ? 'text-rec' : 'text-ink'}`}
        style={{ fontSize: 'var(--text-big)', fontWeight: 600 }}
      >
        {value}
        {unit && <span className="ml-1 text-caption font-medium text-ink-2">{unit}</span>}
      </span>
    </div>
  )
}

function Skeleton() {
  return (
    <div className="grid grid-cols-3 gap-4" aria-hidden="true">
      {[0, 1, 2].map((k) => (
        <div key={k} className="flex flex-col gap-2">
          <div className="h-3 w-14 rounded bg-line" />
          <div className="h-8 w-20 rounded bg-line" />
        </div>
      ))}
    </div>
  )
}

export interface CaddiePanelProps {
  /** Part 21: which controls this mode carries (`panelParts` in HoleScreen). All on by default. */
  parts?: { logger: boolean; learn: boolean; playItOut: boolean }
  /** What to say before there is a ball. */
  emptyText?: string
  /** Shown first in the panel: the GPS notice in Play, a hole that failed to load. */
  notice?: ReactNode
  /** The read-only hole line: "Hole 11 · Par 4 · 342 yd · Black tees". */
  info?: string
  /** Last in the expanded panel: Next hole and End round. */
  footer?: ReactNode
}

const ALL_PARTS = { logger: true, learn: true, playItOut: true }

export function CaddiePanel({ parts = ALL_PARTS, emptyText = 'Tap the map to place the ball', notice, info, footer }: CaddiePanelProps) {
  const recommendation = useStore((s) => s.recommendation)
  const aim = useStore(currentAim)
  const outcome = useStore(currentOutcome)
  const ball = useStore((s) => s.ball)
  const bundle = useStore((s) => s.bundle)
  const player = useStore((s) => s.player)
  const mode = useStore((s) => s.mode)
  const lieOverride = useStore((s) => s.lieOverride)
  const [expanded, setExpanded] = useState(false)

  const toPinYd = bundle && ball ? toYards(distanceToPinM(bundle.meta, ball)) : null
  const lie: Lie | null = bundle && ball ? (lieOverride ?? lieAt(bundle, ball)) : null
  const onGreen = lie === 5
  const inHazard = lie === 6 || lie === 7
  const putts = bundle && ball && onGreen ? valueNearest(bundle, ball) : null
  const offsetYd =
    aim && player && lie !== null ? aimOffsetYd(player, aim.club, lie, aim.dir_deg) : null

  let body
  if (!bundle) {
    body = <Skeleton />
  } else if (!ball) {
    body = <p className="text-body text-ink-2">{emptyText}</p>
  } else if (onGreen && putts !== null) {
    body = (
      <div className="grid grid-cols-3 gap-4">
        <Figure label="To pin" value={String(Math.round(toPinYd ?? 0))} unit="yd" />
        <Figure label="On the green" value="Putt" />
        <Figure label="Expected" value={putts.toFixed(1)} unit="putts" accent />
      </div>
    )
  } else if (inHazard) {
    body = (
      <div className="flex flex-col gap-1">
        <span className="label">{lie === 6 ? 'In the water' : 'Out of bounds'}</span>
        <p className="text-body text-ink-2">
          {MODE_LABEL[mode]} rule: {lie === 6 && mode === 'drop' ? 'drop at the nearest fairway on the entry side, one stroke' : mode === 'mulligan' ? 'hit again from the same spot, no penalty' : 'hit again from the same spot, one stroke'}
        </p>
      </div>
    )
  } else if (recommendation) {
    // Part 22: the club and the expected strokes are those of the aim in force. The pill is
    // the recommendation colour only while that aim is the caddie's own.
    const own = aim?.custom ?? false
    const club = aim?.club ?? recommendation.club
    const expected = own && outcome ? outcome.expected : recommendation.expected_strokes
    body = (
      <div className="grid grid-cols-3 gap-4">
        <Figure label="To pin" value={String(Math.round(toPinYd ?? 0))} unit="yd" />
        <div className="flex min-w-0 flex-col gap-1">
          <span className="label">{own ? 'Your club' : 'Club'}</span>
          <span
            className={`inline-flex w-fit max-w-full items-center rounded-lg px-3 py-1.5 leading-tight ${own ? 'bg-ink text-surface' : 'bg-rec text-rec-ink'}`}
            style={{ fontSize: 'var(--text-body)', fontWeight: 600 }}
            data-testid="club"
          >
            {clubDisplayName(club)}
          </span>
        </div>
        <div className="flex min-w-0 flex-col gap-1">
          <Figure label="Expected" value={expected.toFixed(1)} accent={!own} />
          {!own && recommendation.baseline_pin_strokes !== undefined && (
            <span className="num text-caption text-ink-2" data-testid="baseline">
              Pin with {clubDisplayName(recommendation.club)}: {recommendation.baseline_pin_strokes.toFixed(1)}
            </span>
          )}
        </div>
      </div>
    )
  } else {
    body = <p className="text-body text-ink-2">No shot from here: off the hole.</p>
  }


  return (
    <section
      aria-label="Caddie"
      className="pointer-events-auto flex w-full flex-col gap-3 rounded-t-2xl border-t border-line bg-surface px-4 pt-3 shadow-[0_-4px_20px_rgba(0,0,0,0.12)] safe-bottom md:h-full md:w-[360px] md:rounded-none md:border-t-0 md:border-l md:shadow-none"
    >
      <button
        type="button"
        className="-mt-3 -mb-2 flex h-12 w-full items-center justify-center md:hidden"
        aria-expanded={expanded}
        aria-controls="caddie-details"
        onClick={() => setExpanded((e) => !e)}
      >
        <span className="h-1.5 w-10 rounded-full bg-line" aria-hidden="true" />
        <span className="sr-only">{expanded ? 'Show less' : 'Show more'}</span>
      </button>

      {notice}
      {(info || lie !== null) && (
        <div className="flex flex-col gap-0.5">
          {info && (
            <p className="num text-caption font-medium text-ink" data-testid="hole-line">
              {info}
            </p>
          )}
          {lie !== null && (
            <p className="num text-caption text-ink-2" data-testid="lie">
              {lieLine(lie)}
            </p>
          )}
        </div>
      )}
      {body}
      <AimChips />
      <CaddiePick />
      {parts.logger && <ShotLogger />}

      <div id="caddie-details" className={`${expanded ? 'flex' : 'hidden'} flex-col gap-3 pb-2 md:flex`}>
        <AimDetails />
        {aim && offsetYd !== null && (
          <p className="num text-body text-ink" data-testid="aim">
            {aimText(offsetYd)}
          </p>
        )}
        {parts.playItOut && <PlayItOut />}
        {parts.learn && <LearnBadge />}
        {parts.learn && <ExportLogButton />}
        {footer}
      </div>
    </section>
  )
}
