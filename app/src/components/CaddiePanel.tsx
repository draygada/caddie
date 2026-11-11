/**
 * The caddie panel: a bottom sheet on a phone (collapsed shows the three numbers and the
 * lie row; expanded adds the aim description and the heatmap legend) and a 360 px column
 * docked right on wider screens. Reads the store only. The Play it out button lives in
 * PlayItOut (part 13 slices 5 and 6) and mounts in the expanded area.
 */
import { useState } from 'react'

import { lieAt, valueNearest } from '../lib/grid'
import { rampGradientCss } from '../lib/heatmap'
import { clubDisplayName, MODE_LABEL } from '../lib/tokens'
import type { Lie, LieName, Meta, Player, XY } from '../lib/types'
import { useStore } from '../store'
import { LieButtons } from './LieButtons'
import { PlayItOut } from './PlayItOut'

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

export function CaddiePanel() {
  const recommendation = useStore((s) => s.recommendation)
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
    recommendation && player && lie !== null ? aimOffsetYd(player, recommendation.club, lie, recommendation.dir_deg) : null

  let body
  if (!bundle) {
    body = <Skeleton />
  } else if (!ball) {
    body = <p className="text-body text-ink-2">Tap the map or turn on GPS</p>
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
    body = (
      <div className="grid grid-cols-3 gap-4">
        <Figure label="To pin" value={String(Math.round(toPinYd ?? 0))} unit="yd" />
        <div className="flex min-w-0 flex-col gap-1">
          <span className="label">Club</span>
          <span
            className="inline-flex w-fit max-w-full items-center rounded-lg bg-rec px-3 py-1.5 leading-tight text-rec-ink"
            style={{ fontSize: 'var(--text-body)', fontWeight: 600 }}
            data-testid="club"
          >
            {clubDisplayName(recommendation.club)}
          </span>
        </div>
        <div className="flex min-w-0 flex-col gap-1">
          <Figure label="Expected" value={recommendation.expected_strokes.toFixed(1)} accent />
          {recommendation.baseline_pin_strokes !== undefined && (
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

  const par = bundle?.meta.par ?? 4

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

      <LieButtons />
      {body}

      <div id="caddie-details" className={`${expanded ? 'flex' : 'hidden'} flex-col gap-3 pb-2 md:flex`}>
        {recommendation && offsetYd !== null && (
          <p className="num text-body text-ink" data-testid="aim">
            {aimText(offsetYd)}
          </p>
        )}
        <div className="flex flex-col gap-1">
          <span className="label">Strokes to go</span>
          <div className="h-3 w-full rounded" style={{ background: rampGradientCss() }} aria-hidden="true" />
          <div className="num flex justify-between text-caption text-ink-2">
            <span>{par - 1}</span>
            <span>par {par}</span>
            <span>{par + 3}</span>
          </div>
        </div>
        <PlayItOut />
      </div>
    </section>
  )
}
