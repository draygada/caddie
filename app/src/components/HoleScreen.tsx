/**
 * The hole screen in one of its two modes (part 21). Simulate is the desk: pick a hole, put
 * the ball anywhere, play it out. Play is the course: GPS on, shots logged. `panelParts`
 * is the single place that says which controls each mode carries.
 */
import { useState } from 'react'

import { useGps } from '../hooks/useGps'
import { MODE_HELP, MODE_LABEL } from '../lib/tokens'
import type { Mode } from '../lib/types'
import { type HoleId, type Screen, useStore } from '../store'
import { CaddiePanel, distanceToPinM, toYards } from './CaddiePanel'
import { GpsNotice, GpsStatusText } from './GpsBadge'
import { HoleMap } from './HoleMap'

export const HOLES: HoleId[] = [10, 11, 12, 'toy']
export const MODES: Mode[] = ['mulligan', 'drop', 'replay']

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

const SCREEN_NAME: Record<HoleMode, string> = { simulate: 'Simulate', play: 'Play' }

function parseHole(v: string): HoleId {
  return v === 'toy' ? 'toy' : (Number(v) as 10 | 11 | 12)
}

interface PickerProps<T extends string | number> {
  label: string
  value: T
  options: readonly T[]
  onChange: (v: string) => void
  render?: (v: T) => string
}

function Picker<T extends string | number>({ label, value, options, onChange, render }: PickerProps<T>) {
  return (
    <label className="flex h-12 items-center gap-2">
      <span className="label">{label}</span>
      <select
        className="num h-12 rounded-lg border border-line bg-surface-2 px-3 text-body text-ink"
        value={String(value)}
        onChange={(e) => onChange(e.target.value)}
      >
        {options.map((o) => (
          <option key={String(o)} value={String(o)}>
            {render ? render(o) : String(o)}
          </option>
        ))}
      </select>
    </label>
  )
}

function ModeControl({ value, onChange }: { value: Mode; onChange: (m: Mode) => void }) {
  return (
    <div className="flex overflow-hidden rounded-lg border border-line bg-surface-2" role="radiogroup" aria-label="Penalty mode">
      {MODES.map((m) => (
        <button
          key={m}
          type="button"
          role="radio"
          aria-checked={value === m}
          title={MODE_HELP[m]}
          className={`h-12 min-w-[72px] px-3 text-body font-medium transition-colors ${
            value === m ? 'bg-ink text-surface' : 'text-ink-2 hover:text-ink'
          }`}
          onClick={() => onChange(m)}
        >
          {MODE_LABEL[m]}
        </button>
      ))}
    </div>
  )
}

function ThemeToggle({ theme, onToggle }: { theme: 'light' | 'dark'; onToggle: () => void }) {
  return (
    <button
      type="button"
      className="h-12 rounded-lg border border-line bg-surface-2 px-3 text-caption font-medium text-ink-2"
      aria-pressed={theme === 'dark'}
      onClick={onToggle}
    >
      {theme === 'dark' ? 'Light' : 'Dark'}
    </button>
  )
}

export interface HoleScreenProps {
  screen: HoleMode
  theme: 'light' | 'dark'
  onToggleTheme: () => void
  error: string | null
}

export function HoleScreen({ screen, theme, onToggleTheme, error }: HoleScreenProps) {
  const hole = useStore((s) => s.hole)
  const mode = useStore((s) => s.mode)
  const tee = useStore((s) => s.tee)
  const bundle = useStore((s) => s.bundle)
  const setHole = useStore((s) => s.setHole)
  const setMode = useStore((s) => s.setMode)
  const setTee = useStore((s) => s.setTee)
  const setScreen = useStore((s) => s.setScreen)
  const [moreOpen, setMoreOpen] = useState(false)
  const parts = panelParts(screen)
  // GPS is on for as long as the Play screen is; leaving it stops the watch.
  const [attempt, setAttempt] = useState(0)
  useGps(parts.gps, attempt)
  const notice = parts.gps ? <GpsNotice onRetry={() => setAttempt((n) => n + 1)} /> : null

  const tees = bundle ? Object.keys(bundle.meta.tees) : [tee]
  const teeXY = bundle?.meta.tees[tee] ?? bundle?.meta.tee_xy
  const yardage = bundle && teeXY ? Math.round(toYards(distanceToPinM(bundle.meta, { x: teeXY[0], y: teeXY[1] }))) : null

  return (
    <div className="flex h-full flex-col bg-surface text-ink">
      <main className="relative min-h-0 flex-1 md:flex">
        <div className="relative h-full min-w-0 flex-1">
          <HoleMap bundle={bundle} tee={tee} parts={parts} />
      <header className="safe-top pointer-events-none absolute inset-x-0 top-0 z-10 px-2 pt-2">
        <div className="pointer-events-auto flex h-14 items-center gap-3 rounded-xl bg-surface/95 px-3 shadow-[0_1px_2px_rgba(0,0,0,0.2),0_4px_12px_rgba(0,0,0,0.12)]">
          <button
            type="button"
            aria-label="Home"
            title="Home"
            className="-ml-1 flex h-12 w-12 shrink-0 items-center justify-center rounded-lg text-ink-2 hover:text-ink"
            onClick={() => setScreen('home')}
          >
            <svg viewBox="0 0 24 24" width="22" height="22" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round" aria-hidden="true">
              <path d="M15 6l-6 6 6 6" />
            </svg>
          </button>
          <h1 className="hidden text-body font-semibold sm:block">{SCREEN_NAME[screen]}</h1>
          <Picker label="Hole" value={hole} options={HOLES} onChange={(v) => setHole(parseHole(v))} />
          {bundle && (
            <span className="num text-caption text-ink-2">
              Par {bundle.meta.par}
              {yardage !== null && <> · {yardage} yd</>}
            </span>
          )}
          <div className="ml-auto hidden items-center gap-3 md:flex">
            <Picker label="Tee" value={tee} options={tees} onChange={setTee} render={(t) => t.charAt(0).toUpperCase() + t.slice(1)} />
            <ModeControl value={mode} onChange={setMode} />
            <ThemeToggle theme={theme} onToggle={onToggleTheme} />
          </div>
          <button
            type="button"
            className="num ml-auto h-12 rounded-lg border border-line bg-surface-2 px-3 text-caption font-medium text-ink-2 md:hidden"
            aria-expanded={moreOpen}
            aria-controls="top-bar-more"
            onClick={() => setMoreOpen((o) => !o)}
          >
            {tee.charAt(0).toUpperCase() + tee.slice(1)} · {MODE_LABEL[mode]}
          </button>
        </div>
        <div
          id="top-bar-more"
          className={`${moreOpen ? 'flex' : 'hidden'} pointer-events-auto mt-2 flex-wrap items-center gap-3 rounded-xl bg-surface/95 p-3 shadow-[0_1px_2px_rgba(0,0,0,0.2),0_4px_12px_rgba(0,0,0,0.12)] md:hidden`}
        >
          <Picker label="Tee" value={tee} options={tees} onChange={setTee} render={(t) => t.charAt(0).toUpperCase() + t.slice(1)} />
          <ModeControl value={mode} onChange={setMode} />
          <ThemeToggle theme={theme} onToggle={onToggleTheme} />
        </div>
      </header>
          <div className="pointer-events-none absolute inset-x-0 bottom-0 z-20 md:hidden">
            <CaddiePanel parts={parts} emptyText={EMPTY_BALL_TEXT[screen]} notice={notice} />
          </div>
        </div>
        <div className="hidden h-full md:block">
          <CaddiePanel parts={parts} emptyText={EMPTY_BALL_TEXT[screen]} notice={notice} />
        </div>
      </main>

      {(parts.gps || error) && (
        <div className="num flex h-6 items-center gap-3 border-t border-line bg-surface px-4 text-caption text-ink-2" role="status">
          {error ? <span className="text-bad">{error}</span> : <GpsStatusText />}
        </div>
      )}
    </div>
  )
}
