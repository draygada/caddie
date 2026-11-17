/**
 * Live position (part 14). `startGps` is the whole behaviour and takes the geolocation
 * object as an argument so tests can drive it; `useGps` is the React wrapper around it.
 *
 * Fixes are written to `store.gps` in grid meters. The ball follows `store.gps` through
 * the effect `BallMarker` has had since part 11, so this module never calls `setBall`.
 */
import { useEffect } from 'react'
import { create } from 'zustand'

import { lonLatToGrid } from '../lib/geo'
import type { Meta, XY } from '../lib/types'
import { useStore } from '../store'

export const GPS_OPTIONS = { enableHighAccuracy: true, maximumAge: 2000, timeout: 10000 } as const
/** After the player moves the ball by hand, fixes are held back for this long. */
export const GPS_HOLD_MS = 10_000
/** Fixes closer than this to the last written one are jitter and are dropped. */
export const MIN_MOVE_M = 2

interface FixLike {
  coords: { longitude: number; latitude: number; accuracy: number }
}

/** The part of `navigator.geolocation` this module uses. */
export interface GeoLike {
  watchPosition(
    success: (p: FixLike) => void,
    error: (e: { message: string }) => void,
    options: typeof GPS_OPTIONS,
  ): number
  clearWatch(id: number): void
}

export interface GpsStatus {
  enabled: boolean
  /** The browser's error text (permission denied, timeout), null when fixes are flowing. */
  error: string | null
  /** The last fix was off the hole's grid. */
  outside: boolean
}

/** What `GpsBadge` shows. Separate from the main store, whose shape is fixed in part 11. */
export const useGpsStatus = create<GpsStatus>()(() => ({ enabled: false, error: null, outside: false }))

function insideGrid(meta: Meta, p: XY): boolean {
  return p.x >= 0 && p.y >= 0 && p.x < meta.cols * meta.cell_m && p.y < meta.rows * meta.cell_m
}

/**
 * Start watching; returns the stop function.
 *
 * Follow rule: any ball change that is not the ball landing on the last written fix is a
 * manual move (a tap or a drag), and for `GPS_HOLD_MS` after it no fix is written, so
 * `BallMarker` has nothing to follow. A fix off the grid clears `gps` and leaves the ball.
 */
export function startGps(geo: GeoLike): () => void {
  useStore.getState().setUseWorker(true)
  useGpsStatus.setState({ enabled: true, error: null, outside: false })

  let manualAt = -Infinity
  let written: XY | null = null
  const unsubscribe = useStore.subscribe((s, prev) => {
    if (s.ball === prev.ball || !s.ball) return
    if (written && s.ball.x === written.x && s.ball.y === written.y) return
    manualAt = Date.now()
  })

  const onFix = (p: FixLike) => {
    const { bundle, gps, setGps } = useStore.getState()
    if (!bundle) return
    const xy = lonLatToGrid(bundle.meta, p.coords.longitude, p.coords.latitude)
    if (!insideGrid(bundle.meta, xy)) {
      written = null
      if (gps) setGps(null)
      useGpsStatus.setState({ error: null, outside: true })
      return
    }
    useGpsStatus.setState({ error: null, outside: false })
    if (Date.now() - manualAt < GPS_HOLD_MS) return
    const accuracy_m = p.coords.accuracy
    if (gps && gps.accuracy_m === accuracy_m && Math.hypot(xy.x - gps.x, xy.y - gps.y) < MIN_MOVE_M) return
    // Keep the old position when only the accuracy changed, so the ball does not twitch.
    const at = gps && Math.hypot(xy.x - gps.x, xy.y - gps.y) < MIN_MOVE_M ? { x: gps.x, y: gps.y } : xy
    written = at
    setGps({ ...at, accuracy_m })
  }
  const onError = (e: { message: string }) => {
    useStore.getState().setGps(null)
    useGpsStatus.setState({ error: e.message || 'Location unavailable' })
  }

  const id = geo.watchPosition(onFix, onError, GPS_OPTIONS)
  return () => {
    unsubscribe()
    geo.clearWatch(id)
    useStore.getState().setGps(null)
    useStore.getState().setUseWorker(false)
    useGpsStatus.setState({ enabled: false, error: null, outside: false })
  }
}

/** Watch the device position while `enabled`. */
export function useGps(enabled: boolean): void {
  useEffect(() => {
    if (!enabled) return
    if (typeof navigator === 'undefined' || !navigator.geolocation) {
      useGpsStatus.setState({ enabled: false, error: 'This browser has no location service' })
      return
    }
    return startGps(navigator.geolocation)
  }, [enabled])
}
