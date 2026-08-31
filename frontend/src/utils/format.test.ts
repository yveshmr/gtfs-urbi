import { describe, expect, it } from 'vitest'

import { formatDistance, formatMinutes, formatPercent } from './format'

describe('operational formatters', () => {
  it('formats ETA durations', () => {
    expect(formatMinutes(540)).toBe('9 min')
    expect(formatMinutes(4_320)).toBe('1h 12min')
  })

  it('formats distance and reliability', () => {
    expect(formatDistance(420)).toBe('420 m')
    expect(formatDistance(1_250)).toBe('1,3 km')
    expect(formatPercent(0.87)).toBe('87%')
  })
})
