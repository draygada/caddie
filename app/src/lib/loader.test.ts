import { afterEach, describe, expect, it, vi } from 'vitest'

import { loadBundle, loadPlayer } from './loader'
import { toArrayBuffer, toyFile, toyPlayerDoc } from './toyFiles'
import { DATA_DIR } from './toyFiles'
import { readFileSync } from 'node:fs'
import { join } from 'node:path'

/** fetch stub serving /data/... from public/data, 404 elsewhere. */
function stubFetch(missing: string[] = []) {
  const calls: string[] = []
  vi.stubGlobal(
    'fetch',
    vi.fn(async (input: string | URL | Request) => {
      const url = typeof input === 'string' ? input : input instanceof URL ? input.href : input.url
      calls.push(url)
      const rel = url.replace(/^\/data\//, '')
      if (missing.some((m) => url.endsWith(m))) return new Response('not found', { status: 404 })
      let body: Buffer
      try {
        body = readFileSync(join(DATA_DIR, rel))
      } catch {
        return new Response('not found', { status: 404 })
      }
      return new Response(toArrayBuffer(body), { status: 200 })
    }),
  )
  return calls
}

afterEach(() => vi.unstubAllGlobals())

describe('loadPlayer', () => {
  it('fetches base/player.json and parses it', async () => {
    const calls = stubFetch()
    const player = await loadPlayer()
    expect(calls).toEqual(['/data/player.json'])
    expect(player).toEqual(toyPlayerDoc())
    expect(player.club_order).toEqual(['test7i'])
  })

  it('honours a custom base', async () => {
    const calls = stubFetch()
    await loadPlayer('/data')
    expect(calls[0]).toBe('/data/player.json')
  })

  it('throws a clear error when the file is missing', async () => {
    stubFetch(['player.json'])
    await expect(loadPlayer()).rejects.toThrow(/player\.json.*404/)
  })
})

describe('loadBundle', () => {
  it('fetches meta.json then the four binaries into typed arrays of length rows * cols', async () => {
    const calls = stubFetch()
    const b = await loadBundle('toy', 'drop')
    expect(calls[0]).toBe('/data/toy/drop/meta.json')
    expect(new Set(calls.slice(1))).toEqual(
      new Set(['/data/toy/drop/lie.u8', '/data/toy/drop/value.f32', '/data/toy/drop/club.u8', '/data/toy/drop/dir.u8']),
    )
    const n = b.meta.rows * b.meta.cols
    expect(b.meta.hole).toBe('toy')
    expect(b.lie).toBeInstanceOf(Uint8Array)
    expect(b.value).toBeInstanceOf(Float32Array)
    expect(b.club).toBeInstanceOf(Uint8Array)
    expect(b.dir).toBeInstanceOf(Uint8Array)
    expect([b.lie.length, b.value.length, b.club.length, b.dir.length]).toEqual([n, n, n, n])
    expect(b.value.byteOffset).toBe(0)
    expect(Array.from(b.lie)).toEqual(Array.from(new Uint8Array(toArrayBuffer(toyFile('lie.u8')))))
    expect(b.value[95]).toBe(1.5) // pin cell (9, 5)
  })

  it('addresses real holes by number', async () => {
    const calls = stubFetch(['10/drop/meta.json'])
    await expect(loadBundle(10, 'drop')).rejects.toThrow(/\/data\/10\/drop\/meta\.json.*404/)
    expect(calls[0]).toBe('/data/10/drop/meta.json')
  })

  it('throws a clear error on a missing binary', async () => {
    stubFetch(['value.f32'])
    await expect(loadBundle('toy', 'drop')).rejects.toThrow(/value\.f32.*404/)
  })

  it('throws when a binary length does not match rows * cols', async () => {
    const calls = stubFetch()
    const real = globalThis.fetch
    vi.stubGlobal('fetch', async (input: string) => {
      if (input.endsWith('club.u8')) return new Response(new Uint8Array(7).buffer, { status: 200 })
      return real(input)
    })
    await expect(loadBundle('toy', 'drop')).rejects.toThrow(/club\.u8.*7.*100/)
    expect(calls.length).toBeGreaterThan(0)
  })
})
