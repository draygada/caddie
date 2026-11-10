/**
 * Fetch `player.json` and a hole bundle from `base` (default `/data`, i.e. public/data).
 * The only place in the app that fetches; components read the store (part 11).
 */
import type { HoleBundle, Meta, Mode, Player } from './types'

async function fetchOk(url: string): Promise<Response> {
  const res = await fetch(url)
  if (!res.ok) throw new Error(`fetch ${url}: ${res.status} ${res.statusText}`.trim())
  return res
}

async function fetchJson<T>(url: string): Promise<T> {
  return (await (await fetchOk(url)).json()) as T
}

/** `response.arrayBuffer()` gives byte offset 0, as Float32Array requires. */
async function fetchBytes(url: string, expected: number, bytesPer: number): Promise<ArrayBuffer> {
  const buf = await (await fetchOk(url)).arrayBuffer()
  const n = buf.byteLength / bytesPer
  if (buf.byteLength % bytesPer !== 0 || n !== expected) {
    throw new Error(`${url}: ${n} values (${buf.byteLength} bytes), expected ${expected}`)
  }
  return buf
}

export async function loadPlayer(base = '/data'): Promise<Player> {
  return fetchJson<Player>(`${base}/player.json`)
}

export async function loadBundle(hole: number | 'toy', mode: Mode, base = '/data'): Promise<HoleBundle> {
  const dir = `${base}/${hole}/${mode}`
  const meta = await fetchJson<Meta>(`${dir}/meta.json`)
  const n = meta.rows * meta.cols
  const [lie, value, club, dir_] = await Promise.all([
    fetchBytes(`${dir}/lie.u8`, n, 1),
    fetchBytes(`${dir}/value.f32`, n, 4),
    fetchBytes(`${dir}/club.u8`, n, 1),
    fetchBytes(`${dir}/dir.u8`, n, 1),
  ])
  return {
    meta,
    lie: new Uint8Array(lie),
    value: new Float32Array(value),
    club: new Uint8Array(club),
    dir: new Uint8Array(dir_),
  }
}
