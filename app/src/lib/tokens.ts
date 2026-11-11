/**
 * Read design tokens that live as CSS variables (docs/design.md section 3) for code that
 * cannot use CSS, such as MapLibre paint properties. Falls back to the reference values
 * so tests and server renders get the same colours.
 */
export const TOKEN_FALLBACK: Record<string, string> = {
  '--t-fairway': '#7fbf6a',
  '--t-rough': '#4f8a3f',
  '--t-green': '#a8e08d',
  '--t-bunker': '#e6d3a3',
  '--t-water': '#4c9be8',
  '--t-ob': '#c8102e',
  '--t-tee': '#dadada',
  '--color-rec': '#0a7c3e',
  '--color-rec-ink': '#ffffff',
  '--ball': '#ffffff',
  '--pin': '#111714',
  '--color-ink': '#111714',
}

export function token(name: string): string {
  if (typeof document === 'undefined') return TOKEN_FALLBACK[name] ?? '#000000'
  const v = getComputedStyle(document.documentElement).getPropertyValue(name).trim()
  return v || TOKEN_FALLBACK[name] || '#000000'
}

/** Club ids from player.json as the names on the sticks (docs/design.md section 7). */
export function clubDisplayName(id: string): string {
  const fixed: Record<string, string> = {
    driver: 'Driver',
    pw: 'Pitching wedge',
    sw: 'Sand wedge',
    gw: 'Gap wedge',
    lw: 'Lob wedge',
  }
  if (id in fixed) return fixed[id]
  let m = /^(\d+)w$/.exec(id)
  if (m) return `${m[1]} wood`
  m = /^(\d+)h$/.exec(id)
  if (m) return `${m[1]} hybrid`
  m = /^(\d+)i$/.exec(id)
  if (m) return `${m[1]} iron`
  m = /^(sw|pw|lw|gw)(\d+)$/.exec(id)
  if (m) return `${fixed[m[1]]}, ${m[2]} yd`
  m = /^test(\d+)i$/.exec(id)
  if (m) return `Test ${m[1]} iron`
  return id.charAt(0).toUpperCase() + id.slice(1)
}

export const MODE_LABEL: Record<string, string> = {
  mulligan: 'Mulligan',
  drop: 'Drop',
  replay: 'Replay',
}

export const MODE_HELP: Record<string, string> = {
  mulligan: 'Water or out of bounds: hit again from the same spot, no penalty',
  drop: 'Water or out of bounds: drop at the nearest fairway on the entry side, one stroke',
  replay: 'Water or out of bounds: hit again from the same spot, one stroke',
}
