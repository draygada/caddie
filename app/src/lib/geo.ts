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
