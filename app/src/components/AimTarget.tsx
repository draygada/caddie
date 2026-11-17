/**
 * The aim on the map (part 22): a ring the player can drag or place with a tap, a line from
 * the ball to it and on to the pin with both distances, and a dot for where each of 200
 * shots with the current club finishes. Replaces the fixed aim arrow and its labels.
 */
import { type GeoJSONSource, type Map as MLMap, Marker } from 'maplibre-gl'
import { useEffect, useRef } from 'react'

import type { Aim } from '../lib/aim'
import { gridToLonLat, lonLatToGrid } from '../lib/geo'
import { whenStyleReady } from '../lib/mapReady'
import type { ActionOutcome } from '../lib/rollout'
import { clubDisplayName, token } from '../lib/tokens'
import type { Meta, XY } from '../lib/types'
import { currentAim, currentOutcome, useStore } from '../store'
import { insideGrid } from './BallMarker'
import { toYards } from './CaddiePanel'

const SOURCE = 'aim-target'

export function targetLabel(aim: Aim): string {
  return `${clubDisplayName(aim.club)} · ${Math.round(toYards(aim.toTargetM))} yd`
}

export function restLabel(aim: Aim): string {
  return `${Math.round(toYards(aim.toPinM))} yd to pin`
}

function lonLat(meta: Meta, p: XY): [number, number] {
  const { lon, lat } = gridToLonLat(meta, p)
  return [lon, lat]
}

/** The two lines and the finish dots as GeoJSON. */
export function aimFeatures(meta: Meta, ball: XY, aim: Aim | null, finishes: ActionOutcome['finishes']) {
  if (!aim) return { type: 'FeatureCollection' as const, features: [] }
  const pin = { x: meta.pin_xy[0], y: meta.pin_xy[1] }
  const line = (kind: string, a: XY, b: XY) => ({
    type: 'Feature' as const,
    properties: { kind, penalty: false },
    geometry: { type: 'LineString' as const, coordinates: [lonLat(meta, a), lonLat(meta, b)] },
  })
  const dots = finishes.map((f) => ({
    type: 'Feature' as const,
    properties: { kind: 'dot', penalty: f.penalty },
    geometry: { type: 'Point' as const, coordinates: lonLat(meta, f) },
  }))
  return { type: 'FeatureCollection' as const, features: [...dots, line('rest', aim.target, pin), line('aim', ball, aim.target)] }
}

function ringElement(): HTMLElement {
  const el = document.createElement('div')
  // A 48 px touch target around a 22 px ring.
  el.style.cssText = 'width:48px;height:48px;display:flex;align-items:center;justify-content:center;cursor:grab;touch-action:none'
  const ring = document.createElement('div')
  ring.style.cssText = `width:22px;height:22px;border-radius:50%;border:3px solid ${token('--color-surface-2')};box-shadow:0 0 0 1.5px rgba(17,23,20,0.7), inset 0 0 0 1.5px rgba(17,23,20,0.7)`
  el.appendChild(ring)
  el.setAttribute('aria-label', 'Aim target, drag to move')
  return el
}

function pill(): HTMLDivElement {
  const el = document.createElement('div')
  el.className = 'map-pill'
  el.setAttribute('aria-hidden', 'true')
  return el
}

export function AimTarget({ map }: { map: MLMap }) {
  const bundle = useStore((s) => s.bundle)
  const ball = useStore((s) => s.ball)
  const aim = useStore(currentAim)
  const outcome = useStore(currentOutcome)
  const setTarget = useStore((s) => s.setTarget)
  const ringRef = useRef<Marker | null>(null)
  const targetPillRef = useRef<Marker | null>(null)
  const restPillRef = useRef<Marker | null>(null)
  const metaRef = useRef<Meta | null>(null)
  metaRef.current = bundle?.meta ?? null

  // Lines and dots.
  useEffect(() => {
    if (!bundle) return
    const data = aimFeatures(bundle.meta, ball ?? { x: 0, y: 0 }, ball ? aim : null, outcome?.finishes ?? [])
    return whenStyleReady(map, () => {
      const source = map.getSource(SOURCE) as GeoJSONSource | undefined
      if (source) {
        source.setData(data)
        return
      }
      const rec = token('--color-rec')
      map.addSource(SOURCE, { type: 'geojson', data })
      map.addLayer({
        id: `${SOURCE}-dots`,
        type: 'circle',
        source: SOURCE,
        filter: ['==', ['get', 'kind'], 'dot'],
        paint: {
          'circle-radius': 2.5,
          'circle-color': ['case', ['get', 'penalty'], token('--color-bad'), '#ffffff'],
          'circle-opacity': 0.75,
          'circle-stroke-color': 'rgba(17,23,20,0.5)',
          'circle-stroke-width': 0.5,
        },
      })
      map.addLayer({
        id: `${SOURCE}-rest`,
        type: 'line',
        source: SOURCE,
        filter: ['==', ['get', 'kind'], 'rest'],
        paint: { 'line-color': '#ffffff', 'line-width': 1.5, 'line-dasharray': [2, 2], 'line-opacity': 0.9 },
      })
      map.addLayer({
        id: `${SOURCE}-aim`,
        type: 'line',
        source: SOURCE,
        filter: ['==', ['get', 'kind'], 'aim'],
        paint: { 'line-color': rec, 'line-width': 3 },
      })
    })
  }, [map, bundle, ball, aim, outcome])

  // The ring and the two distance pills.
  useEffect(() => {
    const clear = () => {
      for (const ref of [ringRef, targetPillRef, restPillRef]) {
        ref.current?.remove()
        ref.current = null
      }
    }
    if (!bundle || !ball || !aim) {
      clear()
      return
    }
    const meta = bundle.meta
    const at = lonLat(meta, aim.target)
    if (!ringRef.current) {
      const ring = new Marker({ element: ringElement(), draggable: true }).setLngLat(at).addTo(map)
      const move = () => {
        const m = metaRef.current
        if (!m) return
        const ll = ring.getLngLat()
        const p = lonLatToGrid(m, ll.lng, ll.lat)
        if (insideGrid(m, p)) setTarget(p)
      }
      ring.on('drag', move)
      ring.on('dragend', move)
      ringRef.current = ring
      targetPillRef.current = new Marker({ element: pill(), anchor: 'bottom', offset: [0, -18] }).setLngLat(at).addTo(map)
      restPillRef.current = new Marker({ element: pill(), anchor: 'center' }).setLngLat(at).addTo(map)
    }
    ringRef.current.setLngLat(at)
    targetPillRef.current?.setLngLat(at)
    const mid = { x: (aim.target.x + meta.pin_xy[0]) / 2, y: (aim.target.y + meta.pin_xy[1]) / 2 }
    restPillRef.current?.setLngLat(lonLat(meta, mid))
    const t = targetPillRef.current?.getElement()
    const r = restPillRef.current?.getElement()
    if (t) t.textContent = targetLabel(aim)
    if (r) r.textContent = restLabel(aim)
  }, [map, bundle, ball, aim, setTarget])

  useEffect(
    () => () => {
      for (const ref of [ringRef, targetPillRef, restPillRef]) {
        ref.current?.remove()
        ref.current = null
      }
    },
    [],
  )

  return null
}
