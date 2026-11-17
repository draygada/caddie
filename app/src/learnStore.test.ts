import { afterEach, beforeEach, describe, expect, it } from 'vitest'

import type { RolloutResult } from './lib/rollout'
import { readToyBundle, toyPlayerDoc } from './lib/toyFiles'
import type { Player } from './lib/types'
import { initialState, learnedObservations, planningPlayer, type RolloutClientLike, setRolloutClient, useStore } from './store'

const T0 = new Date(2026, 10, 17, 9, 0, 0).getTime()

class FakeClient implements RolloutClientLike {
  players: Player[] = []
  bundles = 0
  setBundle() {
    this.bundles += 1
  }
  recommend(player: Player): Promise<RolloutResult | null> {
    this.players.push(player)
    return Promise.resolve({ club: 'test7i', dir_deg: 0, expected_strokes: 3, baseline_pin_strokes: 3, q: new Float32Array(0) })
  }
  terminate() {
    this.players = []
  }
}

/** Two shots on the toy hole: tee to (27.5, 27.5), then on to the green. */
function playTwo() {
  const s = useStore.getState
  s().setBall({ x: 27.5, y: 2.5 })
  s().hitShot(undefined, T0)
  s().setBall({ x: 27.5, y: 27.5 })
  s().hitShot(undefined, T0 + 1)
  s().setBall({ x: 27.5, y: 44 })
  s().finishShot('green', T0 + 2)
}

beforeEach(() => useStore.setState({ ...initialState, bundle: readToyBundle(), player: toyPlayerDoc() }))
afterEach(() => {
  setRolloutClient(null)
  useStore.setState(initialState)
})

describe('learning from the log', () => {
  it('gives one observation per learnable shot, across every round in the log', () => {
    playTwo()
    expect(learnedObservations(useStore.getState())).toHaveLength(2)
    useStore.setState({ logs: { ...useStore.getState().logs, '2026-11-01:10': useStore.getState().logs['2026-11-17:toy'] } })
    expect(learnedObservations(useStore.getState())).toHaveLength(4)
  })

  it('leaves out a penalty shot', () => {
    useStore.getState().setBall({ x: 27.5, y: 2.5 })
    useStore.getState().hitShot(undefined, T0)
    useStore.getState().setBall({ x: 27.5, y: 27.5 })
    useStore.getState().finishShot('penalty', T0 + 1)
    expect(learnedObservations(useStore.getState())).toEqual([])
  })

  it('planningPlayer is the stored player until the toggle is on, and never touches it', () => {
    const base = useStore.getState().player
    playTwo()
    expect(planningPlayer(useStore.getState())).toBe(base)
    useStore.getState().setLearn(true)
    const learned = planningPlayer(useStore.getState())
    expect(learned).not.toBe(base)
    expect(learned?.clubs.test7i.stats?.n).toBe((base?.clubs.test7i.stats?.n ?? 0) + 2)
    expect(useStore.getState().player).toBe(base)
    expect(planningPlayer(useStore.getState())).toBe(learned) // memoised: same log, same player
  })
})

describe('learning in the rollout', () => {
  it('the toggle is off by default and then the worker is not used', () => {
    const client = new FakeClient()
    setRolloutClient(client)
    playTwo()
    expect(useStore.getState().learn).toBe(false)
    expect(client.players).toEqual([])
  })

  it('with the toggle on, the worker plans with the learned player', async () => {
    const client = new FakeClient()
    setRolloutClient(client)
    playTwo()
    useStore.getState().setLearn(true)
    useStore.getState().setBall({ x: 27.5, y: 12.5 })
    await new Promise((r) => setTimeout(r, 0))
    const sent = client.players[client.players.length - 1]
    expect(sent).toBe(planningPlayer(useStore.getState()))
    expect(sent).not.toBe(useStore.getState().player)
    expect(useStore.getState().recommendation?.source).toBe('worker')
  })

  it('turning the toggle on, and logging another shot, each ask the worker again', () => {
    const client = new FakeClient()
    setRolloutClient(client)
    useStore.getState().setBall({ x: 27.5, y: 2.5 })
    useStore.getState().setLearn(true)
    expect(client.players).toHaveLength(1)
    useStore.getState().hitShot(undefined, T0)
    expect(client.players).toHaveLength(2)
  })
})
