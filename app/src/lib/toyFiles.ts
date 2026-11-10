/** Test helper: read the committed toy bundle from public/data with node fs (no fetch). */
import { readFileSync } from 'node:fs'
import { dirname, join } from 'node:path'
import { fileURLToPath } from 'node:url'

import type { HoleBundle, Meta, Mode, Player } from './types'

export const DATA_DIR = join(dirname(fileURLToPath(import.meta.url)), '..', '..', 'public', 'data')

export function toyFile(name: string, hole = 'toy', mode: Mode = 'drop'): Buffer {
  return readFileSync(join(DATA_DIR, hole, mode, name))
}

export function toyPlayerDoc(): Player {
  return JSON.parse(readFileSync(join(DATA_DIR, 'player.json'), 'utf8')) as Player
}

/** A fresh ArrayBuffer at byte offset 0, as `Response.arrayBuffer()` would give. */
export function toArrayBuffer(buf: Buffer): ArrayBuffer {
  return buf.buffer.slice(buf.byteOffset, buf.byteOffset + buf.byteLength) as ArrayBuffer
}

export function readToyBundle(): HoleBundle {
  const meta = JSON.parse(toyFile('meta.json').toString('utf8')) as Meta
  return {
    meta,
    lie: new Uint8Array(toArrayBuffer(toyFile('lie.u8'))),
    value: new Float32Array(toArrayBuffer(toyFile('value.f32'))),
    club: new Uint8Array(toArrayBuffer(toyFile('club.u8'))),
    dir: new Uint8Array(toArrayBuffer(toyFile('dir.u8'))),
  }
}
