/**
 * The single Zustand store (shape fixed in app/CLAUDE.md). Other parts add fields only
 * where their part file says. `player` and `bundle` are written with `useStore.setState`
 * by the loader caller; the recommendation is derived in a subscriber, never in render.
 */
import { create } from 'zustand'

import { lieAt, policyAt, valueNearest } from './lib/grid'
import { createRolloutWorker, RolloutClient, type RolloutResult } from './lib/rollout'
import type { HoleBundle, Lie, Mode, Player, XY } from './lib/types'

export type HoleId = 10 | 11 | 12 | 'toy'

export interface Recommendation {
  club: string
  dir_deg: number
  expected_strokes: number
  baseline_pin_strokes?: number
  source: 'grid' | 'worker'
}

export interface Gps extends XY {
  accuracy_m: number
}

export interface State {
  hole: HoleId
  mode: Mode
  tee: string
  player: Player | null
  bundle: HoleBundle | null
  ball: XY | null
  lieOverride: Lie | null
  gps: Gps | null
  recommendation: Recommendation | null
  /** Part 12: route ball and lie changes through the rollout worker (part 14 turns it on). */
  useWorker: boolean
  setHole: (h: HoleId) => void
  setMode: (m: Mode) => void
  setTee: (name: string) => void
  setBall: (p: XY | null) => void
  setLieOverride: (l: Lie | null) => void
  setGps: (g: Gps | null) => void
  setRecommendation: (r: Recommendation | null) => void
  setUseWorker: (on: boolean) => void
}

export const initialState = {
  hole: 'toy' as HoleId,
  mode: 'drop' as Mode,
  tee: 'black',
  player: null,
  bundle: null,
  ball: null,
  lieOverride: null,
  gps: null,
  recommendation: null,
  useWorker: false,
}

function sameXY(a: XY, b: readonly [number, number]): boolean {
  return a.x === b[0] && a.y === b[1]
}

export const useStore = create<State>()((set, get) => ({
  ...initialState,
  setHole: (hole) => set({ hole }),
  setMode: (mode) => set({ mode }),
  setTee: (tee) => {
    const { bundle, ball } = get()
    const xy = bundle?.meta.tees[tee]
    if (!xy) {
      set({ tee })
      return
    }
    const onAnotherTee =
      ball !== null && Object.values(bundle.meta.tees).some((t) => sameXY(ball, t))
    const moveBall = ball === null || onAnotherTee
    set({ tee, ball: moveBall ? { x: xy[0], y: xy[1] } : ball })
  },
  setBall: (ball) => set({ ball }),
  setLieOverride: (lieOverride) => set({ lieOverride }),
  setGps: (gps) => set({ gps }),
  setRecommendation: (recommendation) => set({ recommendation }),
  setUseWorker: (useWorker) => set({ useWorker }),
}))

// --- derived recommendation (M1: a direct grid lookup) -------------------------------------

/** Grid recommendation at `ball`, or null on terminal and out-of-grid cells. */
export function gridRecommendation(bundle: HoleBundle | null, ball: XY | null): Recommendation | null {
  if (!bundle || !ball) return null
  const policy = policyAt(bundle, ball)
  if (!policy) return null
  return {
    club: policy.club,
    dir_deg: policy.dir_deg,
    expected_strokes: valueNearest(bundle, ball),
    source: 'grid',
  }
}

// --- part 12: the rollout worker -------------------------------------------------------------

/** What the store needs from `RolloutClient`; tests substitute an in-process fake. */
export interface RolloutClientLike {
  setBundle(bundle: HoleBundle): void
  recommend(player: Player, from: XY, lie: Lie, mode: Mode, m?: number, seed?: number): Promise<RolloutResult | null>
  terminate(): void
}

let rolloutClient: RolloutClientLike | null = null

/** Install (or remove with null) the worker client the subscriber posts to. */
export function setRolloutClient(client: RolloutClientLike | null): void {
  rolloutClient = client
}

export const WORKER_DRAWS = 100

/**
 * Whenever ball, lieOverride or bundle changes: write the grid recommendation at once, and
 * when `useWorker` is on and a client is installed, post to the worker and replace it with
 * the worker's answer (`source: 'worker'`). Stale answers resolve null and are ignored.
 * Runs outside React render.
 */
useStore.subscribe((state, prev) => {
  if (
    state.ball === prev.ball &&
    state.lieOverride === prev.lieOverride &&
    state.bundle === prev.bundle &&
    state.useWorker === prev.useWorker
  )
    return
  const grid = gridRecommendation(state.bundle, state.ball)
  state.setRecommendation(grid)
  const { bundle, ball, player, mode } = state
  if (!state.useWorker || !rolloutClient || !bundle || !ball || !player || !grid) return
  const lie = state.lieOverride ?? lieAt(bundle, ball)
  if (lie < 1 || lie > 4) return
  rolloutClient.setBundle(bundle)
  rolloutClient
    .recommend(player, ball, lie, mode, WORKER_DRAWS, 1)
    .then((result) => {
      if (!result) return // superseded by a newer request
      const now = useStore.getState()
      if (now.ball !== ball || now.bundle !== bundle || now.lieOverride !== state.lieOverride) return
      now.setRecommendation({
        club: result.club,
        dir_deg: result.dir_deg,
        expected_strokes: result.expected_strokes,
        baseline_pin_strokes: result.baseline_pin_strokes,
        source: 'worker',
      })
    })
    .catch((e: unknown) => console.warn('rollout worker:', e))
})

// In the browser, install the real Web Worker. Tests and node have no `Worker`.
if (typeof Worker !== 'undefined') setRolloutClient(new RolloutClient(createRolloutWorker))
