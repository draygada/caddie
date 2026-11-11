/**
 * Lie override row: Fairway, Rough, Bunker toggles and Auto, which clears the override.
 * The highlighted button is `lieOverride ?? lieAt(bundle, ball)`.
 */
import { lieAt } from '../lib/grid'
import type { Lie } from '../lib/types'
import { useStore } from '../store'

export const LIE_OPTIONS: { label: string; lie: Lie }[] = [
  { label: 'Fairway', lie: 2 },
  { label: 'Rough', lie: 3 },
  { label: 'Bunker', lie: 4 },
]

export function LieButtons() {
  const bundle = useStore((s) => s.bundle)
  const ball = useStore((s) => s.ball)
  const lieOverride = useStore((s) => s.lieOverride)
  const setLieOverride = useStore((s) => s.setLieOverride)

  const current: Lie | null = lieOverride ?? (bundle && ball ? lieAt(bundle, ball) : null)
  const base = 'rounded px-3 py-1 text-sm font-medium transition-colors'
  const on = 'bg-emerald-500 text-slate-900'
  const off = 'bg-slate-700 text-slate-200 hover:bg-slate-600'

  return (
    <div className="flex items-center gap-2 border-t border-slate-700 px-4 py-2" role="group" aria-label="Lie">
      <span className="text-sm text-slate-400">lie</span>
      {LIE_OPTIONS.map(({ label, lie }) => (
        <button
          key={lie}
          type="button"
          aria-pressed={current === lie}
          className={`${base} ${current === lie ? on : off}`}
          onClick={() => setLieOverride(lieOverride === lie ? null : lie)}
        >
          {label}
        </button>
      ))}
      <button
        type="button"
        aria-pressed={lieOverride === null}
        className={`${base} ${lieOverride === null ? 'bg-slate-500 text-slate-50' : off}`}
        onClick={() => setLieOverride(null)}
      >
        Auto
      </button>
    </div>
  )
}
