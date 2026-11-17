import { afterEach, describe, expect, it, vi } from 'vitest'

import { initialState, LOG_STORAGE_KEY, useStore } from './store'

afterEach(() => {
  useStore.setState(initialState)
  vi.unstubAllGlobals()
  vi.resetModules()
})

describe('screen (part 21)', () => {
  it('starts on home and setScreen moves between the three screens', () => {
    expect(useStore.getState().screen).toBe('home')
    useStore.getState().setScreen('simulate')
    expect(useStore.getState().screen).toBe('simulate')
    useStore.getState().setScreen('play')
    expect(useStore.getState().screen).toBe('play')
    useStore.getState().setScreen('home')
    expect(useStore.getState().screen).toBe('home')
  })

  it('is never persisted: a reload always opens on home', async () => {
    const items = new Map<string, string>()
    vi.stubGlobal('localStorage', {
      getItem: (k: string) => items.get(k) ?? null,
      setItem: (k: string, v: string) => void items.set(k, v),
      removeItem: (k: string) => void items.delete(k),
    })
    vi.resetModules()
    const first = await import('./store')
    first.useStore.getState().setScreen('play')
    expect(items.get(LOG_STORAGE_KEY)).not.toMatch(/screen/)
    vi.resetModules()
    const second = await import('./store')
    expect(second.useStore.getState().screen).toBe('home')
  })
})
