import { describe, expect, it } from 'vitest'

import { createHandler, RolloutClient, type WorkerLike, type WorkerRequest, type WorkerResponse } from './rollout'
import { readToyBundle, toyPlayerDoc } from './toyFiles'

const b = readToyBundle()
const player = toyPlayerDoc()

/** In-process stand-in for a Web Worker running rollout.worker.ts. */
class FakeWorker implements WorkerLike {
  onmessage: ((e: MessageEvent<WorkerResponse>) => void) | null = null
  received: WorkerRequest[] = []
  private readonly handle = createHandler()
  constructor(private readonly delayMs = 0) {}
  postMessage(msg: WorkerRequest) {
    this.received.push(msg)
    const post = (out: WorkerResponse) => {
      setTimeout(() => this.onmessage?.({ data: out } as MessageEvent<WorkerResponse>), this.delayMs)
    }
    this.handle(msg, post)
  }
  terminate() {
    this.onmessage = null
  }
}

describe('createHandler', () => {
  it('caches the bundle and answers recommend requests with the requestId', () => {
    const handleMessage = createHandler()
    const out: WorkerResponse[] = []
    const post = (m: WorkerResponse) => out.push(m)
    handleMessage({ type: 'bundle', bundle: b }, post)
    expect(out).toEqual([])
    handleMessage(
      { type: 'recommend', requestId: 7, player, from: { x: 27.5, y: 2.5 }, lie: 2, mode: 'drop', m: 20, seed: 1 },
      post,
    )
    expect(out).toHaveLength(1)
    expect(out[0].requestId).toBe(7)
    expect(out[0].result?.club).toBe('test7i')
    expect(out[0].error).toBeUndefined()
  })

  it('reports an error when no bundle was sent', () => {
    const handleMessage = createHandler()
    const out: WorkerResponse[] = []
    handleMessage(
      { type: 'recommend', requestId: 1, player, from: { x: 1, y: 1 }, lie: 2, mode: 'drop', m: 5, seed: 1 },
      (m) => out.push(m),
    )
    expect(out[0].result).toBeUndefined()
    expect(out[0].error).toMatch(/bundle/)
  })
})

describe('RolloutClient', () => {
  it('round-trips a request and sends the bundle only once', async () => {
    const w = new FakeWorker()
    const client = new RolloutClient(() => w)
    client.setBundle(b)
    const r1 = await client.recommend(player, { x: 27.5, y: 2.5 }, 2, 'drop', 20, 1)
    const r2 = await client.recommend(player, { x: 12, y: 17 }, 2, 'drop', 20, 1)
    expect(r1?.club).toBe('test7i')
    expect(r2?.club).toBe('test7i')
    expect(w.received.filter((m) => m.type === 'bundle')).toHaveLength(1)
    expect(w.received.filter((m) => m.type === 'recommend')).toHaveLength(2)
  })

  it('drops stale results: only the latest request resolves with a result', async () => {
    const w = new FakeWorker(5)
    const client = new RolloutClient(() => w)
    client.setBundle(b)
    const first = client.recommend(player, { x: 27.5, y: 2.5 }, 2, 'drop', 20, 1)
    const second = client.recommend(player, { x: 12, y: 17 }, 2, 'drop', 20, 1)
    const [a, c] = await Promise.all([first, second])
    expect(a).toBeNull()
    expect(c).not.toBeNull()
  })

  it('re-sends the bundle after it changes', async () => {
    const w = new FakeWorker()
    const client = new RolloutClient(() => w)
    client.setBundle(b)
    await client.recommend(player, { x: 27.5, y: 2.5 }, 2, 'drop', 5, 1)
    client.setBundle({ ...b })
    await client.recommend(player, { x: 27.5, y: 2.5 }, 2, 'drop', 5, 1)
    expect(w.received.filter((m) => m.type === 'bundle')).toHaveLength(2)
  })

  it('rejects when the worker reports an error', async () => {
    const w = new FakeWorker()
    const client = new RolloutClient(() => w)
    await expect(client.recommend(player, { x: 1, y: 1 }, 2, 'drop', 5, 1)).rejects.toThrow(/bundle/)
  })
})
