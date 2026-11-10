import { describe, expect, it } from 'vitest'

import { cellOf, centreOf, distance, lieAt, policyAt, valueBilinear, valueNearest } from './grid'
import type { HoleBundle } from './types'
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

describe('valueBilinear (Alg 8.6 on cell centres)', () => {
  function yField(): HoleBundle {
    const b = testBundle()
    for (let r = 0; r < ROWS; r++) for (let c = 0; c < COLS; c++) b.value[r * COLS + c] = (r + 0.5) * CELL_M
    return b
  }

  it('reproduces a field equal to y at any point between the outer centres', () => {
    const b = yField()
    for (const p of [
      { x: 2.5, y: 2.5 },
      { x: 12, y: 47.5 },
      { x: 31.3, y: 17.77 },
      { x: 0, y: 30 },
      { x: 49.9, y: 44.4 },
      { x: 26, y: 2.5 },
    ])
      expect(valueBilinear(b, p)).toBeCloseTo(p.y, 6)
  })

  it('clamps to the outer centres beyond them instead of extrapolating', () => {
    const b = yField()
    expect(valueBilinear(b, { x: 10, y: 0 })).toBeCloseTo(2.5, 6)
    expect(valueBilinear(b, { x: 10, y: 60 })).toBeCloseTo(47.5, 6)
  })

  it('equals the cell value at every cell centre', () => {
    const b = readToyBundle()
    for (let r = 0; r < b.meta.rows; r++)
      for (let c = 0; c < b.meta.cols - 1; c++) {
        const v = valueBilinear(b, centreOf(b, r, c))
        const want = b.value[r * b.meta.cols + c]
        if (Number.isNaN(want)) expect(Number.isNaN(v) || Number.isFinite(v)).toBe(true)
        else expect(v).toBeCloseTo(want, 5)
      }
  })

  it('replaces NaN neighbours with the nearest finite of the four', () => {
    const b = yField()
    b.value[0] = NaN // corner cell (0, 0)
    const v = valueBilinear(b, { x: 3, y: 3 })
    expect(Number.isFinite(v)).toBe(true)
    expect(v).toBeGreaterThanOrEqual(2.5)
    expect(v).toBeLessThanOrEqual(7.5)
    // the toy's OB column 9 is NaN: a point between columns 8 and 9 stays finite
    const toy = readToyBundle()
    expect(Number.isFinite(valueBilinear(toy, { x: 46, y: 22 }))).toBe(true)
    expect(valueBilinear(toy, { x: 27.5, y: 47.5 })).toBeCloseTo(1.5, 6)
  })

  it('is NaN only when all four neighbours are NaN', () => {
    const b = yField()
    b.value.fill(NaN)
    expect(valueBilinear(b, { x: 20, y: 20 })).toBeNaN()
  })
})
