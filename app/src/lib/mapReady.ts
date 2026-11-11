/**
 * Run `fn` once the map style can take source and layer edits. MapLibre's `load` event
 * fires once per map, so a second bundle that arrives while tiles or an image source are
 * still loading must wait on `idle` instead; `idle` fires after every settle. Returns a
 * cancel for effect cleanup.
 */
export interface StyleReadyMap {
  isStyleLoaded: () => unknown
  once: (ev: 'idle', fn: () => void) => unknown
  off: (ev: 'idle', fn: () => void) => unknown
}

export function whenStyleReady(map: StyleReadyMap, fn: () => void): () => void {
  if (map.isStyleLoaded()) {
    fn()
    return () => undefined
  }
  map.once('idle', fn)
  return () => {
    map.off('idle', fn)
  }
}
