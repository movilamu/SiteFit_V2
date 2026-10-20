import * as React from 'react'

import { cn } from '@/lib/utils'

const baseField =
  'w-full rounded-md border border-line bg-surface px-3 text-sm text-ink placeholder:text-ink-subtle transition-colors focus-visible:border-ring focus-visible:ring-2 focus-visible:ring-ring/25 focus-visible:outline-none disabled:cursor-not-allowed disabled:bg-surface-muted disabled:text-ink-subtle aria-[invalid=true]:border-danger aria-[invalid=true]:ring-danger/25'

/** Text input. */
function Input({ className, type = 'text', ...props }: React.ComponentProps<'input'>) {
  return (
    <input
      type={type}
      data-slot="input"
      className={cn(baseField, 'h-9', className)}
      {...props}
    />
  )
}

/** Multi-line text input. */
function Textarea({ className, ...props }: React.ComponentProps<'textarea'>) {
  return (
    <textarea
      data-slot="textarea"
      className={cn(baseField, 'min-h-24 py-2 leading-relaxed', className)}
      {...props}
    />
  )
}

/**
 * Numeric input.
 *
 * `type="number"` is used so that mobile keyboards offer a numeric pad
 * and so that the browser's own validation applies; the value is kept as a
 * string in the form state and parsed by the caller.
 */
function NumberInput({
  className,
  min,
  max,
  step = 1,
  suffix,
  ...props
}: React.ComponentProps<'input'> & { suffix?: string }) {
  return (
    <div className="relative">
      <input
        type="number"
        inputMode="decimal"
        data-slot="number-input"
        min={min}
        max={max}
        step={step}
        className={cn(baseField, 'h-9 tabular-nums', suffix && 'pr-12', className)}
        {...props}
      />
      {suffix ? (
        <span className="text-ink-subtle pointer-events-none absolute top-1/2 right-3 -translate-y-1/2 text-xs">
          {suffix}
        </span>
      ) : null}
    </div>
  )
}

/** Native select, styled to match the design system. */
function Select({ className, children, ...props }: React.ComponentProps<'select'>) {
  return (
    <select
      data-slot="select"
      className={cn(
        baseField,
        'h-9 cursor-pointer appearance-none bg-[url("data:image/svg+xml;charset=utf-8,%3Csvg xmlns=\'http://www.w3.org/2000/svg\' width=\'12\' height=\'12\' viewBox=\'0 0 12 12\'%3E%3Cpath fill=\'%2357616f\' d=\'M6 8.5 2 4.5h8z\'/%3E%3C/svg%3E")] bg-[length:12px] bg-[right_0.75rem_center] bg-no-repeat pr-8',
        className,
      )}
      {...props}
    >
      {children}
    </select>
  )
}

/** Checkbox with an accessible label wrapper. */
function Checkbox({ className, ...props }: React.ComponentProps<'input'>) {
  return (
    <input
      type="checkbox"
      data-slot="checkbox"
      className={cn(
        'border-line size-4 shrink-0 cursor-pointer rounded border accent-[var(--primary)]',
        'focus-visible:ring-ring focus-visible:ring-2 focus-visible:outline-none',
        'disabled:cursor-not-allowed disabled:opacity-50',
        className,
      )}
      {...props}
    />
  )
}

/** Radio button with an accessible label wrapper. */
function Radio({ className, ...props }: React.ComponentProps<'input'>) {
  return (
    <input
      type="radio"
      data-slot="radio"
      className={cn(
        'border-line size-4 shrink-0 cursor-pointer rounded-full border accent-[var(--primary)]',
        'focus-visible:ring-ring focus-visible:ring-2 focus-visible:outline-none',
        'disabled:cursor-not-allowed disabled:opacity-50',
        className,
      )}
      {...props}
    />
  )
}

/** Range slider used for the weight controls. */
function Slider({ className, ...props }: React.ComponentProps<'input'>) {
  return (
    <input
      type="range"
      data-slot="slider"
      className={cn(
        'h-1.5 w-full cursor-pointer appearance-none rounded-full bg-surface-sunken accent-[var(--primary)]',
        'focus-visible:ring-ring focus-visible:ring-2 focus-visible:outline-none',
        'disabled:cursor-not-allowed disabled:opacity-50',
        className,
      )}
      {...props}
    />
  )
}

export { Checkbox, Input, NumberInput, Radio, Select, Slider, Textarea }
