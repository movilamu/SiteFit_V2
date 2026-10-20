import { describe, expect, it } from 'vitest'

import {
  UNAVAILABLE,
  formatDistance,
  formatMoney,
  formatNumber,
  formatPercent,
  formatScore,
  humaniseKey,
} from '@/lib/format'

describe('formatting', () => {
  it('never renders a missing value as zero', () => {
    expect(formatMoney(null)).toBe(UNAVAILABLE)
    expect(formatMoney(undefined)).toBe(UNAVAILABLE)
    expect(formatMoney(Number.NaN)).toBe(UNAVAILABLE)
    expect(formatNumber(null)).toBe(UNAVAILABLE)
  })

  it('renders a zero value as zero rather than as unavailable', () => {
    expect(formatMoney(0)).toBe('0')
    expect(formatNumber(0)).toBe('0')
  })

  it('uses the Indian numbering convention for large amounts', () => {
    expect(formatMoney(30_000_000)).toBe('3.00 Cr')
    expect(formatMoney(2_500_000)).toBe('25.00 L')
  })

  it('formats a score with a fixed number of decimals', () => {
    expect(formatScore(0.1234)).toBe('0.123')
    expect(formatScore(0.1234, 4)).toBe('0.1234')
    expect(formatScore(null)).toBe('—')
  })

  it('formats a ratio as a percentage', () => {
    expect(formatPercent(0.5)).toBe('50.0%')
    expect(formatPercent(null)).toBe('—')
  })

  it('formats distances in metres below a kilometre', () => {
    expect(formatDistance(450)).toBe('450 m')
    expect(formatDistance(1500)).toBe('1.5 km')
  })

  it('turns snake_case keys into readable labels', () => {
    expect(humaniseKey('resident_density')).toBe('Resident Density')
    expect(humaniseKey('site-and-property')).toBe('Site And Property')
  })
})
