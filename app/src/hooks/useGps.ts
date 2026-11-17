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
import { useStore } from '../store'

export const GPS_OPTIONS = { enableHighAccuracy: true, maximumAge: 2000, timeout: 10000 } as const

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

/** Start watching; returns the stop function. */
export function startGps(geo: GeoLike): () => void {
  useStore.getState().setUseWorker(true)
  useGpsStatus.setState({ enabled: true, error: null, outside: false })

  const onFix = (p: FixLike) => {
    const { bundle, setGps } = useStore.getState()
    if (!bundle) return
    const xy = lonLatToGrid(bundle.meta, p.coords.longitude, p.coords.latitude)
    useGpsStatus.setState({ error: null })
    setGps({ ...xy, accuracy_m: p.coords.accuracy })
  }
  const onError = (e: { message: string }) => {
    useStore.getState().setGps(null)
    useGpsStatus.setState({ error: e.message || 'Location unavailable' })
  }

  const id = geo.watchPosition(onFix, onError, GPS_OPTIONS)
  return () => {
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
