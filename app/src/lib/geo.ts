/**
 * Grid metres to lon/lat and back, per the root CLAUDE.md data contract.
 *
 * Grid frame: origin at `meta.origin`, +y along the hole bearing `rotation_deg`
 * (degrees clockwise from north), +x to the golfer's right. The rotation here is the
 * inverse of `rotate` in solver/caddie/geometry.py, so that both halves agree; the
 * three points in docs/fixtures/geo_points.json are the arbiter (see geo.test.ts).
 */
import type { Meta, XY } from './types'

/** Metres per degree of latitude in the contract formula. */
export const M_PER_DEG_LAT = 111320

export interface LonLat {
  lon: number
  lat: number
}

function mPerDegLon(lat: number): number {
  return M_PER_DEG_LAT * Math.cos((lat * Math.PI) / 180)
}

/** Grid (x, y) to local (east, north) metres: the inverse of the solver's `rotate`. */
export function gridToEastNorth(m: Meta, p: XY): { east: number; north: number } {
  const b = (m.rotation_deg * Math.PI) / 180
  return {
    east: p.x * Math.cos(b) + p.y * Math.sin(b),
    north: -p.x * Math.sin(b) + p.y * Math.cos(b),
  }
}

export function eastNorthToGrid(m: Meta, east: number, north: number): XY {
  const b = (m.rotation_deg * Math.PI) / 180
  return {
    x: east * Math.cos(b) - north * Math.sin(b),
    y: east * Math.sin(b) + north * Math.cos(b),
  }
}

export function gridToLonLat(m: Meta, p: XY): LonLat {
  const { east, north } = gridToEastNorth(m, p)
  return {
    lat: m.origin.lat + north / M_PER_DEG_LAT,
    lon: m.origin.lon + east / mPerDegLon(m.origin.lat),
  }
}

export function lonLatToGrid(m: Meta, lon: number, lat: number): XY {
  const north = (lat - m.origin.lat) * M_PER_DEG_LAT
  const east = (lon - m.origin.lon) * mPerDegLon(m.origin.lat)
  return eastNorthToGrid(m, east, north)
}

/** Approximate ground distance between two lon/lat points, metres (same flat formula). */
export function metresBetween(a: LonLat, b: LonLat): number {
  const north = (a.lat - b.lat) * M_PER_DEG_LAT
  const east = (a.lon - b.lon) * mPerDegLon((a.lat + b.lat) / 2)
  return Math.hypot(east, north)
}

export type Corners = [[number, number], [number, number], [number, number], [number, number]]

/**
 * Lon/lat of the four grid corners in the order MapLibre image sources expect:
 * top-left, top-right, bottom-right, bottom-left, where "top" is the far (max-y) edge
 * and "left" is min-x in grid coordinates.
 */
export function gridCorners(m: Meta): Corners {
  const w = m.cols * m.cell_m
  const h = m.rows * m.cell_m
  const ll = (p: XY): [number, number] => {
    const q = gridToLonLat(m, p)
    return [q.lon, q.lat]
  }
  return [ll({ x: 0, y: h }), ll({ x: w, y: h }), ll({ x: w, y: 0 }), ll({ x: 0, y: 0 })]
}

/** Room left around the hole in the default view, in meters. */
export const FRAME_MARGIN_M = 15
/** The polygon kinds that are the hole itself; rough and hazards spread far wider. */
const FRAME_KINDS = ['fairway', 'green', 'tee']

/**
 * The box the map opens on, in grid meters: every tee, the pin, the fairway and the green,
 * plus a margin, clamped to the grid. Much tighter than the grid, which carries wide rough
 * and out-of-bounds margins on every side.
 */
export function holeFrame(m: Meta): { x0: number; y0: number; x1: number; y1: number } {
  const pts: [number, number][] = [m.tee_xy, m.pin_xy, ...Object.values(m.tees)]
  for (const kind of FRAME_KINDS) for (const ring of m.polygons[kind] ?? []) pts.push(...ring)
  const xs = pts.map((p) => p[0])
  const ys = pts.map((p) => p[1])
  const w = m.cols * m.cell_m
  const h = m.rows * m.cell_m
  return {
    x0: Math.max(0, Math.min(...xs) - FRAME_MARGIN_M),
    y0: Math.max(0, Math.min(...ys) - FRAME_MARGIN_M),
    x1: Math.min(w, Math.max(...xs) + FRAME_MARGIN_M),
    y1: Math.min(h, Math.max(...ys) + FRAME_MARGIN_M),
  }
}

const EARTH_CIRCUMFERENCE_M = 40075016.686
const TILE_PX = 512

/**
 * The MapLibre zoom at which a `widthM` x `heightM` box of ground just fits `availW` x
 * `availH` screen pixels at latitude `lat`. Computed here because `fitBounds` fits the
 * north-up bounding box of the corners, which is far looser than a rotated hole.
 */
export function frameZoom(widthM: number, heightM: number, availW: number, availH: number, lat: number): number {
  const mpp = Math.max(widthM / Math.max(availW, 1), heightM / Math.max(availH, 1))
  return Math.log2((EARTH_CIRCUMFERENCE_M * Math.cos((lat * Math.PI) / 180)) / (TILE_PX * mpp))
}
