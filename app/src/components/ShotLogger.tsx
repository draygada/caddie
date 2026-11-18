/**
 * Shot logging (part 15): the Hit button, the club chips with the recommended club
 * preselected, and the finish buttons, in the caddie panel; and the logged shots on the map
 * as thin lines with draggable ends. Everything is a 44 px target or larger, in one column a
 * thumb can reach.
 */
import { type GeoJSONSource, type Map as MLMap, Marker } from 'maplibre-gl'
import { useEffect, useRef, useState } from 'react'

import { gridToLonLat, lonLatToGrid } from '../lib/geo'
import { whenStyleReady } from '../lib/mapReady'
import type { LoggedShot } from '../lib/shotLog'
import { type Dwell, exportFileName, exportLog, logKey, shouldPromptLanding, updateDwell } from '../lib/shotLog'
import { clubDisplayName, token } from '../lib/tokens'
import type { Meta, XY } from '../lib/types'
import { activeLog, currentAim, useStore } from '../store'
import { chipText } from './AimPanel'
import { insideGrid } from './BallMarker'
import { toYards } from './CaddiePanel'

const SOURCE = 'shot-log'

function lonLat(meta: Meta, p: XY): [number, number] {
  const { lon, lat } = gridToLonLat(meta, p)
  return [lon, lat]
}

/** One line per shot: finished shots start to end, the open shot start to the ball. */
export function shotLineFeatures(meta: Meta, log: LoggedShot[], ball: XY | null) {
  const features = []
  for (const s of log) {
    const to = s.end ?? ball
    if (!to || (to.x === s.start.x && to.y === s.start.y)) continue
    features.push({
      type: 'Feature' as const,
      properties: { open: s.end === null, penalty: s.outcome === 'penalty' },
      geometry: { type: 'LineString' as const, coordinates: [lonLat(meta, s.start), lonLat(meta, to)] },
    })
  }
  return { type: 'FeatureCollection' as const, features }
}

/** Indices of the shots whose end gets a drag handle: finished, and not under the ball marker. */
export function endHandles(log: LoggedShot[], ball: XY | null): number[] {
  const out: number[] = []
  log.forEach((s, k) => {
    if (!s.end) return
    if (ball && ball.x === s.end.x && ball.y === s.end.y) return
    out.push(k)
  })
  return out
}

/** "Shot 2: 7 iron, 148 yd". */
export function shotLabel(s: LoggedShot, index: number): string {
  const head = `Shot ${index + 1}: ${clubDisplayName(s.club)}`
  if (!s.end) return `${head}, in the air`
  if (s.outcome === 'penalty') return `${head}, penalty`
  return `${head}, ${Math.round(toYards(Math.hypot(s.end.x - s.start.x, s.end.y - s.start.y)))} yd`
}

const BUTTON = 'flex h-14 min-w-0 items-center justify-center rounded-lg px-3 text-body font-medium transition-colors'

/**
 * Slice 8: with GPS on, true once the player has stood still for 20 s at least 20 m from the
 * open shot's start. It only reveals a button; a shot is recorded on a tap and never otherwise.
 */
function useLandingPrompt(openStart: XY | null): boolean {
  const gps = useStore((s) => s.gps)
  const dwellRef = useRef<Dwell | null>(null)
  const [show, setShow] = useState(false)

  useEffect(() => {
    dwellRef.current = gps ? updateDwell(dwellRef.current, gps, Date.now()) : null
  }, [gps])

  useEffect(() => {
    if (!gps || !openStart) {
      setShow(false)
      return
    }
    const check = () => setShow(shouldPromptLanding(dwellRef.current, openStart, Date.now()))
    check()
    const id = setInterval(check, 1000)
    return () => clearInterval(id)
  }, [gps, openStart])

  return show
}

export function ShotLogger() {
  const bundle = useStore((s) => s.bundle)
  const player = useStore((s) => s.player)
  const ball = useStore((s) => s.ball)
  const recommendation = useStore((s) => s.recommendation)
  const aim = useStore(currentAim)
  const log = useStore((s) => activeLog(s))
  const hitShot = useStore((s) => s.hitShot)
  const finishShot = useStore((s) => s.finishShot)
  const undoShot = useStore((s) => s.undoShot)
  const lastShot = log[log.length - 1]
  const open = lastShot !== undefined && lastShot.end === null
  const ballHere = useLandingPrompt(open ? lastShot.start : null)

  if (!bundle || !player) return null
  const club = aim?.club ?? recommendation?.club ?? null
  const canHit = recommendation !== null && ball !== null
  const plain = `${BUTTON} border border-line bg-surface-2 text-ink`

  return (
    <div className="flex flex-col gap-2" data-testid="shot-logger">
      {open ? (
        // The ball is in the air or being walked to: confirm where it finished (part 22).
        <div className="flex gap-2">
          <button
            type="button"
            disabled={ball === null}
            className={`${BUTTON} flex-1 font-semibold disabled:opacity-40 ${ballHere ? 'bg-gps text-white' : 'bg-rec text-rec-ink'}`}
            onClick={() => finishShot('normal')}
            data-testid="ball-here"
          >
            Ball is here
          </button>
          <button type="button" className={plain} onClick={() => finishShot('green')}>
            On the green
          </button>
          <button type="button" className={plain} onClick={() => finishShot('penalty')}>
            Penalty
          </button>
        </div>
      ) : (
        <button
          type="button"
          disabled={!canHit}
          className={`${BUTTON} bg-rec font-semibold text-rec-ink disabled:opacity-40`}
          onClick={() => hitShot()}
        >
          Hit{club && canHit ? ` ${chipText(club)}` : ''}
        </button>
      )}
      {lastShot && (
        <div className="flex h-11 items-center justify-between gap-2">
          <span className="num truncate text-caption text-ink-2" role="status">
            {shotLabel(lastShot, log.length - 1)}
          </span>
          <button type="button" className="h-11 shrink-0 rounded-lg px-3 text-caption font-medium text-ink-2 underline" onClick={() => undoShot()}>
            Undo
          </button>
        </div>
      )}
    </div>
  )
}

/** Download the round being played as JSON, for `fit --course-log` (part 15 slice 7). */
export function ExportLogButton() {
  const hole = useStore((s) => s.hole)
  const log = useStore((s) => activeLog(s))
  if (log.length === 0) return null
  const download = () => {
    const url = URL.createObjectURL(exportLog(log, hole))
    const a = document.createElement('a')
    a.href = url
    a.download = exportFileName(logKey(log[0].t, hole))
    a.click()
    URL.revokeObjectURL(url)
  }
  return (
    <button
      type="button"
      className="flex h-12 items-center justify-center rounded-lg border border-line bg-surface-2 px-3 text-body text-ink"
      onClick={download}
    >
      Export {log.length} {log.length === 1 ? 'shot' : 'shots'}
    </button>
  )
}

function handleElement(label: string): HTMLElement {
  const el = document.createElement('div')
  // A 44 px touch target around a 14 px dot.
  el.style.cssText = 'width:44px;height:44px;display:flex;align-items:center;justify-content:center;cursor:grab;touch-action:none'
  const dot = document.createElement('div')
  dot.style.cssText = `width:14px;height:14px;border-radius:50%;background:${token('--color-surface-2')};border:2px solid ${token('--color-ink')}`
  el.appendChild(dot)
  el.setAttribute('aria-label', label)
  return el
}

/** The logged shots on the map. A dragged end is a correction: accuracy 0 (part 15). */
export function ShotLogLayer({ map }: { map: MLMap }) {
  const bundle = useStore((s) => s.bundle)
  const hole = useStore((s) => s.hole)
  const ball = useStore((s) => s.ball)
  const log = useStore((s) => activeLog(s))
  const moveShotEnd = useStore((s) => s.moveShotEnd)
  const markersRef = useRef<Marker[]>([])

  useEffect(() => {
    if (!bundle) return
    const data = shotLineFeatures(bundle.meta, log, ball)
    return whenStyleReady(map, () => {
      const source = map.getSource(SOURCE) as GeoJSONSource | undefined
      if (source) {
        source.setData(data)
        return
      }
      map.addSource(SOURCE, { type: 'geojson', data })
      map.addLayer({
        id: SOURCE,
        type: 'line',
        source: SOURCE,
        paint: {
          'line-color': ['case', ['get', 'penalty'], token('--color-bad'), token('--color-surface-2')],
          'line-width': 1.5,
          'line-opacity': ['case', ['get', 'open'], 0.6, 1],
        },
      })
    })
  }, [map, bundle, log, ball])

  useEffect(() => {
    if (!bundle) return
    const meta = bundle.meta
    const markers = endHandles(log, ball).map((k) => {
      const end = log[k].end as XY
      const marker = new Marker({ element: handleElement(`End of shot ${k + 1}, drag to correct`), draggable: true })
        .setLngLat(lonLat(meta, end))
        .addTo(map)
      marker.on('dragend', () => {
        const ll = marker.getLngLat()
        const p = lonLatToGrid(meta, ll.lng, ll.lat)
        if (insideGrid(meta, p)) moveShotEnd(logKey(log[k].t, hole), k, p)
        else marker.setLngLat(lonLat(meta, end)) // snap back
      })
      return marker
    })
    markersRef.current = markers
    return () => markers.forEach((m) => m.remove())
  }, [map, bundle, hole, log, ball, moveShotEnd])

  return null
}
