import { describe, expect, it } from 'vitest'

import { cellOf, centreOf, distance, lieAt, policyAt, valueNearest } from './grid'
import { CELL_M, COLS, ROWS, testBundle } from './testBundle'
import { readToyBundle } from './toyFiles'

describe('cellOf', () => {
  const b = testBundle()

  it('maps a point to its row, column and flat index', () => {
    expect(cellOf(b, { x: 12, y: 47 })).toEqual({ r: 9, c: 2, i: 92 })
    expect(cellOf(b, { x: 0.1, y: 0.1 })).toEqual({ r: 0, c: 0, i: 0 })
    expect(cellOf(b, { x: 27.5, y: 2.5 })).toEqual({ r: 0, c: 5, i: 5 })
  })

  it('treats a cell as the half-open range [k * cell_m, (k + 1) * cell_m)', () => {
    expect(cellOf(b, { x: 5, y: 10 })).toEqual({ r: 2, c: 1, i: 21 })
    expect(cellOf(b, { x: 4.999, y: 9.999 })).toEqual({ r: 1, c: 0, i: 10 })
  })

  it('clamps points outside the grid to the edge cells', () => {
    expect(cellOf(b, { x: -3, y: -3 })).toEqual({ r: 0, c: 0, i: 0 })
    expect(cellOf(b, { x: 60, y: 60 })).toEqual({ r: ROWS - 1, c: COLS - 1, i: ROWS * COLS - 1 })
    expect(cellOf(b, { x: 50, y: 20 })).toEqual({ r: 4, c: COLS - 1, i: 4 * COLS + COLS - 1 })
    expect(cellOf(b, { x: 20, y: 50 })).toEqual({ r: ROWS - 1, c: 4, i: (ROWS - 1) * COLS + 4 })
  })
})

describe('centreOf', () => {
  const b = testBundle()

  it('returns the cell centre at ((c + 0.5) cell_m, (r + 0.5) cell_m)', () => {
    expect(centreOf(b, 0, 0)).toEqual({ x: CELL_M / 2, y: CELL_M / 2 })
    expect(centreOf(b, 9, 2)).toEqual({ x: 12.5, y: 47.5 })
  })

  it('round-trips with cellOf', () => {
    for (let r = 0; r < ROWS; r++)
      for (let c = 0; c < COLS; c++) expect(cellOf(b, centreOf(b, r, c))).toEqual({ r, c, i: r * COLS + c })
  })
})

describe('distance', () => {
  it('is Euclidean', () => {
    expect(distance({ x: 0, y: 0 }, { x: 3, y: 4 })).toBe(5)
    expect(distance({ x: 1, y: 1 }, { x: 1, y: 1 })).toBe(0)
  })
})

describe('toy bundle lookups (public/data/toy/drop from solver part 08)', () => {
  const b = readToyBundle()
  const tee = { x: b.meta.tee_xy[0], y: b.meta.tee_xy[1] }
  const pin = { x: b.meta.pin_xy[0], y: b.meta.pin_xy[1] }

  it('has the expected shape', () => {
    expect(b.meta.rows * b.meta.cols).toBe(b.value.length)
    expect(b.meta.directions_deg).toHaveLength(91)
  })

  it('lieAt reads the lie code of the containing cell', () => {
    expect(lieAt(b, tee)).toBe(2) // the toy has no tee cells: fairway at row 0
    expect(lieAt(b, pin)).toBe(5)
    expect(lieAt(b, { x: 2.5, y: 37.5 })).toBe(6) // water, row 7 col 0
    expect(lieAt(b, { x: 47.5, y: 20 })).toBe(7) // OB column
    expect(lieAt(b, { x: 22.5, y: 27.5 })).toBe(4) // bunker (5, 4)
    expect(lieAt(b, { x: 99, y: 99 })).toBe(7) // clamped to the OB corner
  })

  it('valueNearest returns the containing cell value, NaN where there is no state', () => {
    expect(valueNearest(b, pin)).toBe(1.5)
    expect(valueNearest(b, tee)).toBe(b.value[cellOf(b, tee).i])
    expect(valueNearest(b, { x: 27.6, y: 2.4 })).toBe(valueNearest(b, tee))
    expect(valueNearest(b, { x: 2.5, y: 37.5 })).toBeNaN()
    expect(valueNearest(b, { x: 47.5, y: 20 })).toBeNaN()
  })

  it('policyAt names the club and the direction in degrees', () => {
    const p = policyAt(b, tee)
    expect(p).not.toBeNull()
    expect(p?.club).toBe('test7i')
    expect(p?.dir_deg).toBe(b.meta.directions_deg[b.dir[cellOf(b, tee).i]])
    expect(Number.isInteger(p?.dir_deg)).toBe(true)
    expect(Math.abs(p?.dir_deg ?? 999)).toBeLessThanOrEqual(90)
  })

  it('policyAt is null on terminal and OUT cells (255)', () => {
    expect(policyAt(b, pin)).toBeNull()
    expect(policyAt(b, { x: 47.5, y: 20 })).toBeNull()
    expect(policyAt(b, { x: 2.5, y: 37.5 })).toBeNull()
  })
})
