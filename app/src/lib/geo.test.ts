import { describe, expect, it } from 'vitest'

import geoPoints from '../../../docs/fixtures/geo_points.json'
import { FRAME_MARGIN_M, frameZoom, gridCorners, gridToLonLat, holeFrame, lonLatToGrid, metresBetween } from './geo'
import { testMeta } from './testBundle'

/** Meta for the fixture frame: origin at the Black tee, +y toward the pin. */
const fixtureMeta = testMeta({
  hole: geoPoints.hole,
  origin: geoPoints.origin,
  rotation_deg: geoPoints.rotation_deg,
})

describe('gridToLonLat and lonLatToGrid', () => {
  it('round-trip to 1e-6 degrees and 1e-3 m', () => {
    for (const m of [fixtureMeta, testMeta({ origin: { lat: 37.42, lon: -122.18 }, rotation_deg: 212 })])
      for (const p of [
        { x: 0, y: 0 },
        { x: 90, y: 320 },
        { x: -19.46, y: 207.994 },
        { x: 400, y: -50 },
      ]) {
        const ll = gridToLonLat(m, p)
        const back = lonLatToGrid(m, ll.lon, ll.lat)
        expect(back.x).toBeCloseTo(p.x, 3)
        expect(back.y).toBeCloseTo(p.y, 3)
        const again = gridToLonLat(m, back)
        expect(again.lon).toBeCloseTo(ll.lon, 6)
        expect(again.lat).toBeCloseTo(ll.lat, 6)
      }
  })

  it('maps the origin to origin.lon/lat', () => {
    const ll = gridToLonLat(fixtureMeta, { x: 0, y: 0 })
    expect(ll.lon).toBe(geoPoints.origin.lon)
    expect(ll.lat).toBe(geoPoints.origin.lat)
  })

  it('with rotation 0, +y is north and +x is east', () => {
    const m = testMeta({ origin: { lat: 37.42, lon: -122.18 }, rotation_deg: 0 })
    const north = gridToLonLat(m, { x: 0, y: 100 })
    expect(north.lat).toBeGreaterThan(m.origin.lat)
    expect(north.lon).toBeCloseTo(m.origin.lon, 9)
    const east = gridToLonLat(m, { x: 100, y: 0 })
    expect(east.lon).toBeGreaterThan(m.origin.lon)
    expect(east.lat).toBeCloseTo(m.origin.lat, 9)
  })
})

describe('docs/fixtures/geo_points.json (the arbiter of the rotation sign)', () => {
  for (const pt of geoPoints.points) {
    it(`${pt.name}: grid to lon/lat within 1 m`, () => {
      const ll = gridToLonLat(fixtureMeta, { x: pt.x, y: pt.y })
      expect(metresBetween(ll, pt)).toBeLessThan(1.0)
    })
    it(`${pt.name}: lon/lat to grid within 1 m`, () => {
      const xy = lonLatToGrid(fixtureMeta, pt.lon, pt.lat)
      expect(Math.hypot(xy.x - pt.x, xy.y - pt.y)).toBeLessThan(1.0)
    })
    // The part file asks for 0.5 m. The contract's 111320 m per degree of latitude is
    // about 0.3 percent long at 37.4 N, which puts the pin 0.8 m off at 312 m. Strict
    // expected failure until Diego decides whether the contract constant changes.
    it.fails(`${pt.name}: within 0.5 m (part file band)`, () => {
      const ll = gridToLonLat(fixtureMeta, { x: pt.x, y: pt.y })
      expect(metresBetween(ll, pt)).toBeLessThan(0.5)
    })
  }
})

describe('gridCorners', () => {
  it('returns TL, TR, BR, BL for rotation 0: TL is the max-y, min-x corner', () => {
    const m = testMeta({ origin: { lat: 37.42, lon: -122.18 }, rotation_deg: 0 })
    const [tl, tr, br, bl] = gridCorners(m)
    const w = m.cols * m.cell_m
    const h = m.rows * m.cell_m
    const want = {
      tl: gridToLonLat(m, { x: 0, y: h }),
      tr: gridToLonLat(m, { x: w, y: h }),
      br: gridToLonLat(m, { x: w, y: 0 }),
      bl: gridToLonLat(m, { x: 0, y: 0 }),
    }
    expect(tl).toEqual([want.tl.lon, want.tl.lat])
    expect(tr).toEqual([want.tr.lon, want.tr.lat])
    expect(br).toEqual([want.br.lon, want.br.lat])
    expect(bl).toEqual([want.bl.lon, want.bl.lat])
    expect(tl[1]).toBeGreaterThan(bl[1]) // TL is north of BL
    expect(tr[0]).toBeGreaterThan(tl[0]) // TR is east of TL
    expect(bl).toEqual([m.origin.lon, m.origin.lat])
  })

  it('rotates with the hole: for the fixture frame the far edge lies up the pin bearing', () => {
    const [tl, , , bl] = gridCorners(fixtureMeta)
    // pin bearing 327.6 deg: the far corners are north and west of the near ones
    expect(tl[1]).toBeGreaterThan(bl[1])
    expect(tl[0]).toBeLessThan(bl[0])
  })
})

describe('holeFrame (the default view)', () => {
  const meta = testMeta({
    rows: 80,
    cols: 40,
    tee_xy: [100, 50],
    tees: { black: [100, 50], white: [98, 70] },
    pin_xy: [105, 360],
    polygons: { fairway: [[[90, 80], [120, 80], [118, 330], [88, 330], [90, 80]]], green: [], rough: [[[0, 0], [200, 0], [200, 400], [0, 400], [0, 0]]] },
  })

  it('boxes the tees, the pin, the fairway and the green with a margin, not the whole grid', () => {
    const f = holeFrame(meta)
    expect(f).toEqual({ x0: 88 - FRAME_MARGIN_M, y0: 50 - FRAME_MARGIN_M, x1: 120 + FRAME_MARGIN_M, y1: 360 + FRAME_MARGIN_M })
    expect(f.x1 - f.x0).toBeLessThan(meta.cols * meta.cell_m)
  })

  it('never reaches outside the grid', () => {
    const tight = holeFrame({ ...meta, tee_xy: [2, 3], tees: { black: [2, 3] }, pin_xy: [198, 399] })
    expect(tight.x0).toBe(0)
    expect(tight.y0).toBe(0)
    expect(tight.x1).toBe(200)
    expect(tight.y1).toBe(400)
  })

  it('works with no polygons at all: tee to pin', () => {
    const f = holeFrame({ ...meta, polygons: {} })
    expect(f.x0).toBe(98 - FRAME_MARGIN_M)
    expect(f.x1).toBe(105 + FRAME_MARGIN_M)
  })
})

describe('frameZoom', () => {
  it('is the zoom at which the box just fits the space, on the tighter side', () => {
    const lat = 37.4
    const z = frameZoom(60, 340, 327, 454, lat)
    const mpp = (40075016.686 * Math.cos((lat * Math.PI) / 180)) / (512 * 2 ** z)
    expect(340 / mpp).toBeCloseTo(454, 6) // height binds
    expect(60 / mpp).toBeLessThan(327)
    const wide = frameZoom(340, 60, 327, 454, lat)
    expect(wide).toBeLessThan(z) // width binds, so it has to sit further out
  })

  it('one zoom level in halves the ground covered', () => {
    expect(frameZoom(100, 100, 400, 400, 0) - frameZoom(200, 200, 400, 400, 0)).toBeCloseTo(1, 9)
  })
})
