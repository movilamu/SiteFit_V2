import * as React from 'react'

import { cn } from '@/lib/utils'

/**
 * Progress bar.
 *
 * The value is exposed through `role="progressbar"` with the numeric
 * value, so assistive technology can read the actual progress rather than
 * an unlabelled bar.
 */
function Progress({
  value,
  max = 100,
  tone = 'info',
  label,
  className,
  ...props
}: React.ComponentProps<'div'> & {
  value: number
  max?: number
  tone?: 'info' | 'success' | 'warning' | 'danger' | 'neutral'
  label?: string
}) {
  const safeMax = max > 0 ? max : 100
  const clamped = Math.max(0, Math.min(safeMax, value))
  const percentage = (clamped / safeMax) * 100

  const tones: Record<string, string> = {
    info: 'bg-info',
    success: 'bg-success',
    warning: 'bg-warning',
    danger: 'bg-danger',
    neutral: 'bg-neutral',
  }

  return (
    <div
      data-slot="progress"
      role="progressbar"
      aria-valuemin={0}
      aria-valuemax={safeMax}
      aria-valuenow={clamped}
      aria-label={label}
      className={cn('bg-surface-sunken h-1.5 w-full overflow-hidden rounded-full', className)}
      {...props}
    >
      <div
        className={cn('h-full rounded-full transition-[width] duration-300', tones[tone])}
        style={{ width: `${percentage}%` }}
      />
    </div>
  )
}

/**
 * A labelled measure, used for score and fit readouts.
 */
function Meter({
  value,
  max = 1,
  tone = 'info',
  label,
  valueLabel,
  className,
}: {
  value: number
  max?: number
  tone?: 'info' | 'success' | 'warning' | 'danger' | 'neutral'
  label: string
  valueLabel?: string
  className?: string
}) {
  return (
    <div className={cn('space-y-1.5', className)}>
      <div className="flex items-baseline justify-between gap-3">
        <span className="text-ink-muted text-xs">{label}</span>
        <span className="text-ink text-xs font-semibold tabular-nums">
          {valueLabel ?? value.toFixed(3)}
        </span>
      </div>
      <Progress value={value} max={max} tone={tone} label={label} />
    </div>
  )
}

export { Meter, Progress }
