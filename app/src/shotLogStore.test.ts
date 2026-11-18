import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'

import { logKey } from './lib/shotLog'
import { pinBearingDeg } from './lib/shot'
import { readToyBundle, toyPlayerDoc } from './lib/toyFiles'
import { activeLog, initialState, LOG_STORAGE_KEY, useStore } from './store'

const T0 = new Date(2026, 10, 17, 9, 0, 0).getTime()
const KEY = '2026-11-17:toy'

function load() {
  useStore.setState({ ...initialState, bundle: readToyBundle(), player: toyPlayerDoc() })
}
const log = () => activeLog(useStore.getState(), T0)

beforeEach(load)
afterEach(() => useStore.setState(initialState))

describe('logKey', () => {
  it('is the local date and the hole', () => {
    expect(logKey(T0, 'toy')).toBe(KEY)
    expect(logKey(new Date(2026, 0, 5, 23, 59).getTime(), 11)).toBe('2026-01-05:11')
  })
})

describe('hitShot', () => {
  it('records position, lie, the recommended club and aim, and the time', () => {
    const s = useStore.getState()
    s.setBall({ x: 27.5, y: 2.5 })
    const rec = useStore.getState().recommendation
    if (!rec) throw new Error('no recommendation on the toy tee')
    useStore.getState().hitShot(undefined, T0)
    const [shot] = log()
    expect(log()).toHaveLength(1)
    expect(shot.start).toEqual({ x: 27.5, y: 2.5 })
    expect(shot.end).toBeNull()
    expect(shot.startAcc).toBe(0) // the marker was placed by hand
    expect(shot.lie).toBe(useStore.getState().bundle?.lie[5])
    expect(shot.club).toBe(rec.club)
    const bearing = pinBearingDeg(readToyBundle(), { x: 27.5, y: 2.5 }) + rec.dir_deg
    expect(shot.aimDeg).toBeCloseTo(bearing, 9)
    expect(shot.recAimDeg).toBeCloseTo(bearing, 9)
    expect(shot.t).toBe(T0)
    expect(shot.outcome).toBe('normal')
    expect(Object.keys(useStore.getState().logs)).toEqual([KEY])
  })

  it('uses the GPS accuracy when the ball is on the fix, and the chosen club and lie override', () => {
    useStore.getState().setGps({ x: 22, y: 12, accuracy_m: 7 })
    useStore.getState().setBall({ x: 22, y: 12 })
    useStore.getState().setLieOverride(3)
    useStore.getState().hitShot('sw', T0)
    expect(log()[0].startAcc).toBe(7)
    expect(log()[0].club).toBe('sw')
    expect(log()[0].lie).toBe(3)
  })

  it('ends the previous shot where the next one starts', () => {
    useStore.getState().setBall({ x: 27.5, y: 2.5 })
    useStore.getState().hitShot(undefined, T0)
    useStore.getState().setGps({ x: 30, y: 22, accuracy_m: 6 })
    useStore.getState().setBall({ x: 30, y: 22 })
    useStore.getState().hitShot(undefined, T0 + 60_000)
    const [first, second] = log()
    expect(first.end).toEqual({ x: 30, y: 22 })
    expect(first.endAcc).toBe(6)
    expect(first.endLie).toBe(2)
    expect(first.outcome).toBe('normal')
    expect(second.start).toEqual({ x: 30, y: 22 })
    expect(second.end).toBeNull()
  })

  it('does nothing without a ball or without a shot to recommend', () => {
    useStore.getState().hitShot(undefined, T0)
    expect(log()).toEqual([])
    useStore.getState().setBall({ x: 27.5, y: 47.5 }) // on the green
    useStore.getState().hitShot(undefined, T0)
    expect(log()).toEqual([])
  })
})

describe('finishShot', () => {
  beforeEach(() => {
    useStore.getState().setBall({ x: 27.5, y: 2.5 })
    useStore.getState().hitShot(undefined, T0)
    useStore.getState().setBall({ x: 27.5, y: 44 })
  })

  it('"On the green" closes the last shot at the ball', () => {
    useStore.getState().finishShot('green')
    const [shot] = log()
    expect(shot.end).toEqual({ x: 27.5, y: 44 })
    expect(shot.endAcc).toBe(0)
    expect(shot.outcome).toBe('green')
    expect(shot.endLie).toBe(5)
  })

  it('"Penalty" closes it as a penalty', () => {
    useStore.getState().finishShot('penalty')
    expect(log()[0].outcome).toBe('penalty')
    expect(log()[0].end).toEqual({ x: 27.5, y: 44 })
  })

  it('does nothing when no shot is open', () => {
    useStore.getState().finishShot('green')
    const before = useStore.getState().logs
    useStore.getState().finishShot('penalty')
    expect(useStore.getState().logs).toBe(before)
  })
})

describe('corrections', () => {
  beforeEach(() => {
    useStore.getState().setGps({ x: 27.5, y: 2.5, accuracy_m: 5 })
    useStore.getState().setBall({ x: 27.5, y: 2.5 })
    useStore.getState().hitShot(undefined, T0)
    useStore.getState().setGps({ x: 30, y: 22, accuracy_m: 9 })
    useStore.getState().setBall({ x: 30, y: 22 })
    useStore.getState().hitShot(undefined, T0 + 1)
  })

  it('dragging an end point moves it, sets accuracy 0, and moves the next start with it', () => {
    useStore.getState().moveShotEnd(KEY, 0, { x: 47, y: 24 })
    const [first, second] = log()
    expect(first.end).toEqual({ x: 47, y: 24 })
    expect(first.endAcc).toBe(0)
    expect(first.endLie).toBe(7) // the toy's OB column
    expect(second.start).toEqual({ x: 47, y: 24 })
    expect(second.startAcc).toBe(0)
    expect(first.startAcc).toBe(5)
  })

  it('ignores an open shot and an unknown index', () => {
    const before = useStore.getState().logs
    useStore.getState().moveShotEnd(KEY, 1, { x: 1, y: 1 })
    useStore.getState().moveShotEnd(KEY, 9, { x: 1, y: 1 })
    useStore.getState().moveShotEnd('2020-01-01:11', 0, { x: 1, y: 1 })
    expect(useStore.getState().logs).toBe(before)
  })

  it('setShotClub changes the club of the last shot; undoShot removes it and reopens the one before', () => {
    useStore.getState().setShotClub('pw', T0)
    expect(log()[1].club).toBe('pw')
    useStore.getState().undoShot(T0)
    expect(log()).toHaveLength(1)
    expect(log()[0].end).toBeNull()
    expect(log()[0].endAcc).toBeNull()
    expect(log()[0].endLie).toBeUndefined()
    useStore.getState().undoShot(T0)
    expect(log()).toEqual([])
  })

  it('clearLog drops one round and leaves the others', () => {
    useStore.setState({ logs: { ...useStore.getState().logs, other: [] } })
    useStore.getState().clearLog(KEY)
    expect(Object.keys(useStore.getState().logs)).toEqual(['other'])
  })
})

describe('persistence', () => {
  function fakeStorage() {
    const items = new Map<string, string>()
    return {
      items,
      getItem: (k: string) => items.get(k) ?? null,
      setItem: (k: string, v: string) => void items.set(k, v),
      removeItem: (k: string) => void items.delete(k),
    }
  }

  afterEach(() => {
    vi.unstubAllGlobals()
    vi.resetModules()
  })

  it('a reload restores the log and the learn toggle, and nothing else', async () => {
    const storage = fakeStorage()
    vi.stubGlobal('localStorage', storage)
    vi.resetModules()
    const first = await import('./store')
    first.useStore.setState({ bundle: readToyBundle(), player: toyPlayerDoc() })
    first.useStore.getState().setBall({ x: 27.5, y: 2.5 })
    first.useStore.getState().hitShot(undefined, T0)
    first.useStore.getState().setLearn(true)
    const saved = JSON.parse(storage.items.get(LOG_STORAGE_KEY) ?? '{}') as { state: Record<string, unknown> }
    expect(Object.keys(saved.state).sort()).toEqual(['learn', 'logs'])

    vi.resetModules()
    const second = await import('./store')
    expect(second.useStore).not.toBe(first.useStore)
    const s = second.useStore.getState()
    expect(s.learn).toBe(true)
    expect(s.logs[KEY]).toHaveLength(1)
    expect(s.logs[KEY][0].start).toEqual({ x: 27.5, y: 2.5 })
    expect(s.ball).toBeNull()
    expect(s.bundle).toBeNull()
  })

  it('works with no localStorage at all', () => {
    useStore.getState().setBall({ x: 27.5, y: 2.5 })
    useStore.getState().hitShot(undefined, T0)
    expect(log()).toHaveLength(1)
  })
})

describe('part 22: Hit logs the aim in force, and "Ball is here" confirms the finish', () => {
  beforeEach(() => useStore.getState().setBall({ x: 27.5, y: 2.5 }))

  it('with a moved target the shot carries the player\'s aim and the caddie\'s as recAimDeg', () => {
    const rec = useStore.getState().recommendation
    if (!rec) throw new Error('no recommendation')
    useStore.getState().setTarget({ x: 37.5, y: 12.5 }) // 45 degrees right of straight up
    useStore.getState().hitShot(undefined, T0)
    const [shot] = log()
    expect(shot.aimDeg).toBeCloseTo(45, 6)
    expect(shot.recAimDeg).toBeCloseTo(pinBearingDeg(readToyBundle(), { x: 27.5, y: 2.5 }) + rec.dir_deg, 9)
    expect(shot.club).toBe(rec.club) // the toy bag has one club
  })

  it('"Ball is here" closes the open shot where the ball is, as a normal shot, and starts nothing', () => {
    useStore.getState().hitShot(undefined, T0)
    useStore.getState().setBall({ x: 30, y: 24 })
    useStore.getState().finishShot('normal', T0 + 1)
    expect(log()).toHaveLength(1)
    expect(log()[0].end).toEqual({ x: 30, y: 24 })
    expect(log()[0].outcome).toBe('normal')
    expect(log()[0].endLie).toBe(2)
  })
})
