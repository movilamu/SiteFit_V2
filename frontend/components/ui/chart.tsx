'use client'

import * as React from 'react'

import { formatNumber } from '@/lib/format'
import { cn } from '@/lib/utils'

/**
 * Chart primitives.
 *
 * The charts are drawn with plain SVG so that no charting dependency is
 * introduced, and they are coloured with the design system's semantic
 * tokens, so a chart never introduces a colour the rest of the interface
 * does not use.
 *
 * Every chart is responsive (an SVG `viewBox` scaled to the width of its
 * container) and carries both an accessible name and a text summary, so
 * the information it shows is available to a reader who cannot see the
 * graphic.  A value of zero is drawn as a zero rather than as a missing
 * bar, and an empty data set says so, so a chart is never a blank box.
 */

export type ChartTone = 'info' | 'success' | 'warning' | 'danger' | 'neutral'

/** The fill used for a bar of each tone. */
const TONE_FILL: Record<ChartTone, string> = {
  info: 'fill-info',
  success: 'fill-success',
  warning: 'fill-warning',
  danger: 'fill-danger',
  neutral: 'fill-neutral',
}

/** The background used for a legend swatch of each tone. */
const TONE_SWATCH: Record<ChartTone, string> = {
  info: 'bg-info',
  success: 'bg-success',
  warning: 'bg-warning',
  danger: 'bg-danger',
  neutral: 'bg-neutral',
}

/** The nominal width of the drawing area; the SVG scales to its container. */
const CHART_WIDTH = 700

/** The width reserved for the value printed at the end of a row. */
const VALUE_GUTTER = 92

/** Truncate a label so that it fits the space available to it. */
function truncate(value: string, maxChars: number): string {
  if (maxChars < 2) return value.slice(0, Math.max(1, maxChars))
  if (value.length <= maxChars) return value
  return `${value.slice(0, maxChars - 1).trimEnd()}…`
}

/**
 * The offset of every item from the start of the drawing area.
 *
 * The offsets are a running total of the heights, so the rows follow one
 * another without the chart having to measure anything at run time.
 */
function prefixOffsets(heights: number[]): number[] {
  const offsets: number[] = []
  let total = 0
  for (const height of heights) {
    offsets.push(total)
    total += height
  }
  return offsets
}

export type HorizontalBarDatum = {
  key: string
  label: string
  value: number
  secondaryLabel?: string
  tone?: ChartTone
}

export type HorizontalBarChartProps = {
  data: HorizontalBarDatum[]
  /** The value that fills the whole track.  Defaults to the largest value. */
  max?: number
  formatValue?: (value: number) => string
  /** The width reserved for the row label, in chart units. */
  labelWidth?: number
  /** The height of a bar, in chart units. */
  barHeight?: number
  className?: string
}

/**
 * A horizontal bar chart.
 *
 * Each row carries a label, a bar against a track and the value printed at
 * the end of the row in tabular figures, so the numbers line up down the
 * column and can be read against the graphic.
 */
export function HorizontalBarChart({
  data,
  max,
  formatValue = formatNumber,
  labelWidth = 150,
  barHeight = 10,
  className,
}: HorizontalBarChartProps) {
  const ceiling = React.useMemo(() => {
    if (max !== undefined && Number.isFinite(max) && max > 0) return max
    return data.reduce((largest, item) => Math.max(largest, item.value), 0)
  }, [data, max])

  const summary = React.useMemo(
    () =>
      data.length === 0
        ? 'No variation to show.'
        : data
            .map((item) => `${item.label}: ${formatValue(item.value)}`)
            .join('. '),
    [data, formatValue],
  )

  const geometry = React.useMemo(() => {
    const barAreaWidth = Math.max(60, CHART_WIDTH - labelWidth - VALUE_GUTTER - 12)
    const maxLabelChars = Math.max(6, Math.floor((labelWidth - 12) / 5.6))
    const baseRowHeight = Math.max(18, barHeight + 10)
    const secondaryRowHeight = 12

    const rowHeights = data.map((item) =>
      item.secondaryLabel ? baseRowHeight + secondaryRowHeight : baseRowHeight,
    )
    const offsets = prefixOffsets(rowHeights)

    const rows = data.map((item, index) => {
      const cursor = offsets[index]
      const hasSecondary = Boolean(item.secondaryLabel)
      const ratio = ceiling > 0 ? Math.min(1, Math.max(0, item.value) / ceiling) : 0
      return {
        item,
        barY: hasSecondary
          ? cursor + 4
          : cursor + Math.max(0, (baseRowHeight - barHeight) / 2),
        labelY: hasSecondary ? cursor + 11 : cursor + baseRowHeight / 2 + 4,
        secondaryY: cursor + 22,
        barWidth: ratio * barAreaWidth,
        label: truncate(item.label, maxLabelChars),
        secondaryLabel: hasSecondary
          ? truncate(item.secondaryLabel ?? '', maxLabelChars)
          : undefined,
        valueLabel: formatValue(item.value),
      }
    })

    const height = rowHeights.reduce((sum, value) => sum + value, 0)
    return { rows, barAreaWidth, height: Math.max(height, baseRowHeight) }
  }, [data, ceiling, formatValue, labelWidth, barHeight])

  if (data.length === 0) {
    return (
      <p className={cn('text-ink-subtle text-xs', className)} role="status">
        No variation to show.
      </p>
    )
  }

  return (
    <figure className={cn('w-full', className)}>
      <svg
        viewBox={`0 0 ${CHART_WIDTH} ${geometry.height}`}
        className="h-auto w-full"
        role="img"
        aria-label={summary}
      >
        {geometry.rows.map((row) => {
          const tone = row.item.tone ?? 'info'
          return (
            <g key={row.item.key}>
              <rect
                x={labelWidth}
                y={row.barY}
                width={geometry.barAreaWidth}
                height={barHeight}
                rx={2}
                className="fill-surface-sunken"
              />
              <rect
                x={labelWidth}
                y={row.barY}
                width={row.barWidth}
                height={barHeight}
                rx={2}
                className={cn('rounded-[2px]', TONE_FILL[tone])}
              />
              <text
                x={labelWidth - 8}
                y={row.labelY}
                textAnchor="end"
                className="fill-ink-muted text-[11px]"
              >
                {row.label}
              </text>
              {row.secondaryLabel ? (
                <text
                  x={labelWidth - 8}
                  y={row.secondaryY}
                  textAnchor="end"
                  className="fill-ink-subtle text-[10px]"
                >
                  {row.secondaryLabel}
                </text>
              ) : null}
              <text
                x={labelWidth + geometry.barAreaWidth + 8}
                y={row.labelY}
                textAnchor="start"
                className="fill-ink text-[11px] tabular-nums"
              >
                {row.valueLabel}
              </text>
            </g>
          )
        })}
      </svg>
      <figcaption className="sr-only">{summary}</figcaption>
    </figure>
  )
}

export type ColumnDatum = {
  key: string
  label: string
  value: number
  tone?: ChartTone
}

export type ColumnChartProps = {
  data: ColumnDatum[]
  /** The value that reaches the top of the plot.  Defaults to the largest value. */
  max?: number
  formatValue?: (value: number) => string
  className?: string
  /** The height of the drawing area, in chart units. */
  height?: number
}

/**
 * A column chart.
 *
 * Each column carries its value above it and its label underneath, so the
 * shape of the series and the exact figures are both readable.
 */
export function ColumnChart({
  data,
  max,
  formatValue = formatNumber,
  className,
  height = 180,
}: ColumnChartProps) {
  const ceiling = React.useMemo(() => {
    if (max !== undefined && Number.isFinite(max) && max > 0) return max
    return data.reduce((largest, item) => Math.max(largest, item.value), 0)
  }, [data, max])

  const summary = React.useMemo(
    () =>
      data.length === 0
        ? 'No variation to show.'
        : data
            .map((item) => `${item.label}: ${formatValue(item.value)}`)
            .join('. '),
    [data, formatValue],
  )

  if (data.length === 0) {
    return (
      <p className={cn('text-ink-subtle text-xs', className)} role="status">
        No variation to show.
      </p>
    )
  }

  const topGutter = 20
  const bottomGutter = 26
  const plotHeight = Math.max(40, height - topGutter - bottomGutter)
  const slot = CHART_WIDTH / data.length

  return (
    <figure className={cn('w-full', className)}>
      <svg
        viewBox={`0 0 ${CHART_WIDTH} ${height}`}
        className="h-auto w-full"
        role="img"
        aria-label={summary}
      >
        {data.map((item, index) => {
          const tone = item.tone ?? 'info'
          const ratio = ceiling > 0 ? Math.min(1, Math.max(0, item.value) / ceiling) : 0
          const columnWidth = Math.max(6, Math.min(slot * 0.6, 72))
          const x = index * slot + (slot - columnWidth) / 2
          const columnHeight = ratio * plotHeight
          const y = topGutter + plotHeight - columnHeight
          const maxLabelChars = Math.max(4, Math.floor((slot - 8) / 5.6))

          return (
            <g key={item.key}>
              <rect
                x={x}
                y={topGutter}
                width={columnWidth}
                height={plotHeight}
                rx={2}
                className="fill-surface-sunken"
              />
              <rect
                x={x}
                y={y}
                width={columnWidth}
                height={columnHeight}
                rx={2}
                className={cn('rounded-[2px]', TONE_FILL[tone])}
              />
              <text
                x={x + columnWidth / 2}
                y={y - 6}
                textAnchor="middle"
                className="fill-ink text-[11px] tabular-nums"
              >
                {formatValue(item.value)}
              </text>
              <text
                x={x + columnWidth / 2}
                y={height - 8}
                textAnchor="middle"
                className="fill-ink-muted text-[11px]"
              >
                {truncate(item.label, maxLabelChars)}
              </text>
            </g>
          )
        })}
      </svg>
      <figcaption className="sr-only">{summary}</figcaption>
    </figure>
  )
}

export type StackedSegment = {
  key: string
  label: string
  /**
   * The size of the segment.  A segment of zero — or one that is not
   * available — is left out of the bar but is still reported in the
   * legend, so the composition is never silently incomplete.
   */
  value: number | null
  tone: ChartTone
}

export type StackedBarProps = {
  segments: StackedSegment[]
  formatValue?: (value: number) => string
  className?: string
  /** The height of the bar, in chart units. */
  height?: number
}

/**
 * A single bar split into segments, with a legend beneath.
 *
 * The bar shows the composition of one total; the legend names every
 * component and its value, including a component that is zero or
 * unavailable, so the reader can tell the difference between "nothing
 * there" and "not known".
 */
export function StackedBar({
  segments,
  formatValue = formatNumber,
  className,
  height = 16,
}: StackedBarProps) {
  const clipId = React.useId().replace(/[^a-zA-Z0-9_-]/g, '')

  const total = segments.reduce(
    (sum, segment) => sum + Math.max(0, segment.value ?? 0),
    0,
  )

  const summary = React.useMemo(() => {
    const parts = segments.map((segment) =>
      segment.value === null
        ? `${segment.label}: unavailable`
        : `${segment.label}: ${formatValue(segment.value)}`,
    )
    return parts.length > 0 ? parts.join('. ') : 'No variation to show.'
  }, [segments, formatValue])

  const offsets = React.useMemo(
    () =>
      prefixOffsets(
        segments.map((segment) =>
          total > 0 ? (Math.max(0, segment.value ?? 0) / total) * CHART_WIDTH : 0,
        ),
      ),
    [segments, total],
  )

  return (
    <figure className={cn('w-full', className)}>
      <svg
        viewBox={`0 0 ${CHART_WIDTH} ${height}`}
        className="h-auto w-full"
        role="img"
        aria-label={summary}
      >
        <defs>
          <clipPath id={clipId}>
            <rect x={0} y={0} width={CHART_WIDTH} height={height} rx={2} />
          </clipPath>
        </defs>
        <g clipPath={`url(#${clipId})`}>
          {segments.map((segment, index) => {
            const value = Math.max(0, segment.value ?? 0)
            if (total <= 0 || value <= 0) return null
            const width = (value / total) * CHART_WIDTH
            return (
              <rect
                key={segment.key}
                x={offsets[index]}
                y={0}
                width={width}
                height={height}
                className={TONE_FILL[segment.tone]}
              />
            )
          })}
        </g>
      </svg>
      <ul className="mt-2.5 flex flex-wrap gap-x-4 gap-y-1.5">
        {segments.map((segment) => (
          <li
            key={segment.key}
            className="text-ink-muted flex items-center gap-1.5 text-[11px]"
          >
            <span
              className={cn('size-2 shrink-0 rounded-[2px]', TONE_SWATCH[segment.tone])}
              aria-hidden="true"
            />
            <span>{segment.label}</span>
            <span className="text-ink font-medium tabular-nums">
              {segment.value === null ? 'Unavailable' : formatValue(segment.value)}
            </span>
          </li>
        ))}
      </ul>
      <figcaption className="sr-only">{summary}</figcaption>
    </figure>
  )
}

export type ChartFrameProps = {
  title: string
  description?: React.ReactNode
  actions?: React.ReactNode
  children: React.ReactNode
  className?: string
}

/**
 * A bordered frame for a chart: a title row, optional actions and the
 * chart beneath.
 */
export function ChartFrame({
  title,
  description,
  actions,
  children,
  className,
}: ChartFrameProps) {
  return (
    <div
      className={cn(
        'border-line bg-surface overflow-hidden rounded-lg border shadow-[0_1px_2px_rgba(17,24,32,0.04)]',
        className,
      )}
    >
      <div className="flex flex-wrap items-start justify-between gap-3 border-b border-line px-4 py-3">
        <div className="min-w-0">
          <p className="text-ink text-sm font-semibold tracking-tight">{title}</p>
          {description ? (
            <p className="text-ink-muted mt-0.5 text-[11px] leading-relaxed">{description}</p>
          ) : null}
        </div>
        {actions ? <div className="flex shrink-0 flex-wrap items-center gap-2">{actions}</div> : null}
      </div>
      <div className="px-4 py-4">{children}</div>
    </div>
  )
}
