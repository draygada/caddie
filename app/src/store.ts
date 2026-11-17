/**
 * The single Zustand store (shape fixed in app/CLAUDE.md). Other parts add fields only
 * where their part file says. `player` and `bundle` are written with `useStore.setState`
 * by the loader caller; the recommendation is derived in a subscriber, never in render.
 */
import { create } from 'zustand'
import { createJSONStorage, persist, type StateStorage } from 'zustand/middleware'

import { type Aim, resolveAim, TARGET_RESET_M } from './lib/aim'
import { lieAt, policyAt, valueNearest } from './lib/grid'
import { learnedPlayer, type Observation } from './lib/learn'
import { type ActionOutcome, actionOutcome, createRolloutWorker, RolloutClient, type RolloutResult } from './lib/rollout'
import { clearAim, pinBearingDeg } from './lib/shot'
import { type LoggedShot, logKey, toObservation } from './lib/shotLog'
import type { HoleBundle, Lie, Mode, Player, XY } from './lib/types'

export type HoleId = 10 | 11 | 12 | 'toy'
/** Part 21: the home page, or one of the two hole screens. Never persisted. */
export type Screen = 'home' | 'simulate' | 'play'

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
  screen: Screen
  hole: HoleId
  mode: Mode
  tee: string
  player: Player | null
  bundle: HoleBundle | null
  ball: XY | null
  lieOverride: Lie | null
  gps: Gps | null
  recommendation: Recommendation | null
  /** Part 22: where the player is aiming; null is the caddie's aim. */
  target: XY | null
  /** Part 22: the club the player chose; null picks it from the target distance. */
  aimClub: string | null
  /** Part 12: route ball and lie changes through the rollout worker (part 14 turns it on). */
  useWorker: boolean
  /** Part 15: the shot log, one list per round, keyed by `logKey(date, hole)`. Persisted. */
  logs: Record<string, LoggedShot[]>
  /** Part 15: plan with the player learned from the log. Persisted. */
  learn: boolean
  setScreen: (s: Screen) => void
  setHole: (h: HoleId) => void
  setMode: (m: Mode) => void
  setTee: (name: string) => void
  setBall: (p: XY | null) => void
  setLieOverride: (l: Lie | null) => void
  setGps: (g: Gps | null) => void
  setRecommendation: (r: Recommendation | null) => void
  setUseWorker: (on: boolean) => void
  setTarget: (p: XY | null) => void
  setAimClub: (club: string | null) => void
  /** Back to the caddie's aim and club. */
  resetAim: () => void
  /** Record a shot from the ball with `club` (default: the recommended club); ends the open shot here. */
  hitShot: (club?: string, now?: number) => void
  /** Close the open shot at the ball: "Ball is here" (normal), "On the green", or a penalty. */
  finishShot: (outcome: 'normal' | 'green' | 'penalty', now?: number) => void
  /** Drag correction: move shot `index`'s end (and the next shot's start) to `p`, accuracy 0. */
  moveShotEnd: (key: string, index: number, p: XY) => void
  setShotClub: (club: string, now?: number) => void
  undoShot: (now?: number) => void
  clearLog: (key: string) => void
  setLearn: (on: boolean) => void
}

export const initialState = {
  screen: 'home' as Screen,
  hole: 'toy' as HoleId,
  mode: 'drop' as Mode,
  tee: 'black',
  player: null,
  bundle: null,
  ball: null,
  lieOverride: null,
  gps: null,
  recommendation: null,
  target: null as XY | null,
  aimClub: null as string | null,
  useWorker: false,
  logs: {} as Record<string, LoggedShot[]>,
  learn: false,
}

export const LOG_STORAGE_KEY = 'caddie.log'

/** `localStorage` when there is one (the browser), else a store that forgets (node, private mode). */
function logStorage(): StateStorage {
  try {
    if (typeof localStorage !== 'undefined') return localStorage
  } catch {
    /* access denied */
  }
  return { getItem: () => null, setItem: () => undefined, removeItem: () => undefined }
}

/** The log of the round being played: today's date and the selected hole. */
export function activeLog(s: Pick<State, 'logs' | 'hole'>, now = Date.now()): LoggedShot[] {
  return s.logs[logKey(now, s.hole)] ?? EMPTY_LOG
}
const EMPTY_LOG: LoggedShot[] = []

/** Where the player is standing and how well that is known: the fix when the ball sits on it. */
function standing(s: State): { at: XY; acc: number; lie: Lie } | null {
  const { bundle, ball, gps } = s
  if (!bundle || !ball) return null
  const onFix = gps !== null && gps.x === ball.x && gps.y === ball.y
  return { at: { x: ball.x, y: ball.y }, acc: onFix ? gps.accuracy_m : 0, lie: s.lieOverride ?? lieAt(bundle, ball) }
}

function closed(shot: LoggedShot, here: { at: XY; acc: number; lie: Lie }, outcome: LoggedShot['outcome']): LoggedShot {
  return { ...shot, end: here.at, endAcc: here.acc, endLie: outcome === 'green' ? 5 : here.lie, outcome }
}

function sameXY(a: XY, b: readonly [number, number]): boolean {
  return a.x === b[0] && a.y === b[1]
}

/** Where the ball was when the player last touched the aim (part 22 staleness rule). */
let aimedFrom: XY | null = null

export const useStore = create<State>()(
  persist(
    (set, get) => ({
  ...initialState,
  setScreen: (screen) => set({ screen }),
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
  setTarget: (target) => {
    aimedFrom = get().ball
    set({ target })
  },
  setAimClub: (aimClub) => {
    aimedFrom = get().ball
    set({ aimClub })
  },
  resetAim: () => set({ target: null, aimClub: null }),
  hitShot: (club, now = Date.now()) => {
    const s = get()
    const here = standing(s)
    const rec = s.recommendation
    if (!here || !s.bundle || !rec) return
    const key = logKey(now, s.hole)
    const log = s.logs[key] ?? []
    const last = log[log.length - 1]
    const before = last && last.end === null ? [...log.slice(0, -1), closed(last, here, 'normal')] : log
    // Part 22: the shot is logged with the player's club and aim; recAimDeg keeps the caddie's.
    const aim = currentAim(s)
    const bearing = pinBearingDeg(s.bundle, here.at)
    const recAimDeg = bearing + rec.dir_deg
    const aimDeg = aim ? bearing + aim.dir_deg : recAimDeg
    const shot: LoggedShot = {
      start: here.at,
      end: null,
      startAcc: here.acc,
      endAcc: null,
      lie: here.lie,
      club: club ?? aim?.club ?? rec.club,
      aimDeg,
      recAimDeg,
      t: now,
      outcome: 'normal',
    }
    set({ logs: { ...s.logs, [key]: [...before, shot] } })
  },
  finishShot: (outcome, now = Date.now()) => {
    const s = get()
    const here = standing(s)
    const key = logKey(now, s.hole)
    const log = s.logs[key]
    const last = log?.[log.length - 1]
    if (!here || !log || !last || last.end !== null) return
    set({ logs: { ...s.logs, [key]: [...log.slice(0, -1), closed(last, here, outcome)] } })
  },
  moveShotEnd: (key, index, p) => {
    const { logs, bundle } = get()
    const log = logs[key]
    const shot = log?.[index]
    if (!log || !shot || shot.end === null) return
    const next = log.map((x, k) => {
      if (k === index) return { ...x, end: p, endAcc: 0, endLie: bundle ? lieAt(bundle, p) : x.endLie }
      if (k === index + 1) return { ...x, start: p, startAcc: 0 }
      return x
    })
    set({ logs: { ...logs, [key]: next } })
  },
  setShotClub: (club, now = Date.now()) => {
    const { logs, hole } = get()
    const key = logKey(now, hole)
    const log = logs[key]
    if (!log || log.length === 0) return
    set({ logs: { ...logs, [key]: [...log.slice(0, -1), { ...log[log.length - 1], club }] } })
  },
  undoShot: (now = Date.now()) => {
    const { logs, hole } = get()
    const key = logKey(now, hole)
    const log = logs[key]
    if (!log || log.length === 0) return
    const kept = log.slice(0, -1)
    const prev = kept[kept.length - 1]
    // The shot before ended where the removed one started: it is open again.
    if (prev && prev.outcome === 'normal') {
      const reopened: LoggedShot = { ...prev, end: null, endAcc: null }
      delete reopened.endLie
      kept[kept.length - 1] = reopened
    }
    set({ logs: { ...logs, [key]: kept } })
  },
  clearLog: (key) => {
    set({ logs: Object.fromEntries(Object.entries(get().logs).filter(([k]) => k !== key)) })
  },
  setLearn: (learn) => set({ learn }),
    }),
    {
      name: LOG_STORAGE_KEY,
      version: 1,
      storage: createJSONStorage(logStorage),
      // Only the log and the toggle outlive the tab; player.json is never written (part 15).
      partialize: (s) => ({ logs: s.logs, learn: s.learn }),
    },
  ),
)

// --- derived recommendation (M1: a direct grid lookup) -------------------------------------

/** Grid recommendation at `ball`, or null on terminal and out-of-grid cells. */
export function gridRecommendation(
  bundle: HoleBundle | null,
  ball: XY | null,
  player: Player | null = null,
  lie: Lie | null = null,
): Recommendation | null {
  if (!bundle || !ball) return null
  const policy = policyAt(bundle, ball)
  if (!policy) return null
  // Part 17: the grid's aim is for the cell centre; step off it if a tree blocks it from here.
  const dir_deg = player ? clearAim(bundle, player, ball, lie ?? lieAt(bundle, ball), policy.club, policy.dir_deg) : policy.dir_deg
  return {
    club: policy.club,
    dir_deg,
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

// --- part 22: the player's aim goes stale -----------------------------------------------------

/** A new hole, or a ball more than `TARGET_RESET_M` from where the aim was set, clears the aim. */
useStore.subscribe((state, prev) => {
  if (state.target === null && state.aimClub === null) return
  const moved =
    state.ball !== prev.ball &&
    state.ball !== null &&
    aimedFrom !== null &&
    Math.hypot(state.ball.x - aimedFrom.x, state.ball.y - aimedFrom.y) > TARGET_RESET_M
  if (state.bundle !== prev.bundle || state.ball === null || moved) state.resetAim()
})

type AimInputs = Pick<State, 'bundle' | 'player' | 'ball' | 'lieOverride' | 'recommendation' | 'target' | 'aimClub' | 'mode'>

let aimMemo: { key: unknown[]; aim: Aim | null } | null = null
let outcomeMemo: { aim: Aim; key: unknown[]; outcome: ActionOutcome } | null = null

function sameKey(a: unknown[], b: unknown[]): boolean {
  return a.length === b.length && a.every((v, i) => v === b[i])
}

/**
 * The aim in force: the caddie's until the player moves the target or picks a club. Null
 * when there is no shot to aim (no ball, on the green, in a hazard). Memoised on its inputs,
 * so it is safe as a Zustand selector.
 */
export function currentAim(s: AimInputs): Aim | null {
  const key = [s.bundle, s.player, s.ball, s.lieOverride, s.recommendation, s.target, s.aimClub]
  if (aimMemo && sameKey(aimMemo.key, key)) return aimMemo.aim
  let aim: Aim | null = null
  const { bundle, player, ball, recommendation } = s
  if (bundle && player && ball && recommendation && recommendation.club in player.clubs) {
    const lie = s.lieOverride ?? lieAt(bundle, ball)
    if ((lie >= 1 && lie <= 4) || lie === 8) aim = resolveAim(bundle, player, ball, lie, recommendation, s.target, s.aimClub)
  }
  aimMemo = { key, aim }
  return aim
}

export const OUTCOME_DRAWS = 200

/** What is likely for the aim in force: 200 shots from the player's distribution. */
export function currentOutcome(s: AimInputs): ActionOutcome | null {
  const aim = currentAim(s)
  const { bundle, player, ball } = s
  if (!aim || !bundle || !player || !ball) return null
  const key = [bundle, player, ball, s.lieOverride, s.mode]
  if (outcomeMemo && outcomeMemo.aim === aim && sameKey(outcomeMemo.key, key)) return outcomeMemo.outcome
  const lie = s.lieOverride ?? lieAt(bundle, ball)
  const outcome = actionOutcome(bundle, player, ball, lie, aim.club, aim.dir_deg, s.mode, OUTCOME_DRAWS, 1)
  outcomeMemo = { aim, key, outcome }
  return outcome
}

// --- part 15: learning from the log ------------------------------------------------------------

/** Every learnable shot in the log, all rounds, oldest round first. Needs a bundle and a player. */
export function learnedObservations(s: Pick<State, 'logs' | 'bundle' | 'player'>): Observation[] {
  const { bundle, player } = s
  if (!bundle || !player) return []
  const out: Observation[] = []
  for (const key of Object.keys(s.logs).sort())
    for (const shot of s.logs[key]) {
      const o = toObservation(bundle, player, shot)
      if (o) out.push(o)
    }
  return out
}

let memo: { logs: State['logs']; player: Player; bundle: HoleBundle; learned: Player } | null = null

/**
 * The player the rollout plans with: the stored player, or with "Use my course shots" on,
 * the player learned from the log. Recomputed from the log, never stored.
 */
export function planningPlayer(s: Pick<State, 'logs' | 'bundle' | 'player' | 'learn'>): Player | null {
  const { player, bundle } = s
  if (!s.learn || !player || !bundle) return player
  if (!memo || memo.logs !== s.logs || memo.player !== player || memo.bundle !== bundle)
    memo = { logs: s.logs, player, bundle, learned: learnedPlayer(player, learnedObservations(s)) }
  return memo.learned
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
    state.useWorker === prev.useWorker &&
    state.learn === prev.learn &&
    (!state.learn || state.logs === prev.logs)
  )
    return
  const grid = gridRecommendation(state.bundle, state.ball, state.player, state.lieOverride)
  state.setRecommendation(grid)
  const { bundle, ball, mode } = state
  // Part 15: the grid was solved for the stored player, so a learned player needs the worker.
  const player = planningPlayer(state)
  if (!(state.useWorker || state.learn) || !rolloutClient || !bundle || !ball || !player || !grid) return
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
