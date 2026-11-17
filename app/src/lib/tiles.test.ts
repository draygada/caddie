import { describe, expect, it } from 'vitest'

import { gridCorners } from './geo'
import { PREWARM_ZOOMS, prewarmTiles, tilesForGrid, tileUrl, tileXY } from './tiles'
import { ESRI_TILE_PATTERN } from './pwa'
import { readToyBundle } from './toyFiles'

describe('tileXY', () => {
  it('follows the slippy map scheme', () => {
    expect(tileXY(0, 0, 0)).toEqual({ x: 0, y: 0 })
    expect(tileXY(0.1, -0.1, 1)).toEqual({ x: 1, y: 1 })
    expect(tileXY(-122.18, 37.42, 16)).toEqual({ x: 10525, y: 25412 })
  })
})

describe('tilesForGrid', () => {
  const meta = readToyBundle().meta
  it('covers every grid corner at zooms 16 to 18 with Esri URLs in z/y/x order', () => {
    expect(PREWARM_ZOOMS).toEqual([16, 17, 18])
    const urls = tilesForGrid(meta)
    expect(new Set(urls).size).toBe(urls.length)
    for (const u of urls) expect(ESRI_TILE_PATTERN.test(u)).toBe(true)
    for (const z of PREWARM_ZOOMS)
      for (const [lon, lat] of gridCorners(meta)) {
        const { x, y } = tileXY(lon, lat, z)
        expect(urls).toContain(tileUrl(z, x, y))
      }
    expect(tileUrl(17, 3, 5).endsWith('/tile/17/5/3')).toBe(true)
  })
})

describe('prewarmTiles', () => {
  const meta = readToyBundle().meta
  it('requests every tile once, survives failures, and skips a hole it already warmed', async () => {
    const seen: string[] = []
    const fetcher = (url: string) => {
      seen.push(url)
      return seen.length === 2 ? Promise.reject(new Error('offline')) : Promise.resolve()
    }
    const n = await prewarmTiles(meta, fetcher)
    expect(n).toBe(tilesForGrid(meta).length)
    expect(seen.sort()).toEqual(tilesForGrid(meta).sort())
    expect(await prewarmTiles(meta, fetcher)).toBe(0)
  })
})
