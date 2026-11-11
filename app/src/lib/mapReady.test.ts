import { describe, expect, it, vi } from 'vitest'

import { whenStyleReady } from './mapReady'

function fakeMap(loaded: boolean) {
  const handlers = new Map<string, (() => void)[]>()
  return {
    isStyleLoaded: () => loaded,
    once: vi.fn((ev: string, fn: () => void) => {
      handlers.set(ev, [...(handlers.get(ev) ?? []), fn])
    }),
    off: vi.fn((ev: string, fn: () => void) => {
      handlers.set(ev, (handlers.get(ev) ?? []).filter((f) => f !== fn))
    }),
    fire: (ev: string) => {
      const fns = handlers.get(ev) ?? []
      handlers.set(ev, [])
      for (const f of fns) f()
    },
  }
}

describe('whenStyleReady', () => {
  it('runs at once when the style is loaded', () => {
    const map = fakeMap(true)
    const fn = vi.fn()
    whenStyleReady(map, fn)
    expect(fn).toHaveBeenCalledTimes(1)
    expect(map.once).not.toHaveBeenCalled()
  })

  it('waits for idle, not load, when the style is busy (load fires only once per map)', () => {
    const map = fakeMap(false)
    const fn = vi.fn()
    whenStyleReady(map, fn)
    expect(fn).not.toHaveBeenCalled()
    map.fire('load')
    expect(fn).not.toHaveBeenCalled()
    map.fire('idle')
    expect(fn).toHaveBeenCalledTimes(1)
  })

  it('returns a cancel that removes the pending handler', () => {
    const map = fakeMap(false)
    const fn = vi.fn()
    const cancel = whenStyleReady(map, fn)
    cancel()
    map.fire('idle')
    expect(fn).not.toHaveBeenCalled()
    expect(map.off).toHaveBeenCalledWith('idle', expect.any(Function))
  })
})
