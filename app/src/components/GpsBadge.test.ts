import { describe, expect, it } from 'vitest'

import { gridToLonLat, metresBetween } from '../lib/geo'
import { readToyBundle } from '../lib/toyFiles'
import { accuracyRing, CIRCLE_POINTS, gpsLabel, gpsProblemText } from './GpsBadge'

describe('accuracyRing', () => {
  const meta = readToyBundle().meta
  it('is a closed 32 point ring whose radius is accuracy_m in meters on the map', () => {
    const gps = { x: 22, y: 13, accuracy_m: 8 }
    const ring = accuracyRing(meta, gps)
    expect(CIRCLE_POINTS).toBe(32)
    expect(ring).toHaveLength(CIRCLE_POINTS + 1)
    expect(ring[0]).toEqual(ring[CIRCLE_POINTS])
    const centre = gridToLonLat(meta, gps)
    for (const [lon, lat] of ring) expect(metresBetween(centre, { lon, lat })).toBeCloseTo(8, 2)
  })
})

describe('gpsLabel', () => {
  const off = { enabled: false, error: null, outside: false }
  it('covers off, waiting, fix, outside and error', () => {
    expect(gpsLabel(off, null)).toBe('GPS off')
    expect(gpsLabel({ ...off, enabled: true }, null)).toBe('GPS: finding you')
    expect(gpsLabel({ ...off, enabled: true }, { x: 1, y: 1, accuracy_m: 4.6 })).toBe('GPS ±5 m')
    expect(gpsLabel({ ...off, enabled: true, outside: true }, null)).toBe('GPS: you are off this hole')
    expect(gpsLabel({ ...off, enabled: true, error: 'User denied Geolocation' }, null)).toBe(
      'GPS: User denied Geolocation',
    )
  })
})

describe('gpsProblemText (part 21)', () => {
  it('tells a refused permission apart from a fix that will not come', () => {
    expect(gpsProblemText('User denied Geolocation')).toBe(
      'Location is turned off for this site. Allow it in your browser settings, then try again.',
    )
    expect(gpsProblemText('Permission denied')).toMatch(/^Location is turned off/)
    expect(gpsProblemText('Timeout expired')).toBe('Cannot find you yet: Timeout expired.')
    expect(gpsProblemText('This browser has no location service')).toBe('Cannot find you yet: This browser has no location service.')
  })
})
