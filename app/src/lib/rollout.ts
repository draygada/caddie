/**
 * Rollout lookahead (Ch 9.2) at a continuous point, matching solver/caddie/online.py
 * `recommend`: one sampled shot per draw for every candidate action, then the value grid
 * at the landing by bilinear interpolation (expected putts when the landing is on the
 * green). Candidate clubs are those with mu_c <= 1.3 x distance to the pin, the shortest
 * club always kept. The pin baseline (direction 0, longest club that reaches) uses the
 * same draws, so the comparison is paired.
 */
import { distance, valueBilinear } from './grid'
import { mulberry32 } from './rng'
import { expectedPutts, sampleShot } from './shot'
import type { HoleBundle, Lie, Mode, Player, XY } from './types'

export const CANDIDATE_CARRY_FACTOR = 1.3

export interface RolloutResult {
  club: string
  dir_deg: number
  expected_strokes: number
  baseline_pin_strokes: number
  /** strokes-to-go per (club, direction), row-major clubs x dirs, NaN where pruned */
  q: Float32Array
}

/** Clubs worth evaluating from `from`: mu_c <= 1.3 x distance to the pin, shortest always kept. */
export function candidateClubs(b: HoleBundle, player: Player, from: XY): number[] {
  const pin = { x: b.meta.pin_xy[0], y: b.meta.pin_xy[1] }
  const d = distance(from, pin)
  const mus = player.club_order.map((c) => player.clubs[c].mu_c)
  const keep = mus.map((mu, i) => (mu <= CANDIDATE_CARRY_FACTOR * d ? i : -1)).filter((i) => i >= 0)
  if (keep.length === 0) keep.push(mus.indexOf(Math.min(...mus)))
  return keep
}

/** Leaf value at a landing: expected putts on the green, else the interpolated grid value. */
function leafValue(b: HoleBundle, player: Player, p: XY, lie: Lie): number {
  if (lie === 5) {
    const pin = { x: b.meta.pin_xy[0], y: b.meta.pin_xy[1] }
    return expectedPutts(player, distance(p, pin))
  }
  const v = valueBilinear(b, p)
  return Number.isFinite(v) ? v : NaN
}

/** Mean strokes-to-go of one action over `draws` fresh shots from one seed. */
function actionValue(
  b: HoleBundle,
  player: Player,
  from: XY,
  lie: Lie,
  club: string,
  dir_deg: number,
  mode: Mode,
  m: number,
  seed: number,
): number {
  const rng = mulberry32(seed)
  let sum = 0
  for (let j = 0; j < m; j++) {
    const s = sampleShot(b, player, from, lie, club, dir_deg, mode, rng)
    const next = s.next
    const nextLie = s.reward === -1 ? s.lie : lieOfNext(b, next)
    sum += -s.reward + leafValue(b, player, next, nextLie)
  }
  return sum / m
}

function lieOfNext(b: HoleBundle, p: XY): Lie {
  const { cols, cell_m } = b.meta
  const r = Math.floor(p.y / cell_m)
  const c = Math.floor(p.x / cell_m)
  return b.lie[r * cols + c] as Lie
}

export function recommend(
  b: HoleBundle,
  player: Player,
  from: XY,
  lie: Lie,
  mode: Mode,
  m = 100,
  seed = 1,
): RolloutResult {
  if (lie === 5 || lie < 1 || lie > 5) throw new Error(`no shot from lie ${lie}`)
  const dirs = b.meta.directions_deg
  const nClubs = player.club_order.length
  const q = new Float32Array(nClubs * dirs.length).fill(NaN)
  let best = Infinity
  let bestClub = -1
  let bestDir = -1
  for (const ci of candidateClubs(b, player, from)) {
    const club = player.club_order[ci]
    for (let di = 0; di < dirs.length; di++) {
      const v = actionValue(b, player, from, lie, club, dirs[di], mode, m, seed)
      q[ci * dirs.length + di] = v
      if (v < best) {
        best = v
        bestClub = ci
        bestDir = di
      }
    }
  }
  if (bestClub < 0) throw new Error('no finite action value')

  const pin = { x: b.meta.pin_xy[0], y: b.meta.pin_xy[1] }
  const d = distance(from, pin)
  const mus = player.club_order.map((c) => player.clubs[c].mu_c)
  let baseCi = -1
  for (let i = 0; i < mus.length; i++) if (mus[i] <= d && (baseCi < 0 || mus[i] > mus[baseCi])) baseCi = i
  if (baseCi < 0) baseCi = mus.indexOf(Math.min(...mus))
  const zero = dirs.indexOf(0)
  const stored = q[baseCi * dirs.length + zero]
  const baseline = Number.isFinite(stored)
    ? stored
    : actionValue(b, player, from, lie, player.club_order[baseCi], 0, mode, m, seed)

  return {
    club: player.club_order[bestClub],
    dir_deg: dirs[bestDir],
    expected_strokes: best,
    baseline_pin_strokes: baseline,
    q,
  }
}

// --- worker protocol (slice 5) ---------------------------------------------------------------
//
// The bundle is posted once and cached in the worker; every later request carries only the
// player (small) and the point. The client drops stale responses: only the latest requestId
// resolves with a result, earlier ones resolve null.

export type WorkerRequest =
  | { type: 'bundle'; bundle: HoleBundle }
  | {
      type: 'recommend'
      requestId: number
      player: Player
      from: XY
      lie: Lie
      mode: Mode
      m: number
      seed: number
    }

export interface WorkerResponse {
  requestId: number
  result?: RolloutResult
  error?: string
}

export type MessageHandler = (msg: WorkerRequest, post: (out: WorkerResponse) => void) => void

/** A worker message handler with its own bundle cache, pure enough to run in-process in tests. */
export function createHandler(): MessageHandler {
  let cached: HoleBundle | null = null
  return (msg, post) => {
    if (msg.type === 'bundle') {
      cached = msg.bundle
      return
    }
    if (!cached) {
      post({ requestId: msg.requestId, error: 'no bundle sent to the rollout worker' })
      return
    }
    try {
      const result = recommend(cached, msg.player, msg.from, msg.lie, msg.mode, msg.m, msg.seed)
      post({ requestId: msg.requestId, result })
    } catch (e) {
      post({ requestId: msg.requestId, error: e instanceof Error ? e.message : String(e) })
    }
  }
}

/** The handler the worker entry uses (one per worker instance). */
export const handleMessage: MessageHandler = createHandler()

/** The subset of `Worker` the client uses, so tests can substitute an in-process fake. */
export interface WorkerLike {
  postMessage(msg: WorkerRequest): void
  onmessage: ((e: MessageEvent<WorkerResponse>) => void) | null
  terminate(): void
}

interface Pending {
  resolve: (r: RolloutResult | null) => void
  reject: (e: Error) => void
}

export class RolloutClient {
  private worker: WorkerLike | null = null
  private bundle: HoleBundle | null = null
  private bundleSent: HoleBundle | null = null
  private nextId = 1
  private latestId = 0
  private pending = new Map<number, Pending>()

  constructor(private readonly create: () => WorkerLike) {}

  private ensureWorker(): WorkerLike {
    if (this.worker) return this.worker
    const w = this.create()
    w.onmessage = (e) => this.onResponse(e.data)
    this.worker = w
    return w
  }

  private onResponse(msg: WorkerResponse): void {
    const p = this.pending.get(msg.requestId)
    if (!p) return
    this.pending.delete(msg.requestId)
    if (msg.error !== undefined) {
      p.reject(new Error(msg.error))
      return
    }
    // stale: a newer request was posted after this one
    p.resolve(msg.requestId === this.latestId ? (msg.result ?? null) : null)
  }

  /** Remember the bundle; it is posted lazily, once per distinct bundle object. */
  setBundle(bundle: HoleBundle): void {
    this.bundle = bundle
  }

  recommend(player: Player, from: XY, lie: Lie, mode: Mode, m = 100, seed = 1): Promise<RolloutResult | null> {
    const w = this.ensureWorker()
    if (this.bundle && this.bundle !== this.bundleSent) {
      w.postMessage({ type: 'bundle', bundle: this.bundle })
      this.bundleSent = this.bundle
    }
    const requestId = this.nextId++
    this.latestId = requestId
    return new Promise((resolve, reject) => {
      this.pending.set(requestId, { resolve, reject })
      w.postMessage({ type: 'recommend', requestId, player, from, lie, mode, m, seed })
    })
  }

  terminate(): void {
    this.worker?.terminate()
    this.worker = null
    this.bundleSent = null
    for (const p of this.pending.values()) p.resolve(null)
    this.pending.clear()
  }
}

/** The real Web Worker, created with Vite's worker URL form. Browser only. */
export function createRolloutWorker(): WorkerLike {
  return new Worker(new URL('../workers/rollout.worker.ts', import.meta.url), { type: 'module' })
}
