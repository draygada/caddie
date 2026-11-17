import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'

import { gridToLonLat } from '../lib/geo'
import { readToyBundle } from '../lib/toyFiles'
import type { XY } from '../lib/types'
import { initialState, useStore } from '../store'
import { type GeoLike, GPS_HOLD_MS, GPS_OPTIONS, MIN_MOVE_M, startGps, useGpsStatus } from './useGps'

type Success = (p: { coords: { longitude: number; latitude: number; accuracy: number } }) => void
type Failure = (e: { message: string }) => void

function must<T>(v: T | null): T {
  if (v === null) throw new Error('unexpected null')
  return v
}
const gpsNow = () => must(useStore.getState().gps)
const ballNow = () => must(useStore.getState().ball)
const metaNow = () => must(useStore.getState().bundle).meta

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
      const { lon, lat } = gridToLonLat(metaNow(), p)
      must(success)({ coords: { longitude: lon, latitude: lat, accuracy } })
    },
    fail(message: string) {
      must(failure)({ message })
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
    const gps = gpsNow()
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
    const meta = metaNow()
    const { lon, lat } = gridToLonLat(meta, { x: 22, y: 13 })
    useStore.setState({ bundle: null })
    const captured: Success[] = []
    const stop = startGps({ ...f.geo, watchPosition: (s) => (captured.push(s), 7) })
    captured[0]({ coords: { longitude: lon, latitude: lat, accuracy: 4 } })
    expect(useStore.getState().gps).toBeNull()
    stop()
  })
})

describe('follow rule', () => {
  beforeEach(() => {
    vi.useFakeTimers()
    vi.setSystemTime(1_000_000)
  })
  afterEach(() => vi.useRealTimers())

  /** What BallMarker does on every gps write: put the ball there. */
  function follow() {
    return useStore.subscribe((s, prev) => {
      if (s.gps && s.gps !== prev.gps) s.setBall({ x: s.gps.x, y: s.gps.y })
    })
  }

  it('a manual ball move blocks gps writes for 10 s, then fixes flow again', () => {
    const f = fakeGeo()
    const unfollow = follow()
    const stop = startGps(f.geo)
    f.fix({ x: 20, y: 10 })
    expect(ballNow().x).toBeCloseTo(20, 3)

    useStore.getState().setBall({ x: 30, y: 30 }) // the player drags or taps the ball
    vi.advanceTimersByTime(GPS_HOLD_MS - 1)
    f.fix({ x: 25, y: 12 })
    expect(useStore.getState().ball).toEqual({ x: 30, y: 30 })
    expect(gpsNow().x).toBeCloseTo(20, 3)

    vi.advanceTimersByTime(1)
    f.fix({ x: 25, y: 12 })
    expect(ballNow().x).toBeCloseTo(25, 3)
    stop()
    unfollow()
  })

  it('the ball following a fix does not count as a manual move', () => {
    const f = fakeGeo()
    const unfollow = follow()
    const stop = startGps(f.geo)
    f.fix({ x: 20, y: 10 })
    f.fix({ x: 25, y: 12 })
    expect(ballNow().x).toBeCloseTo(25, 3)
    stop()
    unfollow()
  })

  it('a fix off the grid clears gps, leaves the ball, and flags outside', () => {
    const f = fakeGeo()
    const unfollow = follow()
    const stop = startGps(f.geo)
    f.fix({ x: 20, y: 10 })
    f.fix({ x: -40, y: 10 })
    expect(useStore.getState().gps).toBeNull()
    expect(ballNow().x).toBeCloseTo(20, 3)
    expect(useGpsStatus.getState().outside).toBe(true)
    f.fix({ x: 21, y: 30 })
    expect(useGpsStatus.getState().outside).toBe(false)
    expect(gpsNow().y).toBeCloseTo(30, 3)
    stop()
    unfollow()
  })

  it('ignores jitter under MIN_MOVE_M unless the accuracy changed', () => {
    const f = fakeGeo()
    const stop = startGps(f.geo)
    f.fix({ x: 20, y: 10 }, 5)
    const first = useStore.getState().gps
    f.fix({ x: 20 + MIN_MOVE_M / 2, y: 10 }, 5)
    expect(useStore.getState().gps).toBe(first)
    f.fix({ x: 20 + MIN_MOVE_M / 2, y: 10 }, 9)
    expect(gpsNow().accuracy_m).toBe(9)
    f.fix({ x: 20 + MIN_MOVE_M * 2, y: 10 }, 9)
    expect(gpsNow().x).toBeCloseTo(20 + MIN_MOVE_M * 2, 3)
    stop()
  })
})
