/**
 * The ball: placed by clicking the map, shown as a MapLibre marker. Reads the bundle and
 * ball from the store; writes the ball back through `setBall`.
 */
import { Map as MLMap, type MapMouseEvent, Marker } from 'maplibre-gl'
import { useEffect, useRef } from 'react'

import { gridToLonLat, lonLatToGrid } from '../lib/geo'
import { token } from '../lib/tokens'
import type { Meta, XY } from '../lib/types'
import { useStore } from '../store'

/** After a manual drag, GPS updates are ignored for this long. */
export const GPS_HOLD_MS = 10_000

export function insideGrid(meta: Meta, p: XY): boolean {
  return p.x >= 0 && p.y >= 0 && p.x < meta.cols * meta.cell_m && p.y < meta.rows * meta.cell_m
}

export function BallMarker({ map }: { map: MLMap }) {
  const bundle = useStore((s) => s.bundle)
  const ball = useStore((s) => s.ball)
  const setBall = useStore((s) => s.setBall)
  const gps = useStore((s) => s.gps)
  // Part 22: in Simulate the ball stays on the tee; in Play a drag corrects the GPS fix.
  const draggable = useStore((s) => s.screen === 'play')
  const markerRef = useRef<Marker | null>(null)
  const lastDragRef = useRef(0)
  // Latest bundle and ball for the dragend handler, which is bound once per marker.
  const bundleRef = useRef(bundle)
  const ballRef = useRef(ball)
  bundleRef.current = bundle ?? bundleRef.current
  ballRef.current = ball

  // A tap on the map moves the aim target; taps outside the grid are ignored.
  useEffect(() => {
    if (!bundle) return
    const onClick = (e: MapMouseEvent) => {
      const p = lonLatToGrid(bundle.meta, e.lngLat.lng, e.lngLat.lat)
      if (!insideGrid(bundle.meta, p)) return
      // Part 22: a tap aims. It only places the ball when there is none yet (Play before a fix).
      const { ball: at, setTarget } = useStore.getState()
      if (at) setTarget(p)
      else setBall(p)
    }
    map.on('click', onClick)
    return () => {
      map.off('click', onClick)
    }
  }, [map, bundle, setBall])

  // Keep the marker where the store says the ball is.
  useEffect(() => {
    if (!bundle || !ball) {
      markerRef.current?.remove()
      markerRef.current = null
      return
    }
    const { lon, lat } = gridToLonLat(bundle.meta, ball)
    if (!markerRef.current) {
      const marker = new Marker({ color: token('--ball'), draggable: true }).setLngLat([lon, lat]).addTo(map)
      marker.getElement().setAttribute('aria-label', 'Ball')
      // `drag` fires continuously; only the end of a drag writes the store.
      marker.on('dragend', () => {
        const meta = bundleRef.current?.meta
        if (!meta) return
        const ll = marker.getLngLat()
        const p = lonLatToGrid(meta, ll.lng, ll.lat)
        lastDragRef.current = Date.now()
        if (insideGrid(meta, p)) setBall(p)
        else setBall(ballRef.current) // snap back
      })
      markerRef.current = marker
    } else {
      markerRef.current.setLngLat([lon, lat])
    }
  }, [map, bundle, ball, setBall])

  // GPS (part 14 sets it): follow it unless the user dragged in the last 10 s.
  useEffect(() => {
    if (!gps || !bundle) return
    if (Date.now() - lastDragRef.current < GPS_HOLD_MS) return
    setBall({ x: gps.x, y: gps.y })
  }, [gps, bundle, setBall])

  useEffect(() => {
    markerRef.current?.setDraggable(draggable)
  }, [draggable, ball])

  useEffect(
    () => () => {
      markerRef.current?.remove()
      markerRef.current = null
    },
    [],
  )

  return null
}
