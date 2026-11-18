/**
 * The home page (part 21): the first screen, every time. Two cards, one per posture in
 * docs/design.md section 1; picking one opens the setup step, which asks for the starting
 * hole and the tees. They are asked here because the hole screen cannot change them. The
 * Start tap is also the user gesture iOS Safari needs before it hands out a position.
 */
import { useEffect, useState } from 'react'

import type { HoleBundle } from '../lib/types'
import { type HoleId, type Screen, useStore } from '../store'

export const HOME_TAGLINE = 'The club and the aim with the fewest expected strokes, on holes 10 to 12 at Stanford.'

export const MODES_ON_HOME: { screen: Exclude<Screen, 'home'>; where: string; title: string; body: string }[] = [
  {
    screen: 'simulate',
    where: 'At a desk',
    title: 'Simulate a hole',
    body: 'Put the ball anywhere on a hole. See the best club and aim from there, then play the hole out.',
  },
  {
    screen: 'play',
    where: 'On the course',
    title: 'Play with GPS',
    body: 'Follows you as you walk and logs each shot you hit. Asks for your location.',
  },
]

/** The round: the only holes the app offers. */
export const SETUP_HOLES: HoleId[] = [10, 11, 12]

export function teeLabel(tee: string): string {
  return tee.charAt(0).toUpperCase() + tee.slice(1)
}

/** Why Start is disabled, or null when the chosen hole is loaded and ready. */
export function startBlocked(bundle: HoleBundle | null, hole: HoleId, error: string | null): string | null {
  if (error) return `Hole ${hole} is not ready yet`
  // The solver writes `meta.hole` as a string ("11"), so compare as text.
  if (!bundle || String(bundle.meta.hole) !== String(hole)) return `Loading hole ${hole}`
  return null
}

const SEGMENT = 'flex h-14 min-w-0 flex-1 items-center justify-center rounded-lg text-body font-medium transition-colors'
const ON = 'bg-ink text-surface'
const OFF = 'border border-line bg-surface-2 text-ink'

function Choice<T extends string | number>({
  label,
  options,
  value,
  onPick,
  render,
}: {
  label: string
  options: readonly T[]
  value: T
  onPick: (v: T) => void
  render?: (v: T) => string
}) {
  return (
    <div className="flex flex-col gap-2">
      <span className="label" id={`setup-${label}`}>
        {label}
      </span>
      <div className="flex gap-2" role="radiogroup" aria-labelledby={`setup-${label}`}>
        {options.map((o) => (
          <button
            key={String(o)}
            type="button"
            role="radio"
            aria-checked={o === value}
            className={`num ${SEGMENT} ${o === value ? ON : OFF}`}
            onClick={() => onPick(o)}
          >
            {render ? render(o) : String(o)}
          </button>
        ))}
      </div>
    </div>
  )
}

export interface HomeProps {
  theme: 'light' | 'dark'
  onToggleTheme: () => void
  /** The bundle load error for the selected hole, if any. */
  error: string | null
}

export function Home({ theme, onToggleTheme, error }: HomeProps) {
  const setScreen = useStore((s) => s.setScreen)
  const hole = useStore((s) => s.hole)
  const tee = useStore((s) => s.tee)
  const bundle = useStore((s) => s.bundle)
  const setHole = useStore((s) => s.setHole)
  const setTee = useStore((s) => s.setTee)
  const [picked, setPicked] = useState<Exclude<Screen, 'home'> | null>(null)

  // The round is holes 10 to 12: entering setup from anything else starts on 10.
  useEffect(() => {
    if (picked && !SETUP_HOLES.includes(hole)) setHole(SETUP_HOLES[0])
  }, [picked, hole, setHole])

  const mode = MODES_ON_HOME.find((m) => m.screen === picked)
  if (picked && mode) {
    const blocked = startBlocked(bundle, hole, error)
    const tees = !blocked && bundle ? Object.keys(bundle.meta.tees) : []
    return (
      <main className="safe-top safe-bottom flex h-full flex-col bg-surface px-5 text-ink">
        <div className="mx-auto flex h-full w-full max-w-md flex-col">
          <header className="flex flex-1 flex-col justify-center gap-2 py-8">
            <span className="label">{mode.where}</span>
            <h1 style={{ fontSize: 'var(--text-big)', fontWeight: 600, lineHeight: 1.1 }}>{mode.title}</h1>
          </header>
          <div className="flex flex-col gap-5 pb-8">
            <Choice label="Starting hole" options={SETUP_HOLES} value={hole} onPick={setHole} />
            {tees.length > 0 ? (
              <Choice label="Tees" options={tees} value={tee} onPick={setTee} render={teeLabel} />
            ) : (
              <p className={`text-body ${error ? 'text-bad' : 'text-ink-2'}`} role="status">
                {blocked}
              </p>
            )}
            <div className="flex gap-2 pt-2">
              <button type="button" className={`${SEGMENT} ${OFF} max-w-[112px]`} onClick={() => setPicked(null)}>
                Back
              </button>
              <button
                type="button"
                disabled={blocked !== null}
                className={`${SEGMENT} bg-rec font-semibold text-rec-ink disabled:opacity-40`}
                onClick={() => setScreen(picked)}
              >
                Start
              </button>
            </div>
          </div>
        </div>
      </main>
    )
  }

  return (
    <main className="safe-top safe-bottom flex h-full flex-col bg-surface px-5 text-ink">
      <div className="mx-auto flex h-full w-full max-w-md flex-col">
        <div className="flex justify-end pt-3">
          <button
            type="button"
            className="h-12 rounded-lg px-3 text-caption font-medium text-ink-2"
            aria-pressed={theme === 'dark'}
            onClick={onToggleTheme}
          >
            {theme === 'dark' ? 'Light mode' : 'Dark mode'}
          </button>
        </div>
        <header className="flex flex-1 flex-col justify-center gap-3 py-8">
          <h1 className="leading-none" style={{ fontSize: 'var(--text-hero)', fontWeight: 700 }}>
            Caddie
          </h1>
          <p className="max-w-[30ch] text-body text-ink-2">{HOME_TAGLINE}</p>
        </header>
        <nav className="flex flex-col gap-3 pb-8" aria-label="Choose a mode">
          {MODES_ON_HOME.map((m) => (
            <button
              key={m.screen}
              type="button"
              className="group flex min-h-[112px] items-center gap-4 rounded-2xl border border-line bg-surface-2 p-5 text-left shadow-[0_1px_2px_rgba(0,0,0,0.06)] transition-colors hover:border-ink active:bg-surface"
              onClick={() => setPicked(m.screen)}
            >
              <span className="flex min-w-0 flex-1 flex-col gap-1">
                <span className="label">{m.where}</span>
                <span className="text-ink" style={{ fontSize: '22px', fontWeight: 600, lineHeight: 1.2 }}>
                  {m.title}
                </span>
                <span className="text-body text-ink-2">{m.body}</span>
              </span>
              <svg
                viewBox="0 0 24 24"
                width="24"
                height="24"
                fill="none"
                stroke="currentColor"
                strokeWidth="2"
                strokeLinecap="round"
                strokeLinejoin="round"
                className="shrink-0 text-ink-2 transition-transform group-hover:translate-x-0.5 group-hover:text-rec"
                aria-hidden="true"
              >
                <path d="M9 6l6 6-6 6" />
              </svg>
            </button>
          ))}
        </nav>
      </div>
    </main>
  )
}
