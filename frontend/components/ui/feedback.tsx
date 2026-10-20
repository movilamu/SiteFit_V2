import * as React from 'react'
import { AlertTriangle, Inbox, RefreshCw } from 'lucide-react'

import { Button } from '@/components/ui/button'
import { cn } from '@/lib/utils'

/** Neutral placeholder shown when a view has no content. */
function EmptyState({
  title,
  description,
  action,
  icon: Icon = Inbox,
  className,
  ...props
}: React.ComponentProps<'div'> & {
  title: string
  description?: React.ReactNode
  action?: React.ReactNode
  icon?: React.ComponentType<{ className?: string }>
}) {
  return (
    <div
      data-slot="empty-state"
      className={cn(
        'flex flex-col items-center justify-center gap-3 px-6 py-12 text-center',
        className,
      )}
      {...props}
    >
      <span className="bg-surface-muted text-ink-subtle flex size-10 items-center justify-center rounded-lg">
        <Icon className="size-5" />
      </span>
      <div className="max-w-md space-y-1">
        <p className="text-ink text-sm font-medium">{title}</p>
        {description ? (
          <p className="text-ink-muted text-xs leading-relaxed">{description}</p>
        ) : null}
      </div>
      {action}
    </div>
  )
}

/** Error state with a retry affordance. */
function ErrorState({
  title = 'Something went wrong',
  description,
  onRetry,
  className,
  ...props
}: React.ComponentProps<'div'> & {
  title?: string
  description?: React.ReactNode
  onRetry?: () => void
}) {
  return (
    <div
      data-slot="error-state"
      role="alert"
      className={cn(
        'border-danger-border bg-danger-subtle flex flex-col items-start gap-2 rounded-lg border p-4',
        className,
      )}
      {...props}
    >
      <div className="flex items-start gap-2">
        <AlertTriangle className="text-danger mt-0.5 size-4 shrink-0" aria-hidden="true" />
        <div className="space-y-1">
          <p className="text-danger text-sm font-medium">{title}</p>
          {description ? (
            <p className="text-ink-muted text-xs leading-relaxed">{description}</p>
          ) : null}
        </div>
      </div>
      {onRetry ? (
        <Button type="button" variant="outline" size="sm" onClick={onRetry}>
          <RefreshCw />
          Try again
        </Button>
      ) : null}
    </div>
  )
}

/** Inline banner for a partial or advisory message. */
function Alert({
  tone = 'info',
  title,
  children,
  className,
  ...props
}: React.ComponentProps<'div'> & {
  tone?: 'info' | 'success' | 'warning' | 'danger' | 'neutral'
  title?: React.ReactNode
}) {
  const tones: Record<string, string> = {
    info: 'border-info-border bg-info-subtle text-info',
    success: 'border-success-border bg-success-subtle text-success',
    warning: 'border-warning-border bg-warning-subtle text-warning',
    danger: 'border-danger-border bg-danger-subtle text-danger',
    neutral: 'border-line bg-surface-muted text-ink-muted',
  }
  return (
    <div
      data-slot="alert"
      className={cn('rounded-lg border px-3.5 py-3', tones[tone], className)}
      {...props}
    >
      {title ? <p className="text-sm font-medium">{title}</p> : null}
      {children ? (
        <div className="text-ink-muted mt-1 text-xs leading-relaxed [&_a]:underline">
          {children}
        </div>
      ) : null}
    </div>
  )
}

/** Loading placeholder block. */
function Skeleton({ className, ...props }: React.ComponentProps<'div'>) {
  return (
    <div
      data-slot="skeleton"
      aria-hidden="true"
      className={cn('bg-surface-muted animate-pulse rounded', className)}
      {...props}
    />
  )
}

/** Busy indicator with an accessible label. */
function LoadingState({
  label = 'Loading…',
  className,
  ...props
}: React.ComponentProps<'div'> & { label?: string }) {
  return (
    <div
      data-slot="loading-state"
      role="status"
      aria-live="polite"
      className={cn(
        'text-ink-muted flex items-center justify-center gap-2 px-6 py-10 text-xs',
        className,
      )}
      {...props}
    >
      <span className="border-line border-t-primary size-3.5 animate-spin rounded-full border-2" />
      {label}
    </div>
  )
}

/** Skeleton rows used while a table is loading. */
function TableSkeleton({ rows = 5, columns = 4 }: { rows?: number; columns?: number }) {
  return (
    <div className="space-y-2 p-4" aria-busy="true" aria-live="polite">
      <span className="sr-only">Loading data</span>
      {Array.from({ length: rows }).map((_, rowIndex) => (
        <div key={rowIndex} className="flex gap-3">
          {Array.from({ length: columns }).map((__, columnIndex) => (
            <Skeleton
              key={columnIndex}
              className={cn('h-6 flex-1', columnIndex === 0 && 'max-w-[38%]')}
            />
          ))}
        </div>
      ))}
    </div>
  )
}

export { Alert, EmptyState, ErrorState, LoadingState, Skeleton, TableSkeleton }
