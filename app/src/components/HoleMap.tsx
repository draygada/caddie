/**
 * Satellite map of the hole with the hole polygons. The strokes-to-go heatmap was removed
 * from the app in part 21.
 * Until the store exists (part 11) the bundle comes in as a prop from App.
 */
import {
  AttributionControl,
  type ExpressionSpecification,
  type GeoJSONSource,
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
import { GpsLayer } from './GpsBadge'
import { MapLabels } from './MapLabels'
import { PlayItOutLayer } from './PlayItOut'
import { ShotLogLayer } from './ShotLogger'

import { frameZoom, gridToLonLat, holeFrame } from '../lib/geo'
import { whenStyleReady } from '../lib/mapReady'
import { token } from '../lib/tokens'
import type { HoleBundle, Meta, XY } from '../lib/types'

export const ESRI_TILES =
  'https://server.arcgisonline.com/ArcGIS/rest/services/World_Imagery/MapServer/tile/{z}/{y}/{x}'
export const ESRI_ATTRIBUTION = 'Esri, Maxar, Earthstar Geographics'
export const MAX_ZOOM = 19
export const FIT_PADDING_PX = 24

/** Fallback for the bottom sheet height on a phone, used until the sheet has rendered. */
export const SHEET_PADDING_PX = 270
/** Room at the top for the map button and the attribution; there is no top bar since part 21. */
export const TOP_BAR_PADDING_PX = 40

function isPhone(): boolean {
  return typeof window !== 'undefined' && window.matchMedia('(max-width: 767px)').matches
}

/** Height of the bottom sheet as it is on screen now, or the fallback before it has rendered. */
function sheetHeightPx(): number {
  if (typeof document === 'undefined') return SHEET_PADDING_PX
  let h = 0
  for (const el of document.querySelectorAll('section[aria-label="Caddie"]')) h = Math.max(h, el.getBoundingClientRect().height)
  return h > 0 ? h + FIT_PADDING_PX : SHEET_PADDING_PX
}

/** Padding that keeps the fitted hole clear of the map button and the sheet. */
export function fitPadding(): { top: number; bottom: number; left: number; right: number } {
  return {
    top: TOP_BAR_PADDING_PX,
    bottom: isPhone() ? sheetHeightPx() : FIT_PADDING_PX,
    left: FIT_PADDING_PX,
    right: FIT_PADDING_PX,
  }
}

/**
 * Bearing = hole bearing, so +y points up the screen, then fit the hole itself (tees, fairway,
 * green and pin with a margin), not the whole grid with its wide rough margins.
 */
export function fitToGrid(map: MLMap, meta: Meta): void {
  const f = holeFrame(meta)
  const padding = fitPadding()
  const box = map.getContainer()
  const availW = box.clientWidth - padding.left - padding.right
  const availH = box.clientHeight - padding.top - padding.bottom
  const { lon, lat } = gridToLonLat(meta, { x: (f.x0 + f.x1) / 2, y: (f.y0 + f.y1) / 2 })
  const zoom = Math.min(MAX_ZOOM, frameZoom(f.x1 - f.x0, f.y1 - f.y0, availW, availH, lat))
  // `padding` puts the centre in the middle of the space the top bar and the sheet leave free.
  map.jumpTo({ center: [lon, lat], zoom, bearing: meta.rotation_deg, padding })
}

/** Polygon kinds in draw order; colours come from the --t-* tokens (docs/design.md). */
const POLYGON_KINDS = ['fairway', 'rough', 'green', 'bunker', 'water', 'ob', 'tee']
export function lieColours(): Record<string, string> {
  return Object.fromEntries(POLYGON_KINDS.map((k) => [k, token(`--t-${k}`)]))
}
/** Terrain fills never exceed 35 percent; 25 keeps fairway edges legible. */
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
  /** Part 21: which layers this mode carries. */
  parts?: { logger: boolean; playItOut: boolean; gps: boolean }
}

const ALL_PARTS = { logger: true, playItOut: true, gps: true }

export function HoleMap({ bundle, tee, parts = ALL_PARTS }: HoleMapProps) {
  const container = useRef<HTMLDivElement>(null)
  const mapRef = useRef<MLMap | null>(null)
  const [map, setMap] = useState<MLMap | null>(null)
  const teeRef = useRef(tee)

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
    // top-left, so the bottom sheet never covers it on a phone
    map.addControl(new AttributionControl({ compact: true }), 'top-left')
    mapRef.current = map
    setMap(map)
    return () => {
      map.remove()
      mapRef.current = null
      setMap(null)
    }
  }, [])

  // Terrain outlines and the tee and pin marks: added once, then updated on bundle change.
  useEffect(() => {
    const map = mapRef.current
    if (!map || !bundle) return
    const apply = () => {
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
      {map && parts.playItOut && <PlayItOutLayer map={map} />}
      {map && parts.logger && <ShotLogLayer map={map} />}
      {map && parts.gps && <GpsLayer map={map} />}
      {map && <MapLabels map={map} />}
      <div className="absolute top-2 right-2 z-10 flex flex-col gap-2 safe-top">
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
