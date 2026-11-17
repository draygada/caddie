import { afterEach, beforeEach, describe, expect, it } from 'vitest'

import { gridToLonLat } from '../lib/geo'
import { readToyBundle } from '../lib/toyFiles'
import type { XY } from '../lib/types'
import { initialState, useStore } from '../store'
import { type GeoLike, GPS_OPTIONS, startGps, useGpsStatus } from './useGps'

type Success = (p: { coords: { longitude: number; latitude: number; accuracy: number } }) => void
type Failure = (e: { message: string }) => void

/** A hand-driven `navigator.geolocation`. */
function fakeGeo() {
  let success: Success | null = null
  let failure: Failure | null = null
  let cleared = 0
  let options: unknown = null
  const geo: GeoLike = {
    watchPosition(s, f, o) {
      success = s
      failure = f
      options = o
      return 7
    },
    clearWatch(id) {
      if (id === 7) cleared += 1
    },
  }
  return {
    geo,
    fix(p: XY, accuracy = 4) {
      const { lon, lat } = gridToLonLat(useStore.getState().bundle!.meta, p)
      success!({ coords: { longitude: lon, latitude: lat, accuracy } })
    },
    fail(message: string) {
      failure!({ message })
    },
    cleared: () => cleared,
    options: () => options,
  }
}

beforeEach(() => {
  useStore.setState({ ...initialState, bundle: readToyBundle() })
  useGpsStatus.setState({ enabled: false, error: null, outside: false })
})
afterEach(() => useStore.setState(initialState))

describe('startGps', () => {
  it('watches with high accuracy and the part 14 options', () => {
    const f = fakeGeo()
    const stop = startGps(f.geo)
    expect(f.options()).toEqual(GPS_OPTIONS)
    expect(GPS_OPTIONS).toEqual({ enableHighAccuracy: true, maximumAge: 2000, timeout: 10000 })
    stop()
  })

  it('writes each fix to the store in grid meters with its accuracy', () => {
    const f = fakeGeo()
    const stop = startGps(f.geo)
    f.fix({ x: 22, y: 13 }, 6)
    const gps = useStore.getState().gps!
    expect(gps.x).toBeCloseTo(22, 3)
    expect(gps.y).toBeCloseTo(13, 3)
    expect(gps.accuracy_m).toBe(6)
    stop()
  })

  it('turns the rollout worker on while running and off when stopped', () => {
    const f = fakeGeo()
    const stop = startGps(f.geo)
    expect(useStore.getState().useWorker).toBe(true)
    expect(useGpsStatus.getState().enabled).toBe(true)
    stop()
    expect(useStore.getState().useWorker).toBe(false)
    expect(useGpsStatus.getState().enabled).toBe(false)
    expect(f.cleared()).toBe(1)
    expect(useStore.getState().gps).toBeNull()
  })

  it('on error clears gps and surfaces the message', () => {
    const f = fakeGeo()
    const stop = startGps(f.geo)
    f.fix({ x: 22, y: 13 })
    f.fail('User denied Geolocation')
    expect(useStore.getState().gps).toBeNull()
    expect(useGpsStatus.getState().error).toBe('User denied Geolocation')
    f.fix({ x: 22, y: 13 })
    expect(useGpsStatus.getState().error).toBeNull()
    stop()
  })

  it('ignores fixes until a bundle is loaded', () => {
    const f = fakeGeo()
    const meta = useStore.getState().bundle!.meta
    const { lon, lat } = gridToLonLat(meta, { x: 22, y: 13 })
    useStore.setState({ bundle: null })
    let success: Success | null = null
    const stop = startGps({ ...f.geo, watchPosition: (s) => ((success = s), 7) })
    success!({ coords: { longitude: lon, latitude: lat, accuracy: 4 } })
    expect(useStore.getState().gps).toBeNull()
    stop()
  })
})
