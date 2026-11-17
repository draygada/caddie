import { afterEach, beforeEach, describe, expect, it } from 'vitest'

import { TARGET_RESET_M } from './lib/aim'
import { readToyBundle, toyPlayerDoc } from './lib/toyFiles'
import { initialState, useStore } from './store'

beforeEach(() => useStore.setState({ ...initialState, bundle: readToyBundle(), player: toyPlayerDoc(), ball: { x: 27.5, y: 2.5 } }))
afterEach(() => useStore.setState(initialState))

describe('target and aimClub (part 22)', () => {
  it('start as the caddie\'s aim: no target, automatic club', () => {
    expect(useStore.getState().target).toBeNull()
    expect(useStore.getState().aimClub).toBeNull()
  })

  it('setTarget and setAimClub store the player\'s aim; resetAim clears both', () => {
    useStore.getState().setTarget({ x: 20, y: 30 })
    useStore.getState().setAimClub('test7i')
    expect(useStore.getState().target).toEqual({ x: 20, y: 30 })
    expect(useStore.getState().aimClub).toBe('test7i')
    useStore.getState().resetAim()
    expect(useStore.getState().target).toBeNull()
    expect(useStore.getState().aimClub).toBeNull()
  })

  it('keeps the aim while the ball only jitters, and drops it once the ball has moved 15 m', () => {
    expect(TARGET_RESET_M).toBe(15)
    useStore.getState().setTarget({ x: 20, y: 30 })
    useStore.getState().setAimClub('test7i')
    useStore.getState().setBall({ x: 27.5, y: 10 }) // 7.5 m
    expect(useStore.getState().target).toEqual({ x: 20, y: 30 })
    useStore.getState().setBall({ x: 27.5, y: 16 }) // 13.5 m from where the target was set
    expect(useStore.getState().target).not.toBeNull()
    useStore.getState().setBall({ x: 27.5, y: 18 }) // 15.5 m
    expect(useStore.getState().target).toBeNull()
    expect(useStore.getState().aimClub).toBeNull()
  })

  it('measures from the ball position when the aim was last touched', () => {
    useStore.getState().setTarget({ x: 20, y: 30 })
    useStore.getState().setBall({ x: 27.5, y: 14 })
    useStore.getState().setTarget({ x: 22, y: 40 }) // re-aimed from here
    useStore.getState().setBall({ x: 27.5, y: 24 }) // 10 m from the re-aim, 21.5 m from the first
    expect(useStore.getState().target).toEqual({ x: 22, y: 40 })
  })

  it('drops the aim when the hole changes', () => {
    useStore.getState().setTarget({ x: 20, y: 30 })
    useStore.setState({ bundle: readToyBundle() })
    expect(useStore.getState().target).toBeNull()
  })
})
