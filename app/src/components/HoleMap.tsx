/**
 * Satellite map of the hole with the strokes-to-go heatmap and the hole polygons.
 * Until the store exists (part 11) the bundle comes in as a prop from App.
 */
import {
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

import { BallMarker } from './BallMarker'

import { gridCorners, gridToLonLat } from '../lib/geo'
import { heatmapDataUrl } from '../lib/heatmap'
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

/** Fill colour per polygon kind, drawn at low opacity over the imagery. */
export const LIE_COLOURS: Record<string, string> = {
  fairway: '#7ccd5a',
  rough: '#4f7d3a',
  green: '#b8f28b',
  bunker: '#f1d58b',
  water: '#3b82f6',
  ob: '#ef4444',
  tee: '#e2e8f0',
}
const POLYGON_KINDS = Object.keys(LIE_COLOURS)

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
  const expr: unknown[] = ['match', ['get', 'kind']]
  for (const k of POLYGON_KINDS) expr.push(k, LIE_COLOURS[k])
  expr.push('#ffffff')
  return expr as ExpressionSpecification
}
const FILL_COLOUR = fillColour()

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
      attributionControl: { compact: false },
    })
    map.addControl(new NavigationControl({ showCompass: true }), 'top-right')
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
        map.addSource('polys', { type: 'geojson', data: polys })
        map.addLayer({
          id: 'polys-fill',
          type: 'fill',
          source: 'polys',
          paint: { 'fill-color': FILL_COLOUR, 'fill-opacity': 0.18 },
        })
        map.addLayer({
          id: 'polys-line',
          type: 'line',
          source: 'polys',
          paint: { 'line-color': FILL_COLOUR, 'line-width': 1, 'line-opacity': 0.9 },
        })
      }
      if (!map.getSource('marks')) {
        map.addSource('marks', { type: 'geojson', data: markerFeatures(bundle.meta, teeRef.current) })
        map.addLayer({
          id: 'marks',
          type: 'circle',
          source: 'marks',
          paint: {
            'circle-radius': 6,
            'circle-color': ['match', ['get', 'kind'], 'pin', '#facc15', '#ffffff'],
            'circle-stroke-color': '#0f172a',
            'circle-stroke-width': 2,
          },
        })
      }
      fitToGrid(map, bundle.meta)
    }
    if (map.isStyleLoaded()) apply()
    else map.once('load', apply)
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
    if (map.isStyleLoaded()) apply()
    else map.once('load', apply)
  }, [bundle, tee])

  return (
    <div ref={container} className="h-full w-full">
      {map && <BallMarker map={map} />}
    </div>
  )
}
