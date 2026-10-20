'use client'

import * as React from 'react'
import { Dialog as BaseDialog } from '@base-ui/react/dialog'
import { X } from 'lucide-react'

import { cn } from '@/lib/utils'

/** Accessible modal dialog built on Base UI. */
function Dialog({
  open,
  onOpenChange,
  children,
  ...props
}: Omit<React.ComponentProps<typeof BaseDialog.Root>, 'className'>) {
  return (
    <BaseDialog.Root open={open} onOpenChange={onOpenChange} {...props}>
      {children}
    </BaseDialog.Root>
  )
}

function DialogTrigger({ className, ...props }: React.ComponentProps<typeof BaseDialog.Trigger>) {
  return <BaseDialog.Trigger className={className} {...props} />
}

function DialogContent({
  className,
  children,
  ...props
}: React.ComponentProps<typeof BaseDialog.Popup>) {
  return (
    <BaseDialog.Portal>
      <BaseDialog.Backdrop
        className={cn(
          'fixed inset-0 z-50 bg-[#111820]/35 backdrop-blur-[1px]',
          'data-[starting-style]:opacity-0 data-[ending-style]:opacity-0 transition-opacity duration-150',
        )}
      />
      <BaseDialog.Viewport
        className={cn(
          'fixed inset-0 z-50 flex items-center justify-center overflow-y-auto p-4',
        )}
      >
        <BaseDialog.Popup
          className={cn(
            'bg-surface border-line w-full max-w-lg rounded-xl border shadow-[0_12px_40px_rgba(17,24,32,0.16)]',
            'data-[starting-style]:scale-[0.98] data-[ending-style]:scale-[0.98] data-[starting-style]:opacity-0 data-[ending-style]:opacity-0 transition-all duration-150',
            className,
          )}
          {...props}
        >
          {children}
        </BaseDialog.Popup>
      </BaseDialog.Viewport>
    </BaseDialog.Portal>
  )
}

function DialogHeader({ className, ...props }: React.ComponentProps<'div'>) {
  return (
    <div
      className={cn('border-line flex items-start justify-between gap-4 border-b px-5 py-4', className)}
      {...props}
    />
  )
}

function DialogTitle({ className, ...props }: React.ComponentProps<typeof BaseDialog.Title>) {
  return (
    <BaseDialog.Title
      className={cn('text-ink text-sm font-semibold tracking-tight', className)}
      {...props}
    />
  )
}

function DialogDescription({
  className,
  ...props
}: React.ComponentProps<typeof BaseDialog.Description>) {
  return (
    <BaseDialog.Description
      className={cn('text-ink-muted mt-1 text-xs leading-relaxed', className)}
      {...props}
    />
  )
}

function DialogBody({ className, ...props }: React.ComponentProps<'div'>) {
  return <div className={cn('px-5 py-4', className)} {...props} />
}

function DialogFooter({ className, ...props }: React.ComponentProps<'div'>) {
  return (
    <div
      className={cn('border-line flex items-center justify-end gap-2 border-t px-5 py-3', className)}
      {...props}
    />
  )
}

function DialogClose({ className, ...props }: React.ComponentProps<typeof BaseDialog.Close>) {
  return (
    <BaseDialog.Close
      className={cn(
        'text-ink-subtle hover:bg-surface-muted hover:text-ink focus-visible:ring-ring focus-visible:ring-2 focus-visible:outline-none absolute top-3.5 right-3.5 rounded p-1',
        className,
      )}
      aria-label="Close dialog"
      {...props}
    >
      <X className="size-4" />
    </BaseDialog.Close>
  )
}

export {
  Dialog,
  DialogBody,
  DialogClose,
  DialogContent,
  DialogDescription,
  DialogFooter,
  DialogHeader,
  DialogTitle,
  DialogTrigger,
}
