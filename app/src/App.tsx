import { useEffect, useState } from 'react'

import { HoleMap } from './components/HoleMap'
import { LieButtons } from './components/LieButtons'
import { loadBundle, loadPlayer } from './lib/loader'
import type { Mode } from './lib/types'
import { type HoleId, useStore } from './store'
export const HOLES: HoleId[] = [10, 11, 12, 'toy']
export const MODES: Mode[] = ['mulligan', 'drop', 'replay']

function parseHole(v: string): HoleId {
  return v === 'toy' ? 'toy' : (Number(v) as 10 | 11 | 12)
}

interface PickerProps<T extends string | number> {
  label: string
  value: T
  options: readonly T[]
  onChange: (v: string) => void
}

function Picker<T extends string | number>({ label, value, options, onChange }: PickerProps<T>) {
  return (
    <label className="flex items-center gap-1 text-sm">
      <span className="text-slate-400">{label}</span>
      <select
        className="rounded border border-slate-600 bg-slate-800 px-2 py-1 text-slate-100"
        value={String(value)}
        onChange={(e) => onChange(e.target.value)}
      >
        {options.map((o) => (
          <option key={String(o)} value={String(o)}>
            {String(o)}
          </option>
        ))}
      </select>
    </label>
  )
}

export default function App() {
  const hole = useStore((s) => s.hole)
  const mode = useStore((s) => s.mode)
  const tee = useStore((s) => s.tee)
  const bundle = useStore((s) => s.bundle)
  const recommendation = useStore((s) => s.recommendation)
  const ball = useStore((s) => s.ball)
  const setHole = useStore((s) => s.setHole)
  const setMode = useStore((s) => s.setMode)
  const setTee = useStore((s) => s.setTee)
  const [error, setError] = useState<string | null>(null)

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

  return (
    <div className="flex h-screen flex-col bg-slate-900 text-slate-100">
      <header className="flex flex-wrap items-center gap-4 border-b border-slate-700 px-4 py-2">
        <h1 className="text-lg font-semibold">Caddie</h1>
        <Picker label="hole" value={hole} options={HOLES} onChange={(v) => setHole(parseHole(v))} />
        <Picker label="mode" value={mode} options={MODES} onChange={(v) => setMode(v as Mode)} />
        <Picker label="tee" value={tee} options={tees} onChange={setTee} />
        {bundle && (
          <span className="text-sm text-slate-400">
            par {bundle.meta.par} · {bundle.meta.rows} x {bundle.meta.cols} cells
          </span>
        )}
        {ball && (
          <span className="text-sm text-slate-300" data-testid="ball">
            ball {ball.x.toFixed(1)}, {ball.y.toFixed(1)} m
          </span>
        )}
        {recommendation && (
          <span className="text-sm text-emerald-300" data-testid="recommendation">
            {recommendation.club} at {recommendation.dir_deg} deg · {recommendation.expected_strokes.toFixed(2)} strokes
          </span>
        )}
        {error && <span className="text-sm text-rose-400">{error}</span>}
      </header>
      <main className="relative flex-1">
        <HoleMap bundle={bundle} tee={tee} />
      </main>
      <LieButtons />
    </div>
  )
}
