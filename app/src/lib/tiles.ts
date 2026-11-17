/**
 * Tile pre-warm (part 14): fetch the satellite tiles covering a hole at the zooms the
 * player uses on the course, so the service worker has them cached before the signal
 * drops. Roughly 100 to 200 tiles per hole.
 */
import { gridCorners } from './geo'
import type { Meta } from './types'

export const ESRI_TILE_BASE =
  'https://server.arcgisonline.com/ArcGIS/rest/services/World_Imagery/MapServer/tile'
export const PREWARM_ZOOMS = [16, 17, 18] as const
const CONCURRENCY = 6

/** Slippy-map tile containing a lon/lat at zoom `z`. */
export function tileXY(lon: number, lat: number, z: number): { x: number; y: number } {
  const n = 2 ** z
  const rad = (lat * Math.PI) / 180
  const x = Math.floor(((lon + 180) / 360) * n)
  const y = Math.floor(((1 - Math.log(Math.tan(rad) + 1 / Math.cos(rad)) / Math.PI) / 2) * n)
  return { x: Math.min(n - 1, Math.max(0, x)), y: Math.min(n - 1, Math.max(0, y)) }
}

/** Esri's path order is z/y/x. */
export function tileUrl(z: number, x: number, y: number): string {
  return `${ESRI_TILE_BASE}/${z}/${y}/${x}`
}

/** Every tile URL in the bounding box of the grid corners, at each zoom. */
export function tilesForGrid(meta: Meta, zooms: readonly number[] = PREWARM_ZOOMS): string[] {
  const corners = gridCorners(meta)
  const urls: string[] = []
  for (const z of zooms) {
    const t = corners.map(([lon, lat]) => tileXY(lon, lat, z))
    const x0 = Math.min(...t.map((p) => p.x))
    const x1 = Math.max(...t.map((p) => p.x))
    const y0 = Math.min(...t.map((p) => p.y))
    const y1 = Math.max(...t.map((p) => p.y))
    for (let x = x0; x <= x1; x++) for (let y = y0; y <= y1; y++) urls.push(tileUrl(z, x, y))
  }
  return urls
}

const warmed = new Set<string>()

/**
 * Request every tile for the hole, a few at a time. Failures are ignored (the map will
 * ask again when it needs the tile). Returns how many requests were made; 0 when this
 * hole was already warmed in this session.
 */
export async function prewarmTiles(
  meta: Meta,
  fetcher: (url: string) => Promise<unknown> = (url) => fetch(url, { mode: 'cors' }),
): Promise<number> {
  const key = `${String(meta.hole)}:${meta.origin.lat},${meta.origin.lon}`
  if (warmed.has(key)) return 0
  warmed.add(key)
  const urls = tilesForGrid(meta)
  let next = 0
  const run = async () => {
    while (next < urls.length) {
      const url = urls[next++]
      try {
        await fetcher(url)
      } catch {
        /* offline or blocked: skip */
      }
    }
  }
  await Promise.all(Array.from({ length: Math.min(CONCURRENCY, urls.length) }, run))
  return urls.length
}
