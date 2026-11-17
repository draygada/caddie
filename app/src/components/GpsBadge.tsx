/**
 * The accuracy circle around the live position, the status text (part 14) and the notice
 * for a failed watch. Since part 21 there is no toggle: GPS is on in Play and absent in
 * Simulate, and tapping "Play with GPS" on the home page is the gesture iOS Safari needs.
 */
import type { GeoJSONSource, Map as MLMap } from 'maplibre-gl'
import { useEffect } from 'react'

import { type GpsStatus, useGpsStatus } from '../hooks/useGps'
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

/** The accuracy circle around the live position. GPS itself is started by the Play screen (part 21). */
export function GpsLayer({ map }: { map: MLMap }) {
  const gps = useStore((s) => s.gps)
  const bundle = useStore((s) => s.bundle)

  useEffect(() => {
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

  return null
}

/** Plain words for a GPS error: a refused permission, or a fix that will not come. */
export function gpsProblemText(error: string): string {
  if (/denied|permission/i.test(error)) return 'Location is turned off for this site. Allow it in your browser settings, then try again.'
  return `Cannot find you yet: ${error.replace(/\.$/, '')}.`
}

/** Shown in the Play panel when the watch has failed. The button press is a fresh user gesture. */
export function GpsNotice({ onRetry }: { onRetry: () => void }) {
  const error = useGpsStatus((s) => s.error)
  if (!error) return null
  return (
    <div className="flex flex-col gap-2 rounded-lg border border-line bg-surface-2 p-3" role="alert">
      <p className="text-body text-ink">{gpsProblemText(error)}</p>
      <p className="text-caption text-ink-2">You can still tap the map to place the ball. Simulate works without location.</p>
      <button
        type="button"
        className="flex h-12 items-center justify-center rounded-lg bg-ink px-3 text-body font-medium text-surface"
        onClick={onRetry}
      >
        Try again
      </button>
    </div>
  )
}
