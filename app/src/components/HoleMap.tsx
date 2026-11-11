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
import { useEffect, useRef, useState } from 'react'

import { AimArrow } from './AimArrow'
import { BallMarker } from './BallMarker'
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
export const FIT_PADDING_PX = 40

/** Bearing = hole bearing, so +y points up the screen, then fit the rotated grid. */
export function fitToGrid(map: MLMap, meta: Meta): void {
  const bounds = new LngLatBounds()
  for (const [lon, lat] of gridCorners(meta)) bounds.extend([lon, lat])
  map.setBearing(meta.rotation_deg)
  map.fitBounds(bounds, { padding: FIT_PADDING_PX, bearing: meta.rotation_deg, duration: 0 })
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

export interface HoleMapProps {
  bundle: HoleBundle | null
  tee: string
}

export function HoleMap({ bundle, tee }: HoleMapProps) {
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
    map.addControl(new NavigationControl({ showCompass: false }), 'top-right')
    // top-left so the bottom sheet never covers it on a phone
    map.addControl(new AttributionControl({ compact: false }), 'top-left')
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
    </div>
  )
}
