import { describe, expect, it } from 'vitest'

import { cellOf, centreOf, distance } from './grid'
import { CELL_M, COLS, ROWS, testBundle } from './testBundle'

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
