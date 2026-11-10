/**
 * The ball: placed by clicking the map, shown as a MapLibre marker. Reads the bundle and
 * ball from the store; writes the ball back through `setBall`.
 */
import { Map as MLMap, type MapMouseEvent, Marker } from 'maplibre-gl'
import { useEffect, useRef } from 'react'

import { gridToLonLat, lonLatToGrid } from '../lib/geo'
import type { Meta, XY } from '../lib/types'
import { useStore } from '../store'

export const BALL_COLOUR = '#f8fafc'

export function insideGrid(meta: Meta, p: XY): boolean {
  return p.x >= 0 && p.y >= 0 && p.x < meta.cols * meta.cell_m && p.y < meta.rows * meta.cell_m
}

export function BallMarker({ map }: { map: MLMap }) {
  const bundle = useStore((s) => s.bundle)
  const ball = useStore((s) => s.ball)
  const setBall = useStore((s) => s.setBall)
  const markerRef = useRef<Marker | null>(null)

  // Click on the map sets the ball; clicks outside the grid are ignored.
  useEffect(() => {
    if (!bundle) return
    const onClick = (e: MapMouseEvent) => {
      const p = lonLatToGrid(bundle.meta, e.lngLat.lng, e.lngLat.lat)
      if (insideGrid(bundle.meta, p)) setBall(p)
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
      markerRef.current = new Marker({ color: BALL_COLOUR }).setLngLat([lon, lat]).addTo(map)
    } else {
      markerRef.current.setLngLat([lon, lat])
    }
  }, [map, bundle, ball])

  useEffect(
    () => () => {
      markerRef.current?.remove()
      markerRef.current = null
    },
    [],
  )

  return null
}
