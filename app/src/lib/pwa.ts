/**
 * Service worker settings for vite-plugin-pwa (part 14). Kept here, not in vite.config.ts,
 * so the caching rules are unit-tested. The manifest is the static file in `public/`.
 */
import type { VitePWAOptions } from 'vite-plugin-pwa'

export const ESRI_TILE_PATTERN =
  /^https:\/\/server\.arcgisonline\.com\/ArcGIS\/rest\/services\/World_Imagery\/MapServer\/tile\//
export const TILE_CACHE = 'esri-tiles'
const FONT_PATTERN = /^https:\/\/fonts\.(googleapis|gstatic)\.com\//

export const pwaOptions: Partial<VitePWAOptions> = {
  registerType: 'autoUpdate',
  manifest: false,
  workbox: {
    // The app shell plus everything the solver exports under public/data.
    globPatterns: ['**/*.{js,css,html,json,u8,f32,png,webmanifest}'],
    maximumFileSizeToCacheInBytes: 5 * 1024 * 1024,
    runtimeCaching: [
      {
        urlPattern: ESRI_TILE_PATTERN,
        handler: 'CacheFirst',
        options: {
          cacheName: TILE_CACHE,
          expiration: { maxEntries: 500, maxAgeSeconds: 30 * 24 * 60 * 60 },
          cacheableResponse: { statuses: [0, 200] },
        },
      },
      {
        urlPattern: FONT_PATTERN,
        handler: 'StaleWhileRevalidate',
        options: { cacheName: 'fonts', cacheableResponse: { statuses: [0, 200] } },
      },
    ],
  },
}
