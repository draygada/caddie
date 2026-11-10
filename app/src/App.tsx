import { useEffect, useState } from 'react'

import { HoleMap } from './components/HoleMap'
import { loadBundle } from './lib/loader'
import type { HoleBundle, Mode } from './lib/types'

export type HoleId = 10 | 11 | 12 | 'toy'

export default function App() {
  const [hole] = useState<HoleId>('toy')
  const [mode] = useState<Mode>('drop')
  const [tee] = useState('black')
  const [bundle, setBundle] = useState<HoleBundle | null>(null)
  const [error, setError] = useState<string | null>(null)

  useEffect(() => {
    let cancelled = false
    setError(null)
    loadBundle(hole, mode)
      .then((b) => {
        if (!cancelled) setBundle(b)
      })
      .catch((e: unknown) => {
        if (!cancelled) setError(e instanceof Error ? e.message : String(e))
      })
    return () => {
      cancelled = true
    }
  }, [hole, mode])

  return (
    <div className="flex h-screen flex-col bg-slate-900 text-slate-100">
      <header className="flex items-center gap-4 border-b border-slate-700 px-4 py-2">
        <h1 className="text-lg font-semibold">Caddie</h1>
        <span className="text-sm text-slate-400">
          hole {String(hole)} · {mode}
        </span>
        {error && <span className="text-sm text-rose-400">{error}</span>}
      </header>
      <main className="relative flex-1">
        <HoleMap bundle={bundle} tee={tee} />
      </main>
    </div>
  )
}
