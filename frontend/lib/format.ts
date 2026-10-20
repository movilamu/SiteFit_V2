/**
 * Presentation helpers.
 *
 * All monetary values are shown in the Indian numbering convention because
 * the platform's reference market is India.  A value that is not available
 * is always rendered as an explicit "Unavailable" rather than as 0, a dash
 * or an empty cell.
 */

export const UNAVAILABLE = 'Unavailable'

/** Format a score / normalised value. */
export function formatScore(value: number | null | undefined, digits = 3): string {
  if (value === null || value === undefined || !Number.isFinite(value)) return '—'
  return value.toFixed(digits)
}

/** Format a percentage from a 0-1 ratio. */
export function formatPercent(value: number | null | undefined, digits = 1): string {
  if (value === null || value === undefined || !Number.isFinite(value)) return '—'
  return `${(value * 100).toFixed(digits)}%`
}

/** Format a number with thousands separators. */
export function formatNumber(
  value: number | null | undefined,
  options: Intl.NumberFormatOptions = {},
): string {
  if (value === null || value === undefined || !Number.isFinite(value)) return UNAVAILABLE
  return new Intl.NumberFormat('en-IN', options).format(value)
}

/**
 * Format a monetary amount using the Indian numbering convention.
 *
 * Crore (10 million) and lakh (100 thousand) are used above one lakh,
 * which is how these figures are read in the market the platform serves.
 */
export function formatMoney(value: number | null | undefined): string {
  if (value === null || value === undefined || !Number.isFinite(value)) return UNAVAILABLE
  const sign = value < 0 ? '-' : ''
  const absolute = Math.abs(value)
  if (absolute >= 10_000_000) {
    return `${sign}${(absolute / 10_000_000).toFixed(2)} Cr`
  }
  if (absolute >= 100_000) {
    return `${sign}${(absolute / 100_000).toFixed(2)} L`
  }
  return `${sign}${new Intl.NumberFormat('en-IN', { maximumFractionDigits: 0 }).format(absolute)}`
}

/** Format a distance in metres. */
export function formatDistance(metres: number | null | undefined): string {
  if (metres === null || metres === undefined || !Number.isFinite(metres)) return '—'
  if (metres < 1000) return `${Math.round(metres)} m`
  return `${(metres / 1000).toFixed(1)} km`
}

/** Format an ISO timestamp as a readable date-time. */
export function formatDateTime(value: string | null | undefined): string {
  if (!value) return '—'
  const parsed = new Date(value)
  if (Number.isNaN(parsed.getTime())) return '—'
  return new Intl.DateTimeFormat('en-GB', {
    dateStyle: 'medium',
    timeStyle: 'short',
  }).format(parsed)
}

/** Format an ISO timestamp as a date. */
export function formatDate(value: string | null | undefined): string {
  if (!value) return '—'
  const parsed = new Date(value)
  if (Number.isNaN(parsed.getTime())) return '—'
  return new Intl.DateTimeFormat('en-GB', { dateStyle: 'medium' }).format(parsed)
}

/** Turn a snake_case key into a human-readable label. */
export function humaniseKey(value: string): string {
  return value
    .replace(/[_-]+/g, ' ')
    .replace(/\b\w/g, (character) => character.toUpperCase())
}

/** Format a numeric value with its unit, e.g. "1,500 sq ft". */
export function formatWithUnit(
  value: number | null | undefined,
  unit: string,
  options: Intl.NumberFormatOptions = {},
): string {
  if (value === null || value === undefined || !Number.isFinite(value)) return UNAVAILABLE
  const formatted = new Intl.NumberFormat('en-IN', options).format(value)
  return unit ? `${formatted} ${unit}` : formatted
}
