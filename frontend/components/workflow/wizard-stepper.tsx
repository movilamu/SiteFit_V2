'use client'

import * as React from 'react'
import { Check, Circle } from 'lucide-react'

import { cn } from '@/lib/utils'

export type WizardStepId =
  | 'business'
  | 'location'
  | 'requirements'
  | 'parking'
  | 'facilities'
  | 'financial'
  | 'review'

export const WIZARD_STEPS: { id: WizardStepId; label: string; description: string }[] = [
  {
    id: 'business',
    label: 'Business type',
    description: 'What kind of site are you looking for?',
  },
  {
    id: 'location',
    label: 'Search area',
    description: 'Where should the platform look?',
  },
  {
    id: 'requirements',
    label: 'Requirements',
    description: 'What must the site provide?',
  },
  {
    id: 'parking',
    label: 'Parking',
    description: 'How much parking, and how strictly?',
  },
  {
    id: 'facilities',
    label: 'Facilities',
    description: 'Which facilities matter?',
  },
  {
    id: 'financial',
    label: 'Budgets',
    description: 'What can you spend?',
  },
  {
    id: 'review',
    label: 'Review',
    description: 'Confirm and evaluate',
  },
]

/**
 * The wizard's step indicator.
 *
 * Steps are a real ordered list so that assistive technology announces the
 * position in the sequence.  Completed steps are marked with an icon *and*
 * text, never colour alone.
 */
export function WizardStepper({
  current,
  completed,
  onNavigate,
}: {
  current: WizardStepId
  completed: Set<WizardStepId>
  onNavigate: (step: WizardStepId) => void
}) {
  const currentIndex = WIZARD_STEPS.findIndex((step) => step.id === current)

  return (
    <nav aria-label="Analysis steps">
      <ol className="flex flex-col gap-0.5">
        {WIZARD_STEPS.map((step, index) => {
          const isCurrent = step.id === current
          const isComplete = completed.has(step.id)
          const isReachable = index <= currentIndex || isComplete
          const Icon = isComplete ? Check : Circle

          return (
            <li key={step.id}>
              <button
                type="button"
                onClick={() => isReachable && onNavigate(step.id)}
                disabled={!isReachable}
                aria-current={isCurrent ? 'step' : undefined}
                className={cn(
                  'group flex w-full items-start gap-2.5 rounded-md px-2.5 py-2 text-left transition-colors',
                  'focus-visible:ring-ring focus-visible:ring-2 focus-visible:outline-none',
                  isCurrent
                    ? 'bg-surface-muted'
                    : isReachable
                      ? 'hover:bg-surface-muted/70'
                      : 'cursor-not-allowed opacity-45',
                )}
              >
                <span
                  className={cn(
                    'mt-0.5 flex size-5 shrink-0 items-center justify-center rounded-full border text-[10px] font-semibold',
                    isCurrent
                      ? 'border-primary bg-primary text-primary-foreground'
                      : isComplete
                        ? 'border-success bg-success-subtle text-success'
                        : 'border-line text-ink-subtle',
                  )}
                  aria-hidden="true"
                >
                  <Icon className="size-3" />
                </span>
                <span className="min-w-0">
                  <span
                    className={cn(
                      'block text-[13px] leading-tight font-medium',
                      isCurrent ? 'text-ink' : 'text-ink-muted',
                    )}
                  >
                    {step.label}
                    {isComplete && !isCurrent ? (
                      <span className="sr-only"> (completed)</span>
                    ) : null}
                  </span>
                  <span className="text-ink-subtle block text-[11px] leading-snug">
                    {step.description}
                  </span>
                </span>
              </button>
            </li>
          )
        })}
      </ol>
    </nav>
  )
}
