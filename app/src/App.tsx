import { useEffect, useState } from 'react'

import { CaddiePanel, distanceToPinM, toYards } from './components/CaddiePanel'
import { HoleMap } from './components/HoleMap'
import { loadBundle, loadPlayer } from './lib/loader'
import { MODE_HELP, MODE_LABEL } from './lib/tokens'
import type { Mode } from './lib/types'
import { type HoleId, useStore } from './store'

export const HOLES: HoleId[] = [10, 11, 12, 'toy']
export const MODES: Mode[] = ['mulligan', 'drop', 'replay']
const THEME_KEY = 'caddie.theme'

function parseHole(v: string): HoleId {
  return v === 'toy' ? 'toy' : (Number(v) as 10 | 11 | 12)
}

function readTheme(): 'light' | 'dark' {
  try {
    return localStorage.getItem(THEME_KEY) === 'dark' ? 'dark' : 'light'
  } catch {
    return 'light'
  }
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

export default function App() {
  const hole = useStore((s) => s.hole)
  const mode = useStore((s) => s.mode)
  const tee = useStore((s) => s.tee)
  const bundle = useStore((s) => s.bundle)
  const setHole = useStore((s) => s.setHole)
  const setMode = useStore((s) => s.setMode)
  const setTee = useStore((s) => s.setTee)
  const [error, setError] = useState<string | null>(null)
  const [theme, setTheme] = useState<'light' | 'dark'>(readTheme)
  const [moreOpen, setMoreOpen] = useState(false)

  useEffect(() => {
    document.documentElement.dataset.theme = theme
    try {
      localStorage.setItem(THEME_KEY, theme)
    } catch {
      /* private mode: the toggle still works for this page */
    }
  }, [theme])

  useEffect(() => {
    loadPlayer()
      .then((player) => useStore.setState({ player }))
      .catch((e: unknown) => setError(e instanceof Error ? e.message : String(e)))
  }, [])

  useEffect(() => {
    let cancelled = false
    setError(null)
    loadBundle(hole, mode)
      .then((b) => {
        if (cancelled) return
        useStore.setState({ bundle: b, ball: null, lieOverride: null })
        const { tee: current, setTee: pick } = useStore.getState()
        pick(current in b.meta.tees ? current : 'black' in b.meta.tees ? 'black' : Object.keys(b.meta.tees)[0])
      })
      .catch((e: unknown) => {
        if (!cancelled) setError(e instanceof Error ? e.message : String(e))
      })
    return () => {
      cancelled = true
    }
  }, [hole, mode])

  const tees = bundle ? Object.keys(bundle.meta.tees) : [tee]
  const teeXY = bundle?.meta.tees[tee] ?? bundle?.meta.tee_xy
  const yardage = bundle && teeXY ? Math.round(toYards(distanceToPinM(bundle.meta, { x: teeXY[0], y: teeXY[1] }))) : null

  return (
    <div className="flex h-full flex-col bg-surface text-ink">
      <header className="safe-top border-b border-line bg-surface px-4">
        <div className="flex h-14 items-center gap-3">
          <h1 className="text-body font-semibold">Caddie</h1>
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
            <ThemeToggle theme={theme} onToggle={() => setTheme((t) => (t === 'dark' ? 'light' : 'dark'))} />
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
        <div id="top-bar-more" className={`${moreOpen ? 'flex' : 'hidden'} flex-wrap items-center gap-3 pb-3 md:hidden`}>
          <Picker label="Tee" value={tee} options={tees} onChange={setTee} render={(t) => t.charAt(0).toUpperCase() + t.slice(1)} />
          <ModeControl value={mode} onChange={setMode} />
          <ThemeToggle theme={theme} onToggle={() => setTheme((t) => (t === 'dark' ? 'light' : 'dark'))} />
        </div>
      </header>

      <main className="relative min-h-0 flex-1 md:flex">
        <div className="relative h-full min-w-0 flex-1">
          <HoleMap bundle={bundle} tee={tee} />
          <div className="pointer-events-none absolute inset-x-0 bottom-0 md:hidden">
            <CaddiePanel />
          </div>
        </div>
        <div className="hidden h-full md:block">
          <CaddiePanel />
        </div>
      </main>

      <div className="num flex h-6 items-center gap-3 border-t border-line bg-surface px-4 text-caption text-ink-2" role="status">
        {error ? <span className="text-bad">{error}</span> : <span>GPS off</span>}
      </div>
    </div>
  )
}
