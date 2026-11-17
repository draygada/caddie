/**
 * The GPS toggle on the map, the accuracy circle around the live position, and the status
 * text (part 14). The button press is the user gesture iOS Safari needs before it will
 * hand out a position.
 */
import type { GeoJSONSource, Map as MLMap } from 'maplibre-gl'
import { useEffect, useState } from 'react'

import { type GpsStatus, useGps, useGpsStatus } from '../hooks/useGps'
import { gridToLonLat } from '../lib/geo'
import { whenStyleReady } from '../lib/mapReady'
import { token } from '../lib/tokens'
import type { Meta } from '../lib/types'
import { type Gps, useStore } from '../store'

export const CIRCLE_POINTS = 32
const SOURCE = 'gps-accuracy'

/** Lon/lat ring of radius `accuracy_m` around the fix, closed, `CIRCLE_POINTS` segments. */
export function accuracyRing(meta: Meta, gps: Gps): [number, number][] {
  const ring: [number, number][] = []
  for (let k = 0; k <= CIRCLE_POINTS; k++) {
    const a = (2 * Math.PI * (k % CIRCLE_POINTS)) / CIRCLE_POINTS
    const { lon, lat } = gridToLonLat(meta, {
      x: gps.x + gps.accuracy_m * Math.cos(a),
      y: gps.y + gps.accuracy_m * Math.sin(a),
    })
    ring.push([lon, lat])
  }
  return ring
}

export function gpsLabel(status: GpsStatus, gps: Gps | null): string {
  if (status.error) return `GPS: ${status.error}`
  if (!status.enabled) return 'GPS off'
  if (status.outside) return 'GPS: you are off this hole'
  if (!gps) return 'GPS: finding you'
  return `GPS ±${Math.round(gps.accuracy_m)} m`
}

/** Status text for the bar under the map. */
export function GpsStatusText() {
  const status = useGpsStatus()
  const gps = useStore((s) => s.gps)
  return <span className={status.error ? 'text-bad' : undefined}>{gpsLabel(status, gps)}</span>
}

/** The toggle button; with a `map`, also draws the accuracy circle. */
export function GpsBadge({ map }: { map?: MLMap }) {
  const [on, setOn] = useState(false)
  const status = useGpsStatus()
  const gps = useStore((s) => s.gps)
  const bundle = useStore((s) => s.bundle)
  useGps(on)

  // A refused permission or a missing location service turns the toggle back off.
  useEffect(() => {
    if (on && status.error && !status.enabled) setOn(false)
  }, [on, status.error, status.enabled])

  useEffect(() => {
    if (!map) return
    const data = {
      type: 'FeatureCollection' as const,
      features:
        bundle && gps
          ? [
              {
                type: 'Feature' as const,
                properties: {},
                geometry: { type: 'Polygon' as const, coordinates: [accuracyRing(bundle.meta, gps)] },
              },
            ]
          : [],
    }
    return whenStyleReady(map, () => {
      const source = map.getSource(SOURCE) as GeoJSONSource | undefined
      if (source) {
        source.setData(data)
        return
      }
      const colour = token('--color-gps')
      map.addSource(SOURCE, { type: 'geojson', data })
      map.addLayer({ id: `${SOURCE}-fill`, type: 'fill', source: SOURCE, paint: { 'fill-color': colour, 'fill-opacity': 0.15 } })
      map.addLayer({ id: `${SOURCE}-line`, type: 'line', source: SOURCE, paint: { 'line-color': colour, 'line-width': 2 } })
    })
  }, [map, bundle, gps])

  const label = gpsLabel(status, gps)
  return (
    <button
      type="button"
      aria-label={on ? `Turn GPS off. ${label}` : 'Turn GPS on'}
      title={label}
      aria-pressed={on}
      onClick={() => {
        if (!on) useGpsStatus.setState({ error: null })
        setOn((v) => !v)
      }}
      className={`num flex h-12 w-12 items-center justify-center rounded-xl text-caption font-semibold shadow-[0_1px_2px_rgba(0,0,0,0.2),0_4px_12px_rgba(0,0,0,0.12)] transition-colors ${
        on ? 'bg-gps text-white' : 'bg-surface-2 text-ink'
      }`}
    >
      GPS
    </button>
  )
}
