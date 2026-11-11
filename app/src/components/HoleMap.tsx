/**
 * Satellite map of the hole with the strokes-to-go heatmap and the hole polygons.
 * Until the store exists (part 11) the bundle comes in as a prop from App.
 */
import {
  AttributionControl,
  type ImageSource,
  type ExpressionSpecification,
  type GeoJSONSource,
  LngLatBounds,
  Map as MLMap,
  NavigationControl,
  setWorkerUrl,
  type StyleSpecification,
} from 'maplibre-gl'
import 'maplibre-gl/dist/maplibre-gl.css'
import workerUrl from 'maplibre-gl/dist/maplibre-gl-worker.mjs?url'
import type { Feature as GJFeature, FeatureCollection, Geometry } from 'geojson'
import { type ReactNode, useEffect, useRef, useState } from 'react'

import { AimArrow } from './AimArrow'
import { BallMarker } from './BallMarker'
import { MapLabels } from './MapLabels'
import { PlayItOutLayer } from './PlayItOut'

import { gridCorners, gridToLonLat } from '../lib/geo'
import { heatmapDataUrl } from '../lib/heatmap'
import { whenStyleReady } from '../lib/mapReady'
import { token } from '../lib/tokens'
import type { HoleBundle, Meta, XY } from '../lib/types'

export const ESRI_TILES =
  'https://server.arcgisonline.com/ArcGIS/rest/services/World_Imagery/MapServer/tile/{z}/{y}/{x}'
export const ESRI_ATTRIBUTION = 'Esri, Maxar, Earthstar Geographics'
export const MAX_ZOOM = 19
export const HEAT_OPACITY = 0.55
export const FIT_PADDING_PX = 24

/** Collapsed bottom sheet height on a phone, so the fit keeps the hole above it. */
export const SHEET_PADDING_PX = 270
export const TOP_BAR_PADDING_PX = 88

function isPhone(): boolean {
  return typeof window !== 'undefined' && window.matchMedia('(max-width: 767px)').matches
}

/** Padding that keeps the fitted grid clear of the floating top bar, the map buttons and the sheet. */
export function fitPadding(): { top: number; bottom: number; left: number; right: number } {
  return {
    top: TOP_BAR_PADDING_PX,
    bottom: isPhone() ? SHEET_PADDING_PX : FIT_PADDING_PX,
    left: FIT_PADDING_PX,
    right: FIT_PADDING_PX,
  }
}

/** Bearing = hole bearing, so +y points up the screen, then fit the rotated grid. */
export function fitToGrid(map: MLMap, meta: Meta): void {
  const bounds = new LngLatBounds()
  for (const [lon, lat] of gridCorners(meta)) bounds.extend([lon, lat])
  map.setBearing(meta.rotation_deg)
  map.fitBounds(bounds, { padding: fitPadding(), bearing: meta.rotation_deg, duration: 0 })
}

/** Polygon kinds in draw order; colours come from the --t-* tokens (docs/design.md). */
const POLYGON_KINDS = ['fairway', 'rough', 'green', 'bunker', 'water', 'ob', 'tee']
export function lieColours(): Record<string, string> {
  return Object.fromEntries(POLYGON_KINDS.map((k) => [k, token(`--t-${k}`)]))
}
/** Terrain fills never exceed 35 percent; 25 keeps fairway edges legible over the heatmap. */
export const TERRAIN_FILL_OPACITY = 0.25

type Feature = GJFeature<Geometry, { kind: string }>

function polygonFeatures(meta: Meta): FeatureCollection {
  const features: Feature[] = []
  for (const kind of POLYGON_KINDS) {
    for (const ring of meta.polygons[kind] ?? []) {
      const coords = ring.map(([x, y]) => {
        const { lon, lat } = gridToLonLat(meta, { x, y })
        return [lon, lat]
      })
      if (coords.length < 4) continue
      features.push({
        type: 'Feature',
        properties: { kind },
        geometry: { type: 'Polygon', coordinates: [coords] },
      })
    }
  }
  return { type: 'FeatureCollection', features }
}

function markerFeatures(meta: Meta, tee: string): FeatureCollection {
  const point = (kind: string, xy: XY): Feature => {
    const { lon, lat } = gridToLonLat(meta, xy)
    return { type: 'Feature', properties: { kind }, geometry: { type: 'Point', coordinates: [lon, lat] } }
  }
  const teeXY = meta.tees[tee] ?? meta.tee_xy
  return {
    type: 'FeatureCollection',
    features: [
      point('pin', { x: meta.pin_xy[0], y: meta.pin_xy[1] }),
      point('tee', { x: teeXY[0], y: teeXY[1] }),
    ],
  }
}

function fillColour(): ExpressionSpecification {
  const colours = lieColours()
  const expr: unknown[] = ['match', ['get', 'kind']]
  for (const k of POLYGON_KINDS) expr.push(k, colours[k])
  expr.push('#ffffff')
  return expr as ExpressionSpecification
}

// Vite pre-bundles maplibre-gl, which breaks the worker URL it derives from its own
// module; point it at the worker file Vite serves instead.
setWorkerUrl(workerUrl)

const STYLE: StyleSpecification = {
  version: 8,
  sources: {
    esri: {
      type: 'raster',
      tiles: [ESRI_TILES],
      tileSize: 256,
      maxzoom: MAX_ZOOM,
      attribution: ESRI_ATTRIBUTION,
    },
  },
  layers: [{ id: 'esri', type: 'raster', source: 'esri' }],
}

const HEAT_KEY = 'caddie.heat'
function readHeatOn(): boolean {
  try {
    return localStorage.getItem(HEAT_KEY) !== 'off'
  } catch {
    return true
  }
}

/** 48 px map button on the panel surface; `pressed` fills it for a toggle that is on. */
function MapButton({
  label,
  pressed,
  onClick,
  children,
}: {
  label: string
  pressed?: boolean
  onClick: () => void
  children: ReactNode
}) {
  return (
    <button
      type="button"
      aria-label={label}
      title={label}
      aria-pressed={pressed}
      onClick={onClick}
      className={`flex h-12 w-12 items-center justify-center rounded-xl shadow-[0_1px_2px_rgba(0,0,0,0.2),0_4px_12px_rgba(0,0,0,0.12)] transition-colors ${
        pressed ? 'bg-ink text-surface' : 'bg-surface-2 text-ink'
      }`}
    >
      {children}
    </button>
  )
}

export interface HoleMapProps {
  bundle: HoleBundle | null
  tee: string
}

export function HoleMap({ bundle, tee }: HoleMapProps) {
  const container = useRef<HTMLDivElement>(null)
  const mapRef = useRef<MLMap | null>(null)
  const [map, setMap] = useState<MLMap | null>(null)
  const teeRef = useRef(tee)
  const [heatOn, setHeatOn] = useState<boolean>(readHeatOn)

  // Mount once.
  useEffect(() => {
    if (!container.current) return
    const map = new MLMap({
      container: container.current,
      style: STYLE,
      center: [0, 0],
      zoom: 15,
      maxZoom: MAX_ZOOM,
      attributionControl: false,
    })
    // bottom-right: a mouse affordance; hidden under 768 px where the user pinches
    map.addControl(new NavigationControl({ showCompass: false }), 'bottom-right')
    // top-left under the floating top bar, so the bottom sheet never covers it on a phone
    map.addControl(new AttributionControl({ compact: true }), 'top-left')
    mapRef.current = map
    setMap(map)
    return () => {
      map.remove()
      mapRef.current = null
      setMap(null)
    }
  }, [])

  // Heatmap image source: added once, then updated in place on bundle change.
  useEffect(() => {
    const map = mapRef.current
    if (!map || !bundle) return
    const apply = () => {
      const url = heatmapDataUrl(bundle)
      const coordinates = gridCorners(bundle.meta)
      const heat = map.getSource('heat') as ImageSource | undefined
      if (heat) {
        heat.updateImage({ url, coordinates })
      } else {
        map.addSource('heat', { type: 'image', url, coordinates })
        map.addLayer({
          id: 'heat',
          type: 'raster',
          source: 'heat',
          paint: { 'raster-opacity': HEAT_OPACITY, 'raster-resampling': 'nearest' },
        })
      }
      const polys = polygonFeatures(bundle.meta)
      const polySource = map.getSource('polys') as GeoJSONSource | undefined
      if (polySource) {
        polySource.setData(polys)
      } else {
        const fill = fillColour()
        map.addSource('polys', { type: 'geojson', data: polys })
        map.addLayer({
          id: 'polys-fill',
          type: 'fill',
          source: 'polys',
          paint: { 'fill-color': fill, 'fill-opacity': TERRAIN_FILL_OPACITY },
        })
        map.addLayer({
          id: 'polys-line',
          type: 'line',
          source: 'polys',
          paint: { 'line-color': fill, 'line-width': 1, 'line-opacity': 0.9 },
        })
      }
      if (!map.getSource('marks')) {
        map.addSource('marks', { type: 'geojson', data: markerFeatures(bundle.meta, teeRef.current) })
        map.addLayer({
          id: 'marks',
          type: 'circle',
          source: 'marks',
          paint: {
            'circle-radius': ['match', ['get', 'kind'], 'pin', 7, 5],
            'circle-color': ['match', ['get', 'kind'], 'pin', token('--pin'), token('--t-tee')],
            'circle-stroke-color': ['match', ['get', 'kind'], 'pin', token('--color-surface-2'), token('--color-ink')],
            'circle-stroke-width': 2,
          },
        })
      }
      fitToGrid(map, bundle.meta)
    }
    return whenStyleReady(map, apply)
  }, [bundle])

  // Heatmap on or off: remembered per device (docs/design.md section 9).
  useEffect(() => {
    try {
      localStorage.setItem(HEAT_KEY, heatOn ? 'on' : 'off')
    } catch {
      /* private mode */
    }
    const map = mapRef.current
    if (!map) return
    return whenStyleReady(map, () => {
      if (map.getLayer('heat')) map.setLayoutProperty('heat', 'visibility', heatOn ? 'visible' : 'none')
    })
  }, [heatOn, bundle])

  // Pin and the selected tee.
  useEffect(() => {
    teeRef.current = tee
    const map = mapRef.current
    if (!map || !bundle) return
    const apply = () => {
      const marks = map.getSource('marks') as GeoJSONSource | undefined
      marks?.setData(markerFeatures(bundle.meta, tee))
    }
    return whenStyleReady(map, apply)
  }, [bundle, tee])

  return (
    <div ref={container} className="h-full w-full">
      {map && <BallMarker map={map} />}
      {map && <AimArrow map={map} />}
      {map && <PlayItOutLayer map={map} />}
      {map && <MapLabels map={map} />}
      <div className="absolute top-16 right-2 z-10 flex flex-col gap-2 safe-top">
        <MapButton
          label={heatOn ? 'Hide strokes-to-go heatmap' : 'Show strokes-to-go heatmap'}
          pressed={heatOn}
          onClick={() => setHeatOn((v) => !v)}
        >
          <svg viewBox="0 0 24 24" width="22" height="22" fill="none" stroke="currentColor" strokeWidth="2" strokeLinejoin="round" aria-hidden="true">
            <path d="M12 3 2 8l10 5 10-5-10-5Z" />
            <path d="m2 12 10 5 10-5" />
            <path d="m2 16 10 5 10-5" />
          </svg>
        </MapButton>
        <MapButton label="Recenter on the hole" onClick={() => bundle && map && fitToGrid(map, bundle.meta)}>
          <svg viewBox="0 0 24 24" width="22" height="22" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" aria-hidden="true">
            <circle cx="12" cy="12" r="7" />
            <path d="M12 2v4M12 18v4M2 12h4M18 12h4" />
          </svg>
        </MapButton>
      </div>
    </div>
  )
}
