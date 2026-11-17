/**
 * Shot logging (part 15): the Hit button, the club chips with the recommended club
 * preselected, and the finish buttons, in the caddie panel; and the logged shots on the map
 * as thin lines with draggable ends. Everything is a 44 px target or larger, in one column a
 * thumb can reach.
 */
import { type GeoJSONSource, type Map as MLMap, Marker } from 'maplibre-gl'
import { useEffect, useRef, useState } from 'react'

import { gridToLonLat, lonLatToGrid } from '../lib/geo'
import { lieAt } from '../lib/grid'
import { whenStyleReady } from '../lib/mapReady'
import { TEE_ONLY_CLUBS } from '../lib/rollout'
import type { LoggedShot } from '../lib/shotLog'
import { exportFileName, exportLog, logKey } from '../lib/shotLog'
import { clubDisplayName, token } from '../lib/tokens'
import type { Lie, Meta, Player, XY } from '../lib/types'
import { activeLog, useStore } from '../store'
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

const CHIP = 'num flex h-11 shrink-0 items-center rounded-lg px-3 text-caption font-medium transition-colors'
const BUTTON = 'flex h-14 min-w-0 items-center justify-center rounded-lg px-3 text-body font-medium transition-colors'

/** Short chip text: the club id as stamped on the stick ("7i", "PW", "SW 50"). */
export function chipText(id: string): string {
  const m = /^(sw|pw|lw|gw)(\d+)$/.exec(id)
  if (m) return `${m[1].toUpperCase()} ${m[2]}`
  if (id === 'driver') return 'Driver'
  return /^(sw|pw|lw|gw)$/.test(id) ? id.toUpperCase() : id
}

/** The chips: the recommended club first, then the rest of the bag in order; tee-only clubs only on the tee. */
export function chipClubs(player: Player, lie: Lie, recommended: string | null): string[] {
  const bag = player.club_order.filter((id) => lie === 1 || !TEE_ONLY_CLUBS.includes(id))
  return recommended && bag.includes(recommended) ? [recommended, ...bag.filter((id) => id !== recommended)] : bag
}

export function ShotLogger() {
  const bundle = useStore((s) => s.bundle)
  const player = useStore((s) => s.player)
  const ball = useStore((s) => s.ball)
  const lieOverride = useStore((s) => s.lieOverride)
  const recommendation = useStore((s) => s.recommendation)
  const log = useStore((s) => activeLog(s))
  const hitShot = useStore((s) => s.hitShot)
  const finishShot = useStore((s) => s.finishShot)
  const undoShot = useStore((s) => s.undoShot)
  const [picked, setPicked] = useState<string | null>(null)

  // A new recommendation (the ball moved) puts the chips back on the recommended club.
  const recClub = recommendation?.club ?? null
  useEffect(() => setPicked(null), [recClub, ball])

  if (!bundle || !player) return null
  const last = log[log.length - 1]
  const open = last !== undefined && last.end === null
  const lie = ball ? (lieOverride ?? lieAt(bundle, ball)) : null
  const club = picked ?? recClub
  const shown = lie !== null ? chipClubs(player, lie, recClub) : []
  const canHit = recommendation !== null && ball !== null

  return (
    <div className="flex flex-col gap-2" data-testid="shot-logger">
      {canHit && shown.length > 0 && (
        <div className="-mx-4 flex gap-2 overflow-x-auto px-4" role="radiogroup" aria-label="Club for this shot">
          {shown.map((id) => (
            <button
              key={id}
              type="button"
              role="radio"
              aria-checked={id === club}
              aria-label={clubDisplayName(id) + (id === recClub ? ' (recommended)' : '')}
              className={`${CHIP} ${id === club ? 'bg-ink text-surface' : 'border border-line bg-surface-2 text-ink'}`}
              onClick={() => setPicked(id)}
            >
              {chipText(id)}
              {id === recClub && <span className="ml-1 h-1.5 w-1.5 rounded-full bg-rec" aria-hidden="true" />}
            </button>
          ))}
        </div>
      )}
      <div className="flex gap-2">
        <button
          type="button"
          disabled={!canHit}
          className={`${BUTTON} flex-1 bg-rec font-semibold text-rec-ink disabled:opacity-40`}
          onClick={() => hitShot(club ?? undefined)}
        >
          Hit{club && canHit ? ` ${chipText(club)}` : ''}
        </button>
        {open && (
          <>
            <button type="button" className={`${BUTTON} border border-line bg-surface-2 text-ink`} onClick={() => finishShot('green')}>
              On the green
            </button>
            <button type="button" className={`${BUTTON} border border-line bg-surface-2 text-ink`} onClick={() => finishShot('penalty')}>
              Penalty
            </button>
          </>
        )}
      </div>
      {last && (
        <div className="flex h-11 items-center justify-between gap-2">
          <span className="num truncate text-caption text-ink-2" role="status">
            {shotLabel(last, log.length - 1)}
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
