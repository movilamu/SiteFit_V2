'use client'

import * as React from 'react'
import { Tabs as BaseTabs } from '@base-ui/react/tabs'

import { cn } from '@/lib/utils'

/**
 * Tabs — a keyboard-navigable tab set.
 *
 * Base UI supplies the roving-focus and ARIA wiring; the styling keeps
 * the enterprise look: an underlined active tab rather than a pill.
 */
function Tabs({
  value,
  defaultValue,
  onValueChange,
  className,
  children,
  ...props
}: React.ComponentProps<typeof BaseTabs.Root>) {
  return (
    <BaseTabs.Root
      value={value}
      defaultValue={defaultValue}
      onValueChange={onValueChange}
      className={cn('flex flex-col', className)}
      {...props}
    >
      {children}
    </BaseTabs.Root>
  )
}

function TabsList({ className, ...props }: React.ComponentProps<typeof BaseTabs.List>) {
  return (
    <BaseTabs.List
      className={cn(
        'border-line flex items-center gap-1 overflow-x-auto border-b',
        className,
      )}
      {...props}
    />
  )
}

function TabsTrigger({ className, ...props }: React.ComponentProps<typeof BaseTabs.Tab>) {
  return (
    <BaseTabs.Tab
      className={cn(
        'text-ink-muted relative -mb-px shrink-0 cursor-pointer border-b-2 border-transparent px-3 py-2.5 text-xs font-medium whitespace-nowrap transition-colors',
        'hover:text-ink focus-visible:ring-ring focus-visible:ring-2 focus-visible:outline-none',
        'data-[selected]:border-primary data-[selected]:text-ink',
        className,
      )}
      {...props}
    />
  )
}

function TabsContent({ className, ...props }: React.ComponentProps<typeof BaseTabs.Panel>) {
  return (
    <BaseTabs.Panel
      className={cn('focus-visible:ring-ring focus-visible:ring-2 focus-visible:outline-none', className)}
      {...props}
    />
  )
}

export { Tabs, TabsContent, TabsList, TabsTrigger }
