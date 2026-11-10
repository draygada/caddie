/**
 * Satellite map of the hole with the strokes-to-go heatmap and the hole polygons.
 * Until the store exists (part 11) the bundle comes in as a prop from App.
 */
import {
  type ImageSource,
  Map as MLMap,
  NavigationControl,
  setWorkerUrl,
  type StyleSpecification,
} from 'maplibre-gl'
import 'maplibre-gl/dist/maplibre-gl.css'
import workerUrl from 'maplibre-gl/dist/maplibre-gl-worker.mjs?url'
import { useEffect, useRef } from 'react'

import { gridCorners } from '../lib/geo'
import { heatmapDataUrl } from '../lib/heatmap'
import type { HoleBundle } from '../lib/types'

export const ESRI_TILES =
  'https://server.arcgisonline.com/ArcGIS/rest/services/World_Imagery/MapServer/tile/{z}/{y}/{x}'
export const ESRI_ATTRIBUTION = 'Esri, Maxar, Earthstar Geographics'
export const MAX_ZOOM = 19
export const HEAT_OPACITY = 0.55

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

export function HoleMap({ bundle }: HoleMapProps) {
  const container = useRef<HTMLDivElement>(null)
  const mapRef = useRef<MLMap | null>(null)

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
    return () => {
      map.remove()
      mapRef.current = null
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
      map.jumpTo({ center: [bundle.meta.origin.lon, bundle.meta.origin.lat], zoom: 16 })
    }
    if (map.isStyleLoaded()) apply()
    else map.once('load', apply)
  }, [bundle])

  return <div ref={container} className="h-full w-full" />
}
