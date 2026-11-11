/**
 * The single Zustand store (shape fixed in app/CLAUDE.md). Other parts add fields only
 * where their part file says. `player` and `bundle` are written with `useStore.setState`
 * by the loader caller; the recommendation is derived in a subscriber, never in render.
 */
import { create } from 'zustand'

import { policyAt, valueNearest } from './lib/grid'
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
  setHole: (h: HoleId) => void
  setMode: (m: Mode) => void
  setTee: (name: string) => void
  setBall: (p: XY | null) => void
  setLieOverride: (l: Lie | null) => void
  setGps: (g: Gps | null) => void
  setRecommendation: (r: Recommendation | null) => void
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

/**
 * Whenever ball, lieOverride or bundle changes and no worker is active (M1), write the grid
 * recommendation. Runs outside React render. Part 12's worker takes over by writing
 * `source: 'worker'` recommendations itself.
 */
useStore.subscribe((state, prev) => {
  if (state.ball === prev.ball && state.lieOverride === prev.lieOverride && state.bundle === prev.bundle)
    return
  state.setRecommendation(gridRecommendation(state.bundle, state.ball))
})
