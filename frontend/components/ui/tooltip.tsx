'use client'

import * as React from 'react'
import { Tooltip as BaseTooltip } from '@base-ui/react/tooltip'

import { cn } from '@/lib/utils'

/**
 * Tooltip.
 *
 * Base UI renders the tooltip in a portal and wires the ARIA
 * relationships, so it is safe for use inside buttons and table cells.
 */
function Tooltip({
  content,
  children,
  side = 'top',
  ...props
}: Omit<React.ComponentProps<typeof BaseTooltip.Root>, 'className'> & {
  content: React.ReactNode
  side?: 'top' | 'right' | 'bottom' | 'left'
}) {
  return (
    <BaseTooltip.Root {...props}>
      <BaseTooltip.Trigger
        render={
          <span
            tabIndex={0}
            className="focus-visible:ring-ring inline-flex rounded focus-visible:ring-2 focus-visible:outline-none"
          />
        }
      >
        {children as React.ReactNode}
      </BaseTooltip.Trigger>
      <BaseTooltip.Portal>
        <BaseTooltip.Positioner side={side} sideOffset={6}>
          <BaseTooltip.Popup
            className={cn(
              'bg-ink text-canvas z-50 max-w-64 rounded-md px-2.5 py-1.5 text-[11px] leading-snug shadow-lg',
            )}
          >
            {content as React.ReactNode}
          </BaseTooltip.Popup>
        </BaseTooltip.Positioner>
      </BaseTooltip.Portal>
    </BaseTooltip.Root>
  )
}

export { Tooltip }
