import * as React from 'react'

import { cn } from '@/lib/utils'

/** Visible label for a form control. */
function Label({ className, ...props }: React.ComponentProps<'label'>) {
  return (
    <label
      data-slot="label"
      className={cn('text-ink text-xs font-medium leading-none', className)}
      {...props}
    />
  )
}

/**
 * Field — a label / control / hint / error group.
 *
 * The control is associated with the label and the hint/error through
 * generated ids so that screen readers announce the right thing.
 */
function Field({
  label,
  hint,
  error,
  required,
  htmlFor,
  className,
  children,
  ...props
}: React.ComponentProps<'div'> & {
  label?: React.ReactNode
  hint?: React.ReactNode
  error?: React.ReactNode
  required?: boolean
  htmlFor?: string
}) {
  return (
    <div data-slot="field" className={cn('flex flex-col gap-1.5', className)} {...props}>
      {label ? (
        <Label htmlFor={htmlFor}>
          {label}
          {required ? (
            <span className="text-danger ml-0.5" aria-hidden="true">
              *
            </span>
          ) : null}
          {required ? <span className="sr-only"> (required)</span> : null}
        </Label>
      ) : null}
      {children}
      {hint && !error ? (
        <p className="text-ink-subtle text-[11px] leading-relaxed">{hint}</p>
      ) : null}
      {error ? (
        <p className="text-danger text-[11px] leading-relaxed" role="alert">
          {error}
        </p>
      ) : null}
    </div>
  )
}

/** Small helper text block. */
function FieldHint({ className, ...props }: React.ComponentProps<'p'>) {
  return (
    <p className={cn('text-ink-subtle text-[11px] leading-relaxed', className)} {...props} />
  )
}

export { Field, FieldHint, Label }
