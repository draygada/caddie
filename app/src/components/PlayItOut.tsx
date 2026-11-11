/**
 * Play it out: one animated sequence from the current ball under the grid policy, its
 * score, then a histogram of 1,000 simulated scores. `PlayItOut` is the control in the
 * caddie panel; `PlayItOutLayer` draws the hopping ball and the dashed path on the map.
 * The two share a small module store so no part 11 store field is needed.
 */
import type { GeoJSONSource, Map as MLMap } from 'maplibre-gl'
import { Marker } from 'maplibre-gl'
import { useEffect, useRef, useSyncExternalStore } from 'react'

import { gridToLonLat } from '../lib/geo'
import { lieAt } from '../lib/grid'
import { mulberry32 } from '../lib/rng'
import {
  animationPosition,
  blowUpShare,
  histogram,
  histogramBins,
  histogramMean,
  MS_PER_SHOT,
  playOut,
  type Shot,
} from '../lib/simulate'
import type { Meta } from '../lib/types'
import { useStore } from '../store'

export const HISTOGRAM_RUNS = 1000
export const PATH_COLOUR = '#f472b6'

// --- shared animation state ---------------------------------------------------------------------

export interface PlayState {
  shots: Shot[]
  strokes: number | null
  startedAt: number | null
  /** elapsed ms when the animation finished, or null while running */
  finishedAt: number | null
  histogram: Map<number, number> | null
}

const idle: PlayState = { shots: [], strokes: null, startedAt: null, finishedAt: null, histogram: null }
let state: PlayState = idle
const listeners = new Set<() => void>()

function setPlayState(next: PlayState): void {
  state = next
  for (const l of listeners) l()
}

function subscribe(l: () => void): () => void {
  listeners.add(l)
  return () => listeners.delete(l)
}

export function usePlayState(): PlayState {
  return useSyncExternalStore(subscribe, () => state)
}

export function resetPlay(): void {
  setPlayState(idle)
}

/** Simulate one sequence from the store's ball and start the animation. */
export function startPlay(): void {
  const { bundle, player, ball, lieOverride, mode } = useStore.getState()
  if (!bundle || !player || !ball) return
  const lie = lieOverride ?? lieAt(bundle, ball)
  if (lie < 1 || lie > 5) return
  const seed = (Date.now() % 2147483647) >>> 0
  const result = playOut(bundle, player, ball, lie, mode, mulberry32(seed))
  setPlayState({ shots: result.shots, strokes: result.strokes, startedAt: performance.now(), finishedAt: null, histogram: null })
}

function finishPlay(): void {
  const { bundle, player, ball, lieOverride, mode } = useStore.getState()
  let h: Map<number, number> | null = null
  if (bundle && player && ball) {
    const lie = lieOverride ?? lieAt(bundle, ball)
    if (lie >= 1 && lie <= 5) h = histogram(bundle, player, ball, lie, mode, HISTOGRAM_RUNS, 7)
  }
  setPlayState({ ...state, finishedAt: performance.now(), histogram: h })
}

// --- map layer: hopping ball and dashed path --------------------------------------------------------

function pathFeatures(meta: Meta, shots: Shot[], upTo: number, head: { x: number; y: number } | null) {
  const coords: [number, number][] = []
  const push = (p: { x: number; y: number }) => {
    const { lon, lat } = gridToLonLat(meta, p)
    coords.push([lon, lat])
  }
  if (shots.length > 0 && upTo >= 0) {
    push(shots[0].from)
    for (let k = 0; k < upTo; k++) push(shots[k].to)
    if (head) push(head)
  }
  return {
    type: 'FeatureCollection' as const,
    features:
      coords.length >= 2
        ? [{ type: 'Feature' as const, properties: {}, geometry: { type: 'LineString' as const, coordinates: coords } }]
        : [],
  }
}

export function PlayItOutLayer({ map }: { map: MLMap }) {
  const play = usePlayState()
  const bundle = useStore((s) => s.bundle)
  const markerRef = useRef<Marker | null>(null)
  const frameRef = useRef(0)

  useEffect(() => {
    const ensureSource = () => {
      if (map.getSource('play-path')) return
      map.addSource('play-path', { type: 'geojson', data: { type: 'FeatureCollection', features: [] } })
      map.addLayer({
        id: 'play-path',
        type: 'line',
        source: 'play-path',
        paint: { 'line-color': PATH_COLOUR, 'line-width': 2, 'line-dasharray': [2, 2] },
      })
    }
    const clear = () => {
      markerRef.current?.remove()
      markerRef.current = null
      const src = map.getSource('play-path') as GeoJSONSource | undefined
      src?.setData({ type: 'FeatureCollection', features: [] })
    }
    if (!bundle || play.startedAt === null) {
      cancelAnimationFrame(frameRef.current)
      if (map.isStyleLoaded()) clear()
      return
    }
    const meta = bundle.meta
    const startedAt = play.startedAt
    const shots = play.shots
    const tick = () => {
      if (!map.isStyleLoaded()) {
        frameRef.current = requestAnimationFrame(tick)
        return
      }
      ensureSource()
      const frame = animationPosition(shots, performance.now() - startedAt, MS_PER_SHOT)
      const src = map.getSource('play-path') as GeoJSONSource | undefined
      src?.setData(pathFeatures(meta, shots, frame.index, frame.pos))
      if (frame.pos) {
        const { lon, lat } = gridToLonLat(meta, frame.pos)
        if (!markerRef.current) markerRef.current = new Marker({ color: PATH_COLOUR, scale: 0.8 }).setLngLat([lon, lat]).addTo(map)
        else markerRef.current.setLngLat([lon, lat])
      }
      if (frame.done) {
        if (play.finishedAt === null) finishPlay()
        return
      }
      frameRef.current = requestAnimationFrame(tick)
    }
    frameRef.current = requestAnimationFrame(tick)
    return () => cancelAnimationFrame(frameRef.current)
  }, [map, bundle, play.startedAt, play.shots, play.finishedAt])

  useEffect(
    () => () => {
      markerRef.current?.remove()
      markerRef.current = null
    },
    [],
  )

  return null
}

// --- panel control: button, score, histogram ---------------------------------------------------------

export function PlayItOut() {
  const play = usePlayState()
  const bundle = useStore((s) => s.bundle)
  const ball = useStore((s) => s.ball)
  const recommendation = useStore((s) => s.recommendation)
  const running = play.startedAt !== null && play.finishedAt === null
  const canPlay = Boolean(bundle && ball && recommendation) && !running
  const par = bundle?.meta.par ?? 4
  const bins = play.histogram ? histogramBins(play.histogram, par) : null
  const maxCount = bins ? Math.max(1, ...bins.map((b) => b.count)) : 1
  const mean = play.histogram ? histogramMean(play.histogram) : null
  const blowUp = play.histogram ? blowUpShare(play.histogram, par) : null

  // clear a stale play-out when the ball or bundle changes
  useEffect(() => {
    resetPlay()
  }, [ball, bundle])

  return (
    <div className="mt-2 flex flex-col gap-2 border-t border-slate-700 pt-2" data-testid="play-it-out">
      <div className="flex gap-2">
        <button
          type="button"
          className="rounded bg-pink-500 px-3 py-1 text-sm font-medium text-slate-900 disabled:opacity-40"
          disabled={!canPlay}
          onClick={startPlay}
        >
          {running ? 'Playing...' : play.strokes === null ? 'Play it out' : 'Play it out again'}
        </button>
        {play.strokes !== null && (
          <button
            type="button"
            className="rounded bg-slate-700 px-3 py-1 text-sm text-slate-200 hover:bg-slate-600"
            onClick={resetPlay}
          >
            Reset
          </button>
        )}
      </div>
      {play.strokes !== null && play.finishedAt !== null && (
        <div className="text-sm" data-testid="score">
          This time: <span className="text-2xl font-bold text-pink-300">{play.strokes}</span>{' '}
          <span className="text-slate-400">
            ({play.shots.length} shot{play.shots.length === 1 ? '' : 's'} plus putts, par {par})
          </span>
        </div>
      )}
      {bins && mean !== null && blowUp !== null && (
        <div data-testid="histogram">
          <div className="flex h-24 items-end gap-1">
            {bins.map((b) => (
              <div key={b.label} className="flex flex-1 flex-col items-center justify-end gap-1" title={`${b.label}: ${b.count}`}>
                <div
                  className={`w-full rounded-t ${b.isPar ? 'bg-emerald-400' : 'bg-slate-500'}`}
                  style={{ height: `${Math.round((88 * b.count) / maxCount)}px` }}
                />
                <div className="text-[10px] text-slate-400">{b.label}</div>
              </div>
            ))}
          </div>
          <div className="mt-1 text-xs text-slate-400" data-testid="summary">
            {HISTOGRAM_RUNS} plays: mean {mean.toFixed(2)} strokes, {Math.round(100 * blowUp)}% at or above par + 3
          </div>
        </div>
      )}
    </div>
  )
}
