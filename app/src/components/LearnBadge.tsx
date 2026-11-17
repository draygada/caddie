/**
 * "Use my course shots" (part 15): off by default. When on, the rollout plans with the
 * player learned from the shot log and the badge says how many shots that is.
 */
import { learnedObservations, useStore } from '../store'

export const LEARN_HELP =
  'Your logged shots update each club you hit. The live recommendation uses the updated clubs; the strokes-to-go map is not re-solved.'

export function learnBadgeText(n: number): string {
  if (n === 0) return 'No course shots to learn from yet'
  return `Learned from ${n} ${n === 1 ? 'shot' : 'shots'}`
}

export function LearnBadge() {
  const learn = useStore((s) => s.learn)
  const setLearn = useStore((s) => s.setLearn)
  const logs = useStore((s) => s.logs)
  const bundle = useStore((s) => s.bundle)
  const player = useStore((s) => s.player)
  const n = learn ? learnedObservations({ logs, bundle, player }).length : 0

  return (
    <div className="flex flex-col gap-1">
      <button
        type="button"
        role="switch"
        aria-checked={learn}
        title={LEARN_HELP}
        className="flex h-12 items-center justify-between gap-3 rounded-lg border border-line bg-surface-2 px-3 text-body text-ink"
        onClick={() => setLearn(!learn)}
      >
        <span>Use my course shots</span>
        <span className={`relative h-6 w-10 shrink-0 rounded-full transition-colors ${learn ? 'bg-rec' : 'bg-line'}`} aria-hidden="true">
          <span className={`absolute top-0.5 h-5 w-5 rounded-full bg-surface-2 shadow transition-all ${learn ? 'left-[18px]' : 'left-0.5'}`} />
        </span>
      </button>
      {learn && (
        <span className="num text-caption text-ink-2" title={LEARN_HELP} data-testid="learn-badge" role="status">
          {learnBadgeText(n)}
        </span>
      )}
    </div>
  )
}
