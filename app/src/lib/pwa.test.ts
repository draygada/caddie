import { readFileSync } from 'node:fs'
import { join } from 'node:path'

import { describe, expect, it } from 'vitest'

import { ESRI_TILE_PATTERN, pwaOptions, TILE_CACHE } from './pwa'
import { DATA_DIR } from './toyFiles'

describe('pwaOptions', () => {
  it('auto-updates and precaches the shell and the solver data', () => {
    expect(pwaOptions.registerType).toBe('autoUpdate')
    const globs = pwaOptions.workbox?.globPatterns ?? []
    for (const ext of ['js', 'css', 'html', 'json', 'u8', 'f32', 'png'])
      expect(globs.some((g) => g.includes(ext))).toBe(true)
  })

  it('caches Esri tiles cache-first, 500 entries, 30 days', () => {
    const rule = pwaOptions.workbox?.runtimeCaching?.find((r) => r.options?.cacheName === TILE_CACHE)
    expect(rule?.handler).toBe('CacheFirst')
    expect(rule?.options?.expiration).toEqual({ maxEntries: 500, maxAgeSeconds: 30 * 24 * 60 * 60 })
    const url = 'https://server.arcgisonline.com/ArcGIS/rest/services/World_Imagery/MapServer/tile/17/50712/21011'
    expect(ESRI_TILE_PATTERN.test(url)).toBe(true)
    expect(ESRI_TILE_PATTERN.test('https://example.com/tile/17/1/2')).toBe(false)
  })
})

describe('manifest.webmanifest', () => {
  it('is installable: name, standalone, portrait, 192 and 512 icons that exist', () => {
    const pub = join(DATA_DIR, '..')
    const m = JSON.parse(readFileSync(join(pub, 'manifest.webmanifest'), 'utf8')) as {
      name: string
      display: string
      orientation: string
      start_url: string
      icons: { src: string; sizes: string }[]
    }
    expect(m.name).toBe('Caddie')
    expect(m.display).toBe('standalone')
    expect(m.orientation).toBe('portrait')
    expect(m.start_url).toBe('/')
    expect(m.icons.map((i) => i.sizes).sort()).toEqual(['192x192', '512x512'])
    for (const icon of m.icons) expect(readFileSync(join(pub, icon.src)).length).toBeGreaterThan(500)
  })
})
