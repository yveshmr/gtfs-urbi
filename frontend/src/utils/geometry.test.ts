import { describe, expect, it } from 'vitest'

import { sliceLineBetweenFractions, splitLineAtFraction } from './geometry'

describe('line geometry helpers', () => {
  const line: [number, number][] = [
    [0, 0],
    [1, 0],
    [2, 0],
  ]

  it('splits a line at the projected vehicle fraction', () => {
    const result = splitLineAtFraction(line, 0.25)

    expect(result.completed).toEqual([
      [0, 0],
      [0.5, 0],
    ])
    expect(result.remaining).toEqual([
      [0.5, 0],
      [1, 0],
      [2, 0],
    ])
  })

  it('extracts a current segment between stop fractions', () => {
    expect(sliceLineBetweenFractions(line, 0.25, 0.75)).toEqual([
      [0.5, 0],
      [1, 0],
      [1.5, 0],
    ])
  })
})
