/**
 * The recommendation display: club, aim relative to the pin, expected strokes, distance
 * to the pin in yards. Reads the store only. The Play it out button lives in PlayItOut
 * (slices 5 and 6) and is mounted next to this panel.
 */
import type { Meta, XY } from '../lib/types'
import { useStore } from '../store'
import { PlayItOut } from './PlayItOut'

export const M_PER_YD = 0.9144

export function toYards(m: number): number {
  return m / M_PER_YD
}

/** "12 deg left of pin", "8 deg right of pin", or "at the pin". Negative is left. */
export function aimText(dir_deg: number): string {
  if (dir_deg === 0) return 'at the pin'
  const side = dir_deg < 0 ? 'left' : 'right'
  return `${Math.abs(dir_deg)} deg ${side} of pin`
}

export function distanceToPinM(meta: Meta, ball: XY): number {
  return Math.hypot(meta.pin_xy[0] - ball.x, meta.pin_xy[1] - ball.y)
}

export function CaddiePanel() {
  const recommendation = useStore((s) => s.recommendation)
  const ball = useStore((s) => s.ball)
  const bundle = useStore((s) => s.bundle)

  const toPinYd = bundle && ball ? toYards(distanceToPinM(bundle.meta, ball)) : null

  return (
    <aside
      className="flex min-w-56 flex-col gap-2 border-l border-slate-700 bg-slate-900 px-4 py-3"
      aria-label="Caddie"
    >
      {toPinYd !== null && (
        <div className="text-sm text-slate-400">
          {Math.round(toPinYd)} yd to the pin
        </div>
      )}
      {recommendation ? (
        <>
          <div className="text-4xl font-bold tracking-tight" data-testid="club">
            {recommendation.club}
          </div>
          <div className="text-sm text-slate-300" data-testid="aim">
            Aim {aimText(recommendation.dir_deg)}
          </div>
          <div className="text-sm" data-testid="expected">
            Expected strokes from here:{' '}
            <span className="font-semibold text-emerald-300">
              {recommendation.expected_strokes.toFixed(1)}
            </span>
          </div>
          {recommendation.baseline_pin_strokes !== undefined && (
            <div className="text-sm text-slate-400" data-testid="baseline">
              Aim at pin with {recommendation.club}: {recommendation.baseline_pin_strokes.toFixed(1)}
            </div>
          )}
          <PlayItOut />
        </>
      ) : (
        <div className="text-sm text-slate-400">
          {ball ? 'No shot from here: on the green or off the hole.' : 'Click the map to place the ball.'}
        </div>
      )}
    </aside>
  )
}
