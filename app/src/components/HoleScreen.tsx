/**
 * The hole screen in one of its two modes (part 21). Simulate is the desk: put the ball
 * anywhere, play it out. Play is the course: GPS on, shots logged. There is no top bar: the
 * hole and the tees are chosen on the setup step and shown read-only in the bottom panel, so
 * neither can change in the middle of a hole. `panelParts` is the single place that says
 * which controls each mode carries.
 */
import { useState } from 'react'

import { useGps } from '../hooks/useGps'
import type { Meta } from '../lib/types'
import { type HoleId, type Screen, useStore } from '../store'
import { CaddiePanel, distanceToPinM, toYards } from './CaddiePanel'
import { GpsNotice, GpsStatusText } from './GpsBadge'
import { HoleMap } from './HoleMap'
import { teeLabel } from './Home'

export type HoleMode = Exclude<Screen, 'home'>

export interface PanelParts {
  /** Hit, finish and undo buttons, and the logged shots on the map. */
  logger: boolean
  /** "Use my course shots" and the export button. */
  learn: boolean
  playItOut: boolean
  /** The GPS watch, the accuracy circle and the status line. */
  gps: boolean
}

export function panelParts(screen: HoleMode): PanelParts {
  return screen === 'play'
    ? { logger: true, learn: true, playItOut: false, gps: true }
    : { logger: false, learn: false, playItOut: true, gps: false }
}

/** What the panel says before there is a ball. */
export const EMPTY_BALL_TEXT: Record<HoleMode, string> = {
  simulate: 'Tap the map to place the ball',
  play: 'Finding you. Tap the map to place the ball yourself.',
}

/** "Hole 11 · Par 4 · 342 yd · Black tees": what the top bar used to carry, read-only. */
export function holeLine(meta: Meta, tee: string): string {
  const xy = meta.tees[tee] ?? meta.tee_xy
  const yd = Math.round(toYards(distanceToPinM(meta, { x: xy[0], y: xy[1] })))
  return `Hole ${meta.hole} · Par ${meta.par} · ${yd} yd · ${teeLabel(tee)} tees`
}

/** The hole after this one in the round, or null on the last (or on a hole outside the round). */
export function nextHole(hole: HoleId): HoleId | null {
  return hole === 10 ? 11 : hole === 11 ? 12 : null
}

const PLAIN_BUTTON = 'flex h-12 flex-1 items-center justify-center rounded-lg border border-line bg-surface-2 px-3 text-body text-ink'

export interface HoleScreenProps {
  screen: HoleMode
  error: string | null
}

export function HoleScreen({ screen, error }: HoleScreenProps) {
  const hole = useStore((s) => s.hole)
  const tee = useStore((s) => s.tee)
  const bundle = useStore((s) => s.bundle)
  const setHole = useStore((s) => s.setHole)
  const setScreen = useStore((s) => s.setScreen)
  const parts = panelParts(screen)
  // GPS is on for as long as the Play screen is; leaving it stops the watch.
  const [attempt, setAttempt] = useState(0)
  useGps(parts.gps, attempt)
  const next = nextHole(hole)

  const notice = (
    <>
      {error && (
        <p className="text-body text-bad" role="alert">
          Hole {hole} is not ready yet.
        </p>
      )}
      {parts.gps && <GpsNotice onRetry={() => setAttempt((n) => n + 1)} />}
    </>
  )
  const footer = (
    <div className="flex gap-2">
      {next !== null && (
        <button type="button" className={PLAIN_BUTTON} onClick={() => setHole(next)}>
          Next hole
        </button>
      )}
      <button type="button" className={PLAIN_BUTTON} onClick={() => setScreen('home')}>
        End round
      </button>
    </div>
  )
  const panel = (
    <CaddiePanel
      parts={parts}
      emptyText={EMPTY_BALL_TEXT[screen]}
      info={bundle ? holeLine(bundle.meta, tee) : `Hole ${hole}`}
      notice={notice}
      footer={footer}
    />
  )

  return (
    <div className="flex h-full flex-col bg-surface text-ink">
      <main className="relative min-h-0 flex-1 md:flex">
        <div className="relative h-full min-w-0 flex-1">
          <HoleMap bundle={bundle} tee={tee} parts={parts} />
          <div className="pointer-events-none absolute inset-x-0 bottom-0 z-20 md:hidden">{panel}</div>
        </div>
        <div className="hidden h-full md:block">{panel}</div>
      </main>
      {parts.gps && (
        <div className="num flex h-6 items-center gap-3 border-t border-line bg-surface px-4 text-caption text-ink-2" role="status">
          <GpsStatusText />
        </div>
      )}
    </div>
  )
}
