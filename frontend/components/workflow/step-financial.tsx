'use client'

import * as React from 'react'
import { AlertTriangle, Info } from 'lucide-react'

import { Card, CardContent, CardDescription, CardHeader, CardTitle } from '@/components/ui/card'
import { Field, FieldHint, Label } from '@/components/ui/field'
import { NumberInput, Radio } from '@/components/ui/input'
import { cn } from '@/lib/utils'
import type { AcquisitionMode, RequirementCatalog } from '@/lib/types'

import { useWizard } from './wizard-context'

/**
 * Step 6 — the financial requirements.
 *
 * A budget is a penalty by default, not a filter.  The user has to choose
 * explicitly if a budget should exclude a site instead.
 */
export function StepFinancial({ catalog }: { catalog: RequirementCatalog | null }) {
  const { brief, setBudgets, update } = useWizard()
  const financial = brief.financial

  const applicable = React.useMemo(() => {
    const definitions = catalog?.budget_definitions ?? []
    return definitions.filter((definition) =>
      definition.applies_to.includes(brief.acquisitionMode as AcquisitionMode),
    )
  }, [catalog, brief.acquisitionMode])

  const limitByKey = React.useMemo(() => {
    const map: Record<string, number | null> = {}
    for (const budget of financial.budgets) {
      map[budget.key] = budget.limit
    }
    return map
  }, [financial.budgets])

  const setLimit = React.useCallback(
    (key: string, limit: number | null) => {
      const definition = applicable.find((item) => item.key === key)
      if (!definition) return
      const existing = financial.budgets.find((budget) => budget.key === key)
      if (existing) {
        setBudgets(
          financial.budgets.map((budget) =>
            budget.key === key
              ? { ...budget, limit, behaviour: financial.budgetBehaviour }
              : budget,
          ),
        )
      } else {
        setBudgets([
          ...financial.budgets,
          {
            key,
            label: definition.label,
            scope: definition.scope,
            limit,
            behaviour: financial.budgetBehaviour,
            appliesTo: definition.applies_to,
          },
        ])
      }
    },
    [applicable, financial.budgets, financial.budgetBehaviour, setBudgets],
  )

  const behaviourChanged = React.useCallback(
    (behaviour: 'penalise' | 'hard') => {
      update({
        financial: {
          ...financial,
          budgetBehaviour: behaviour,
          budgets: financial.budgets.map((budget) => ({ ...budget, behaviour })),
        },
      })
    },
    [financial, update],
  )

  return (
    <div className="space-y-5">
      <Card>
        <CardHeader>
          <CardTitle>Budgets</CardTitle>
          <CardDescription>
            Set the ceilings you are working to. A budget is a penalty by default: sites
            that exceed it are kept and flagged rather than silently removed.
          </CardDescription>
        </CardHeader>
        <CardContent className="space-y-4">
          <div className="grid gap-4 sm:grid-cols-2">
            {applicable.map((definition) => (
              <Field
                key={definition.key}
                label={definition.label}
                htmlFor={`budget-${definition.key}`}
              >
                <NumberInput
                  id={`budget-${definition.key}`}
                  min={0}
                  step={1000}
                  suffix="₹"
                  value={limitByKey[definition.key] ?? ''}
                  onChange={(event) =>
                    setLimit(
                      definition.key,
                      event.target.value === '' ? null : Number(event.target.value),
                    )
                  }
                />
              </Field>
            ))}
          </div>

          {applicable.length === 0 ? (
            <p className="text-ink-muted text-sm">
              No budget fields apply to the selected acquisition mode.
            </p>
          ) : null}
        </CardContent>
      </Card>

      <Card>
        <CardHeader>
          <CardTitle>What should happen when a budget is exceeded?</CardTitle>
          <CardDescription>
            This applies to every budget above.
          </CardDescription>
        </CardHeader>
        <CardContent>
          <fieldset>
            <legend className="sr-only">Budget behaviour</legend>
            <div className="space-y-2">
              <label
                className={cn(
                  'flex cursor-pointer items-start gap-3 rounded-lg border p-3 transition-colors',
                  financial.budgetBehaviour === 'penalise'
                    ? 'border-primary bg-info-subtle'
                    : 'border-line hover:bg-surface-muted',
                )}
              >
                <Radio
                  name="budget-behaviour"
                  value="penalise"
                  checked={financial.budgetBehaviour === 'penalise'}
                  onChange={() => behaviourChanged('penalise')}
                  className="mt-0.5"
                />
                <span>
                  <span className="text-ink flex items-center gap-2 text-[13px] font-medium">
                    <Info className="size-4" aria-hidden="true" />
                    Penalise the site
                  </span>
                  <span className="text-ink-muted mt-0.5 block text-[11px] leading-relaxed">
                    The site stays in the shortlist and is flagged as over budget. Its
                    suitability score is reduced.
                  </span>
                </span>
              </label>

              <label
                className={cn(
                  'flex cursor-pointer items-start gap-3 rounded-lg border p-3 transition-colors',
                  financial.budgetBehaviour === 'hard'
                    ? 'border-primary bg-info-subtle'
                    : 'border-line hover:bg-surface-muted',
                )}
              >
                <Radio
                  name="budget-behaviour"
                  value="hard"
                  checked={financial.budgetBehaviour === 'hard'}
                  onChange={() => behaviourChanged('hard')}
                  className="mt-0.5"
                />
                <span>
                  <span className="text-ink flex items-center gap-2 text-[13px] font-medium">
                    <AlertTriangle className="size-4" aria-hidden="true" />
                    Exclude the site
                  </span>
                  <span className="text-ink-muted mt-0.5 block text-[11px] leading-relaxed">
                    Any site whose cost exceeds a budget is removed from the shortlist
                    entirely.
                  </span>
                </span>
              </label>
            </div>
          </fieldset>

          <FieldHint className="mt-3">
            Where a cost component is not published, the platform reports the budget as
            partially assessed. It never treats missing data as a pass.
          </FieldHint>
        </CardContent>
      </Card>
    </div>
  )
}
