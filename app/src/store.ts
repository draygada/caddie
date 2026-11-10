/**
 * The single Zustand store (shape fixed in app/CLAUDE.md). Other parts add fields only
 * where their part file says. `player` and `bundle` are written with `useStore.setState`
 * by the loader caller; the recommendation is derived in a subscriber, never in render.
 */
import { create } from 'zustand'

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
