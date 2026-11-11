import { afterEach, beforeEach, describe, expect, it } from 'vitest'

import { policyAt, valueNearest } from './lib/grid'
import { readToyBundle, toyPlayerDoc } from './lib/toyFiles'
import type { RolloutResult } from './lib/rollout'
import type { HoleBundle, Lie, Player, XY } from './lib/types'
import { initialState, type RolloutClientLike, setRolloutClient, useStore } from './store'

beforeEach(() => useStore.setState(initialState))

describe('store shape', () => {
  it('starts with the fixed shape from app/CLAUDE.md', () => {
    const s = useStore.getState()
    expect(s.hole).toBe('toy')
    expect(s.mode).toBe('drop')
    expect(s.tee).toBe('black')
    expect(s.player).toBeNull()
    expect(s.bundle).toBeNull()
    expect(s.ball).toBeNull()
    expect(s.lieOverride).toBeNull()
    expect(s.gps).toBeNull()
    expect(s.recommendation).toBeNull()
    for (const a of [
      'setHole',
      'setMode',
      'setTee',
      'setBall',
      'setLieOverride',
      'setGps',
      'setRecommendation',
    ] as const)
      expect(typeof s[a]).toBe('function')
  })
})

describe('setBall', () => {
  it('updates ball and nothing else', () => {
    const before = useStore.getState()
    before.setBall({ x: 12, y: 47 })
    const after = useStore.getState()
    expect(after.ball).toEqual({ x: 12, y: 47 })
    for (const k of Object.keys(before) as (keyof typeof before)[]) {
      if (k === 'ball') continue
      expect(after[k]).toBe(before[k])
    }
  })

  it('accepts null', () => {
    useStore.getState().setBall({ x: 1, y: 1 })
    useStore.getState().setBall(null)
    expect(useStore.getState().ball).toBeNull()
  })
})

describe('simple setters', () => {
  it('setHole, setMode, setLieOverride, setGps, setRecommendation write their field', () => {
    const s = useStore.getState()
    s.setHole(11)
    s.setMode('replay')
    s.setLieOverride(3)
    s.setGps({ x: 1, y: 2, accuracy_m: 5 })
    s.setRecommendation({ club: '7i', dir_deg: 4, expected_strokes: 3.2, source: 'grid' })
    const t = useStore.getState()
    expect([t.hole, t.mode, t.lieOverride]).toEqual([11, 'replay', 3])
    expect(t.gps).toEqual({ x: 1, y: 2, accuracy_m: 5 })
    expect(t.recommendation?.club).toBe('7i')
  })
})

describe('setTee', () => {
  const bundle = readToyBundle()
  const tees: Record<string, [number, number]> = { black: [27.5, 2.5], white: [27.5, 12.5] }
  const two = { ...bundle, meta: { ...bundle.meta, tees } }

  it('sets the ball to the tee when the ball is null', () => {
    useStore.setState({ bundle: two, ball: null })
    useStore.getState().setTee('white')
    expect(useStore.getState().tee).toBe('white')
    expect(useStore.getState().ball).toEqual({ x: 27.5, y: 12.5 })
  })

  it('moves the ball when it sits on another tee', () => {
    useStore.setState({ bundle: two, ball: { x: 27.5, y: 2.5 }, tee: 'black' })
    useStore.getState().setTee('white')
    expect(useStore.getState().ball).toEqual({ x: 27.5, y: 12.5 })
  })

  it('leaves a ball that is elsewhere alone', () => {
    useStore.setState({ bundle: two, ball: { x: 10, y: 30 }, tee: 'black' })
    useStore.getState().setTee('white')
    expect(useStore.getState().ball).toEqual({ x: 10, y: 30 })
  })

  it('only records the name when there is no bundle', () => {
    useStore.getState().setTee('white')
    expect(useStore.getState().tee).toBe('white')
    expect(useStore.getState().ball).toBeNull()
  })

  it('keeps player and bundle as plain fields', () => {
    useStore.setState({ player: toyPlayerDoc(), bundle })
    expect(useStore.getState().player?.handicap).toBe(15)
    expect(useStore.getState().bundle?.meta.hole).toBe('toy')
  })
})

describe('derived recommendation (subscriber)', () => {
  const bundle = readToyBundle()
  const tee = { x: bundle.meta.tee_xy[0], y: bundle.meta.tee_xy[1] }

  it('writes a grid recommendation when the ball moves', () => {
    useStore.setState({ bundle })
    useStore.getState().setBall(tee)
    const r = useStore.getState().recommendation
    expect(r).not.toBeNull()
    expect(r?.source).toBe('grid')
    expect(r?.club).toBe('test7i')
    expect(r?.dir_deg).toBe(policyAt(bundle, tee)?.dir_deg)
    expect(r?.expected_strokes).toBe(valueNearest(bundle, tee))
    expect(Number.isFinite(r?.expected_strokes)).toBe(true)
  })

  it('is null on the green, off grid, and without a bundle or ball', () => {
    useStore.setState({ bundle })
    useStore.getState().setBall({ x: bundle.meta.pin_xy[0], y: bundle.meta.pin_xy[1] })
    expect(useStore.getState().recommendation).toBeNull()
    useStore.getState().setBall({ x: 47.5, y: 20 }) // OB column
    expect(useStore.getState().recommendation).toBeNull()
    useStore.getState().setBall(tee)
    expect(useStore.getState().recommendation).not.toBeNull()
    useStore.getState().setBall(null)
    expect(useStore.getState().recommendation).toBeNull()
    useStore.getState().setBall(tee)
    useStore.setState({ bundle: null })
    expect(useStore.getState().recommendation).toBeNull()
  })

  it('recomputes when the bundle changes under a fixed ball', () => {
    useStore.setState({ bundle, ball: tee })
    const first = useStore.getState().recommendation
    expect(first).not.toBeNull()
    const shifted = { ...bundle, value: bundle.value.map((v) => v + 1) }
    useStore.setState({ bundle: shifted })
    const second = useStore.getState().recommendation
    expect(second?.expected_strokes).toBeCloseTo((first?.expected_strokes ?? 0) + 1, 5)
  })

  it('recomputes on a lie override but still reads the grid in M1', () => {
    useStore.setState({ bundle, ball: tee })
    const before = useStore.getState().recommendation
    useStore.getState().setLieOverride(3)
    const after = useStore.getState().recommendation
    expect(after).toEqual(before)
  })

  it('does not run when unrelated fields change', () => {
    useStore.setState({ bundle, ball: tee })
    const r = useStore.getState().recommendation
    useStore.getState().setMode('replay')
    useStore.getState().setGps({ x: 1, y: 1, accuracy_m: 3 })
    expect(useStore.getState().recommendation).toBe(r) // same object, not recomputed
  })

  it('leaves a worker recommendation alone', () => {
    useStore.setState({ bundle, ball: tee })
    useStore.getState().setRecommendation({ club: 'x', dir_deg: 0, expected_strokes: 9, source: 'worker' })
    expect(useStore.getState().recommendation?.source).toBe('worker')
  })
})

describe('worker wiring (part 12 slice 6)', () => {
  const bundle = readToyBundle()
  const tee = { x: bundle.meta.tee_xy[0], y: bundle.meta.tee_xy[1] }

  class FakeClient implements RolloutClientLike {
    bundles: HoleBundle[] = []
    calls: { from: XY; lie: Lie }[] = []
    setBundle(b: HoleBundle) {
      this.bundles.push(b)
    }
    recommend(_player: Player, from: XY, lie: Lie): Promise<RolloutResult | null> {
      this.calls.push({ from, lie })
      const result: RolloutResult = {
        club: 'test7i',
        dir_deg: 12,
        expected_strokes: 9.5,
        baseline_pin_strokes: 9.9,
        q: new Float32Array(0),
      }
      return Promise.resolve(result)
    }
    terminate() {
      this.calls = []
    }
  }

  const flush = () => new Promise((r) => setTimeout(r, 0))

  afterEach(() => setRolloutClient(null))

  it('defaults to useWorker false and the grid lookup', () => {
    const client = new FakeClient()
    setRolloutClient(client)
    useStore.setState({ bundle, player: toyPlayerDoc() })
    useStore.getState().setBall(tee)
    expect(useStore.getState().useWorker).toBe(false)
    expect(useStore.getState().recommendation?.source).toBe('grid')
    expect(client.calls).toHaveLength(0)
  })

  it('with useWorker true, ball and lie changes go to the worker and its answer becomes the recommendation', async () => {
    const client = new FakeClient()
    setRolloutClient(client)
    useStore.setState({ bundle, player: toyPlayerDoc() })
    useStore.getState().setUseWorker(true)
    useStore.getState().setBall(tee)
    await flush()
    expect(client.calls).toHaveLength(1)
    expect(client.calls[0].lie).toBe(2)
    const r = useStore.getState().recommendation
    expect(r?.source).toBe('worker')
    expect(r?.expected_strokes).toBe(9.5)
    expect(r?.baseline_pin_strokes).toBe(9.9)
    useStore.getState().setLieOverride(3)
    await flush()
    expect(client.calls).toHaveLength(2)
    expect(client.calls[1].lie).toBe(3)
    expect(new Set(client.bundles)).toEqual(new Set([bundle])) // same object each time; the client dedups
  })

  it('sends the grid lookup first so the panel is never empty while the worker runs', () => {
    const slow = new FakeClient()
    slow.recommend = () => new Promise(() => undefined) // never resolves
    setRolloutClient(slow)
    useStore.setState({ bundle, player: toyPlayerDoc(), useWorker: true })
    useStore.getState().setBall(tee)
    expect(useStore.getState().recommendation?.source).toBe('grid')
  })

  it('on the green or without a player it clears the recommendation and does not post', async () => {
    const client = new FakeClient()
    setRolloutClient(client)
    useStore.setState({ bundle, player: toyPlayerDoc(), useWorker: true })
    useStore.getState().setBall({ x: bundle.meta.pin_xy[0], y: bundle.meta.pin_xy[1] })
    await flush()
    expect(useStore.getState().recommendation).toBeNull()
    expect(client.calls).toHaveLength(0)
  })

  it('without a client, useWorker true falls back to the grid', () => {
    useStore.setState({ bundle, player: toyPlayerDoc(), useWorker: true })
    useStore.getState().setBall(tee)
    expect(useStore.getState().recommendation?.source).toBe('grid')
  })
})
