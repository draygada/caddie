/**
 * Lie row: Auto, Fairway, Rough, Bunker as 56 px segments (pressed with a glove). Auto
 * clears the override. The filled segment is `lieOverride ?? lieAt(bundle, ball)`.
 */
import { lieAt } from '../lib/grid'
import type { Lie } from '../lib/types'
import { useStore } from '../store'

export const LIE_OPTIONS: { label: string; lie: Lie }[] = [
  { label: 'Fairway', lie: 2 },
  { label: 'Rough', lie: 3 },
  { label: 'Bunker', lie: 4 },
]

const SEGMENT = 'flex h-14 min-w-0 flex-1 items-center justify-center rounded-lg text-body font-medium transition-colors'
const ON = 'bg-ink text-surface'
const OFF = 'bg-surface-2 text-ink border border-line hover:bg-line/60'

export function LieButtons() {
  const bundle = useStore((s) => s.bundle)
  const ball = useStore((s) => s.ball)
  const lieOverride = useStore((s) => s.lieOverride)
  const setLieOverride = useStore((s) => s.setLieOverride)

  const current: Lie | null = lieOverride ?? (bundle && ball ? lieAt(bundle, ball) : null)
  const auto = lieOverride === null

  return (
    <div className="flex flex-col gap-1">
      <span className="label" id="lie-label">
        Lie
      </span>
      <div className="flex gap-2" role="group" aria-labelledby="lie-label">
        <button
          type="button"
          aria-pressed={auto}
          className={`${SEGMENT} ${auto ? ON : OFF}`}
          onClick={() => setLieOverride(null)}
        >
          Auto
        </button>
        {LIE_OPTIONS.map(({ label, lie }) => (
          <button
            key={lie}
            type="button"
            aria-pressed={current === lie}
            className={`${SEGMENT} ${!auto && current === lie ? ON : OFF}`}
            onClick={() => setLieOverride(lieOverride === lie ? null : lie)}
          >
            {label}
            {auto && current === lie && <span className="sr-only"> (detected)</span>}
          </button>
        ))}
      </div>
    </div>
  )
}
