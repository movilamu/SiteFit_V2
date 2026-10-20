import * as React from 'react'
import { cva, type VariantProps } from 'class-variance-authority'

import { cn } from '@/lib/utils'

/**
 * Status is communicated by colour *and* by an explicit label.  The
 * `dot` variant pairs the colour with a filled shape so that the status
 * is still distinguishable without colour vision.
 */
const badgeVariants = cva(
  'inline-flex w-fit shrink-0 items-center gap-1.5 rounded-md border px-2 py-0.5 text-[11px] font-medium whitespace-nowrap',
  {
    variants: {
      tone: {
        neutral: 'bg-neutral-subtle text-neutral border-neutral-border',
        info: 'bg-info-subtle text-info border-info-border',
        success: 'bg-success-subtle text-success border-success-border',
        warning: 'bg-warning-subtle text-warning border-warning-border',
        danger: 'bg-danger-subtle text-danger border-danger-border',
        outline: 'bg-surface text-ink-muted border-line',
      },
    },
    defaultVariants: { tone: 'neutral' },
  },
)

export type BadgeTone = NonNullable<VariantProps<typeof badgeVariants>['tone']>

function Badge({
  className,
  tone,
  ...props
}: React.ComponentProps<'span'> & VariantProps<typeof badgeVariants>) {
  return (
    <span
      data-slot="badge"
      className={cn(badgeVariants({ tone }), className)}
      {...props}
    />
  )
}

const DOT_TONE: Record<BadgeTone, string> = {
  neutral: 'bg-neutral',
  info: 'bg-info',
  success: 'bg-success',
  warning: 'bg-warning',
  danger: 'bg-danger',
  outline: 'bg-ink-subtle',
}

/** Badge with a leading status dot. The text remains the primary signal. */
function StatusDot({
  tone = 'neutral',
  className,
  ...props
}: React.ComponentProps<'span'> & { tone?: BadgeTone }) {
  return (
    <span
      data-slot="status-dot"
      className={cn('inline-block size-1.5 shrink-0 rounded-full', DOT_TONE[tone], className)}
      aria-hidden="true"
      {...props}
    />
  )
}

export { Badge, StatusDot, badgeVariants }
