'use client'

import * as React from 'react'
import { ChevronDown, ChevronRight, RotateCcw, Scale } from 'lucide-react'

import { Badge } from '@/components/ui/badge'
import { Button } from '@/components/ui/button'
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from '@/components/ui/card'
import { Slider } from '@/components/ui/input'
import { Tooltip } from '@/components/ui/tooltip'
import { equalCategoryWeights, equalLeafWeights, normalizeWeights, weightSum } from '@/lib/criteria'
import { formatPercent, formatScore } from '@/lib/format'
import { cn } from '@/lib/utils'

import { useWorkspace } from './workspace-context'

const METHOD_OPTIONS = [
  {
    value: 'weighted_sum',
    label: 'Weighted sum (SAW)',
    hint: 'Fully compensatory: a strong criterion can offset a weak one.',
  },
  {
    value: 'weighted_product',
    label: 'Weighted product (WPM)',
    hint: 'Partially compensatory: one very weak criterion penalises the whole score.',
  },
  {
    value: 'distance_to_ideal',
    label: 'Distance to ideal (TOPSIS)',
    hint: 'Scores each site on its distance to the best and worst observed value.',
  },
]

/**
 * The weight model.
 *
 * The user sets weights over the eight criteria categories; within a
 * category the leaves can be refined.  The roll-down to the 28 leaf
 * criteria is performed by the backend so that the interface and the
 * ranking always use the same arithmetic.
 */
export function WeightPanel() {
  const {
    criteria,
    weights,
    method,
    scores,
    setWeights,
    setMethod,
  } = useWorkspace()

  const [expanded, setExpanded] = React.useState<string | null>(null)

  const categoryWeights = React.useMemo(
    () => weights.category_weights ?? {},
    [weights.category_weights],
  )
  const leafWeights = React.useMemo(
    () => weights.leaf_weights ?? {},
    [weights.leaf_weights],
  )

  const total = weightSum(categoryWeights)
  const isBalanced = Math.abs(total - 1) <= 0.01

  const setCategoryWeight = React.useCallback(
    (key: string, value: number) => {
      setWeights({
        ...weights,
        category_weights: { ...categoryWeights, [key]: value },
      })
    },
    [categoryWeights, setWeights, weights],
  )

  const setLeafWeight = React.useCallback(
    (categoryKey: string, leafKey: string, value: number) => {
      setWeights({
        ...weights,
        leaf_weights: {
          ...leafWeights,
          [categoryKey]: { ...(leafWeights[categoryKey] ?? {}), [leafKey]: value },
        },
      })
    },
    [leafWeights, setWeights, weights],
  )

  const normalise = () => {
    setWeights({
      ...weights,
      category_weights: normalizeWeights(categoryWeights),
    })
  }

  const reset = () => {
    setWeights({
      category_weights: equalCategoryWeights(criteria),
      leaf_weights: equalLeafWeights(criteria),
    })
  }

  if (!criteria) {
    return (
      <Card>
        <CardHeader>
          <CardTitle>Weights</CardTitle>
          <CardDescription>Loading the criteria hierarchy…</CardDescription>
        </CardHeader>
        <CardContent>
          <div className="space-y-3">
            {Array.from({ length: 6 }).map((_, index) => (
              <div key={index} className="bg-surface-muted h-12 animate-pulse rounded-md" />
            ))}
          </div>
        </CardContent>
      </Card>
    )
  }

  return (
    <Card>
      <CardHeader>
        <div className="flex flex-wrap items-start justify-between gap-3">
          <div>
            <CardTitle>Criteria weights</CardTitle>
            <CardDescription>
              Set how much each criterion matters. The ranking updates as you change them.
            </CardDescription>
          </div>
          <Badge tone={isBalanced ? 'success' : 'warning'}>
            Sum {total.toFixed(2)}
          </Badge>
        </div>
      </CardHeader>

      <CardContent className="space-y-4">
        {/* Aggregation method */}
        <div className="border-line bg-surface-muted rounded-md border p-3">
          <div className="flex items-start gap-2">
            <Scale className="text-ink-subtle mt-0.5 size-3.5 shrink-0" aria-hidden="true" />
            <div className="min-w-0 flex-1">
              <label
                htmlFor="aggregation-method"
                className="text-ink block text-[11px] font-semibold tracking-[0.06em] uppercase"
              >
                Aggregation method
              </label>
              <select
                id="aggregation-method"
                value={method}
                onChange={(event) => setMethod(event.target.value)}
                className="border-line bg-surface text-ink mt-1.5 h-9 w-full rounded-md border px-3 text-sm"
              >
                {METHOD_OPTIONS.map((option) => (
                  <option key={option.value} value={option.value}>
                    {option.label}
                  </option>
                ))}
              </select>
              <p className="text-ink-subtle mt-1.5 text-[11px] leading-relaxed">
                {METHOD_OPTIONS.find((option) => option.value === method)?.hint}
              </p>
            </div>
          </div>
        </div>

        {/* Category sliders */}
        <ul className="space-y-1.5">
          {criteria.categories.map((category) => {
            const value = categoryWeights[category.key] ?? 0
            const isOpen = expanded === category.key
            const leaves = category.subcategories.flatMap((subcategory) => subcategory.criteria)
            const localWeights = leafWeights[category.key] ?? {}

            return (
              <li key={category.key} className="border-line rounded-md border">
                <div className="flex items-center gap-3 px-3 py-2.5">
                  <button
                    type="button"
                    onClick={() => setExpanded(isOpen ? null : category.key)}
                    aria-expanded={isOpen}
                    className="text-ink-muted hover:text-ink focus-visible:ring-ring flex shrink-0 items-center gap-1 rounded focus-visible:ring-2 focus-visible:outline-none"
                  >
                    {isOpen ? (
                      <ChevronDown className="size-3.5" aria-hidden="true" />
                    ) : (
                      <ChevronRight className="size-3.5" aria-hidden="true" />
                    )}
                    <span className="sr-only">
                      {isOpen ? 'Hide' : 'Show'} the criteria in {category.label}
                    </span>
                  </button>

                  <div className="min-w-0 flex-1">
                    <div className="flex items-baseline justify-between gap-3">
                      <label
                        htmlFor={`weight-${category.key}`}
                        className="text-ink truncate text-[13px] font-medium"
                      >
                        {category.label}
                      </label>
                      <span className="text-ink shrink-0 text-xs font-semibold tabular-nums">
                        {formatPercent(value, 0)}
                      </span>
                    </div>
                    <Slider
                      id={`weight-${category.key}`}
                      min={0}
                      max={1}
                      step={0.01}
                      value={value}
                      onChange={(event) => setCategoryWeight(category.key, Number(event.target.value))}
                      className="mt-1.5"
                    />
                  </div>
                </div>

                {isOpen ? (
                  <ul className="border-line bg-surface-muted space-y-1 border-t px-3 py-2.5">
                    {leaves.map((leaf) => {
                      const leafValue = localWeights[leaf.key] ?? 0
                      return (
                        <li key={leaf.key} className="flex items-center gap-3">
                          <div className="min-w-0 flex-1">
                            <div className="flex items-baseline justify-between gap-3">
                              <span className="text-ink-muted truncate text-xs">
                                {leaf.label}
                              </span>
                              <span className="text-ink-subtle shrink-0 text-[11px] tabular-nums">
                                {formatPercent(leafValue, 0)}
                              </span>
                            </div>
                            <Slider
                              min={0}
                              max={1}
                              step={0.01}
                              value={leafValue}
                              onChange={(event) =>
                                setLeafWeight(category.key, leaf.key, Number(event.target.value))
                              }
                              className="mt-1"
                              aria-label={`${leaf.label} weight within ${category.label}`}
                            />
                          </div>
                          {leaf.data_available ? null : (
                            <Tooltip
                              content="This criterion has no data in the current release, so its weight is redistributed across the criteria that can be scored."
                            >
                              <span className="text-warning shrink-0 text-[10px] font-medium">
                                No data
                              </span>
                            </Tooltip>
                          )}
                        </li>
                      )
                    })}
                  </ul>
                ) : null}
              </li>
            )
          })}
        </ul>

        <div className="flex flex-wrap items-center gap-2 border-t border-line pt-3">
          <Button type="button" variant="outline" size="sm" onClick={normalise}>
            Normalise to 1.00
          </Button>
          <Button type="button" variant="ghost" size="sm" onClick={reset}>
            <RotateCcw />
            Equal weights
          </Button>
        </div>

        {scores ? (
          <div
            className={cn(
              'rounded-md border px-3 py-2.5 text-[11px] leading-relaxed',
              scores.coverage < 0.999
                ? 'border-warning-border bg-warning-subtle text-warning'
                : 'border-line bg-surface-muted text-ink-muted',
            )}
          >
            {scores.coverage < 0.999 ? (
              <>
                <strong className="font-semibold">
                  {formatPercent(scores.coverage, 0)} of the requested weight could be
                  scored.
                </strong>{' '}
                {scores.dropped_criteria.length} criteria have no data in the current
                release and their weight has been redistributed across the criteria
                that could be scored.
              </>
            ) : (
              <>
                All {scores.effective_weights ? Object.keys(scores.effective_weights).length : 0}{' '}
                criteria carrying weight were scored. Effective weight mass:{' '}
                {formatScore(
                  Object.values(scores.effective_weights).reduce((sum, value) => sum + value, 0),
                )}
                .
              </>
            )}
          </div>
        ) : null}
      </CardContent>
    </Card>
  )
}
