'use client'

import * as React from 'react'
import { CircleAlert, CircleCheck, Info } from 'lucide-react'

import { Badge, StatusDot } from '@/components/ui/badge'
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from '@/components/ui/card'
import { ChartFrame, StackedBar, type ChartTone } from '@/components/ui/chart'
import { EmptyState } from '@/components/ui/feedback'
import { Table, TableBody, TableCell, TableHead, TableHeader, TableRow } from '@/components/ui/table'
import { formatMoney, formatNumber, UNAVAILABLE } from '@/lib/format'
import type { CostAssessment, CostLine, CostOfOwnership, CostProvenance } from '@/lib/types'

import { useWorkspace } from './workspace-context'

const PROVENANCE_TONE: Record<CostProvenance, 'success' | 'info' | 'warning' | 'neutral'> = {
  verified_listed: 'success',
  user_provided: 'info',
  estimated: 'warning',
  calculated: 'info',
  unavailable: 'neutral',
}

const CATEGORY_LABEL: Record<string, string> = {
  acquisition: 'Acquisition',
  setup: 'Setup',
  recurring: 'Recurring',
}

function ProvenanceBadge({ line }: { line: CostLine }) {
  return (
    <Badge tone={PROVENANCE_TONE[line.provenance] ?? 'neutral'}>
      <StatusDot tone={PROVENANCE_TONE[line.provenance] ?? 'neutral'} />
      {line.provenance_label}
    </Badge>
  )
}

function CostTable({ assessment }: { assessment: CostAssessment }) {
  const grouped = React.useMemo(() => {
    const groups: Record<string, CostLine[]> = { acquisition: [], setup: [], recurring: [] }
    for (const line of assessment.lines) {
      groups[line.category]?.push(line)
    }
    return groups
  }, [assessment])

  return (
    <div className="space-y-4">
      {Object.entries(grouped).map(([category, lines]) =>
        lines.length === 0 ? null : (
          <div key={category}>
            <h4 className="section-eyebrow mb-1.5">{CATEGORY_LABEL[category]}</h4>
            <div className="border-line overflow-hidden rounded-md border">
              <Table>
                <TableHeader>
                  <TableRow>
                    <TableHead>Item</TableHead>
                    <TableHead className="w-32">Provenance</TableHead>
                    <TableHead className="w-32 text-right">Amount</TableHead>
                  </TableRow>
                </TableHeader>
                <TableBody>
                  {lines.map((line) => (
                    <TableRow key={line.key}>
                      <TableCell>
                        <span className="text-ink block text-xs font-medium">{line.label}</span>
                        {line.note ? (
                          <span className="text-ink-subtle block text-[11px]">{line.note}</span>
                        ) : null}
                      </TableCell>
                      <TableCell>
                        <ProvenanceBadge line={line} />
                      </TableCell>
                      <TableCell className="text-ink text-right text-xs font-semibold tabular-nums">
                        {line.amount === null ? (
                          <span className="text-ink-subtle font-normal">{UNAVAILABLE}</span>
                        ) : (
                          formatMoney(line.amount)
                        )}
                      </TableCell>
                    </TableRow>
                  ))}
                </TableBody>
              </Table>
            </div>
          </div>
        ),
      )}
    </div>
  )
}

/**
 * The cost of ownership over the horizon.
 *
 * The total is only shown when every component of the cost picture is
 * known.  Otherwise the known part is shown as a minimum and the missing
 * components are named, so an incomplete figure is never mistaken for a
 * total.
 */
function OwnershipSummary({ ownership }: { ownership: CostOfOwnership }) {
  const months = formatNumber(ownership.horizon_months)
  const complete = ownership.is_complete && ownership.total_cost_of_ownership !== null

  return (
    <div className="border-line rounded-md border p-4">
      <h4 className="section-eyebrow mb-1.5">Total cost of ownership</h4>
      <div className="flex flex-wrap items-baseline justify-between gap-2">
        <p className="text-ink text-[13px] font-medium">Over {months} months</p>
        <p className="text-ink text-xs font-semibold tabular-nums">
          {complete ? (
            formatMoney(ownership.total_cost_of_ownership)
          ) : (
            <span title="The known part of the cost of ownership">
              ≥ {formatMoney(ownership.known_minimum)}
            </span>
          )}
        </p>
      </div>
      <p className="text-ink-muted mt-1 text-[11px] leading-relaxed">
        {complete ? (
          <>Every component of the cost picture is known, so this is the total cost of ownership over the horizon.</>
        ) : (
          <>
            The total is not known: {ownership.missing.join(' and ')} could not be
            established. The figure shown is the known minimum, not a total.
          </>
        )}
      </p>
      <dl className="text-ink-muted mt-2.5 flex flex-wrap gap-x-6 gap-y-1.5 text-[11px]">
        <div>
          <dt className="text-ink-subtle">Initial investment</dt>
          <dd className="tabular-nums">
            {ownership.initial_investment === null
              ? UNAVAILABLE
              : formatMoney(ownership.initial_investment)}
          </dd>
        </div>
        <div>
          <dt className="text-ink-subtle">Recurring over {months} months</dt>
          <dd className="tabular-nums">
            {ownership.recurring_total === null
              ? UNAVAILABLE
              : formatMoney(ownership.recurring_total)}
          </dd>
        </div>
      </dl>
    </div>
  )
}

/**
 * The composition of the cost of ownership.
 *
 * The recurring component is the cost over the ownership horizon, so the
 * three parts add up to the cost of ownership rather than mixing a
 * one-off amount with a monthly one.
 */
function CostComposition({ assessment }: { assessment: CostAssessment }) {
  const ownership = assessment.cost_of_ownership
  const horizon = ownership?.horizon_months ?? null

  const segments = React.useMemo(
    () => [
      {
        key: 'acquisition',
        label: 'Acquisition',
        value: assessment.totals.acquisition_total,
        tone: 'info' as ChartTone,
      },
      {
        key: 'setup',
        label: 'Setup',
        value: assessment.totals.setup_total,
        tone: 'warning' as ChartTone,
      },
      {
        key: 'recurring',
        label: horizon ? `Recurring over ${formatNumber(horizon)} months` : 'Recurring',
        value: ownership?.recurring_total ?? null,
        tone: 'success' as ChartTone,
      },
    ],
    [assessment.totals, ownership, horizon],
  )

  const known = segments.filter((segment) => segment.value !== null)

  return (
    <ChartFrame
      title="Cost composition"
      description={
        horizon
          ? `How the cost of ownership over ${formatNumber(horizon)} months is made up. A component that could not be established is left out of the bar and reported in the legend.`
          : 'How the cost of ownership is made up. A component that could not be established is left out of the bar and reported in the legend.'
      }
    >
      {known.length === 0 ? (
        <p className="text-ink-subtle text-xs leading-relaxed">
          No cost component could be established for this site, so there is nothing
          to chart. The lines above show which components were missing.
        </p>
      ) : (
        <StackedBar segments={segments} formatValue={formatMoney} />
      )}
    </ChartFrame>
  )
}

/**
 * Cost analysis.
 *
 * Every figure carries its provenance, and an incomplete cost picture is
 * reported as incomplete rather than being presented as a total.
 */
export function CostPanel() {
  const { evaluation, selectedSiteId, siteById } = useWorkspace()

  const assessments = React.useMemo(
    () =>
      (evaluation?.sites ?? [])
        .map((item) => item.evaluation.cost)
        .filter((cost): cost is CostAssessment => cost !== null),
    [evaluation],
  )

  const selected = assessments.find((item) => item.site_id === selectedSiteId) ?? null

  if (!evaluation) {
    return (
      <Card>
        <CardHeader>
          <CardTitle>Cost analysis</CardTitle>
          <CardDescription>
            Confirm the analysis requirements to assess the cost position of each site.
          </CardDescription>
        </CardHeader>
        <CardContent className="p-0">
          <EmptyState
            icon={Info}
            title="No cost assessment yet"
            description="The cost analysis runs alongside the requirement evaluation. Confirm the analysis requirements to produce it."
          />
        </CardContent>
      </Card>
    )
  }

  return (
    <div className="space-y-5">
      <Card>
        <CardHeader>
          <CardTitle>Cost position across the shortlist</CardTitle>
          <CardDescription>
            Amounts are shown only where a defensible value exists. Where a component is
            unavailable, the total is reported as incomplete rather than estimated.
          </CardDescription>
        </CardHeader>
        <CardContent className="p-0">
          <Table>
            <TableHeader>
              <TableRow>
                <TableHead>Site</TableHead>
                <TableHead className="text-right">Acquisition</TableHead>
                <TableHead className="text-right">Setup</TableHead>
                <TableHead className="text-right">Initial investment</TableHead>
                <TableHead className="text-right">Monthly</TableHead>
                <TableHead className="text-right">Annual</TableHead>
                <TableHead className="text-right">Total cost of ownership</TableHead>
                <TableHead className="w-32">Completeness</TableHead>
              </TableRow>
            </TableHeader>
            <TableBody>
              {assessments.map((assessment) => {
                const site = siteById[assessment.site_id]
                const totals = assessment.totals
                return (
                  <TableRow key={assessment.site_id}>
                    <TableCell className="text-ink font-medium">
                      {site?.name || `Site ${assessment.site_id}`}
                    </TableCell>
                    <TableCell className="text-right text-xs tabular-nums">
                      {totals.acquisition_total === null ? (
                        <span className="text-ink-subtle">{UNAVAILABLE}</span>
                      ) : (
                        formatMoney(totals.acquisition_total)
                      )}
                    </TableCell>
                    <TableCell className="text-right text-xs tabular-nums">
                      {totals.setup_total === null ? (
                        <span className="text-ink-subtle">{UNAVAILABLE}</span>
                      ) : (
                        formatMoney(totals.setup_total)
                      )}
                    </TableCell>
                    <TableCell className="text-right text-xs font-semibold tabular-nums">
                      {totals.initial_investment_total === null ? (
                        <span className="text-ink-subtle font-normal">
                          {totals.known_minimum_initial_investment > 0
                            ? `≥ ${formatMoney(totals.known_minimum_initial_investment)}`
                            : UNAVAILABLE}
                        </span>
                      ) : (
                        formatMoney(totals.initial_investment_total)
                      )}
                    </TableCell>
                    <TableCell className="text-right text-xs tabular-nums">
                      {totals.recurring_monthly_total === null ? (
                        <span className="text-ink-subtle">{UNAVAILABLE}</span>
                      ) : (
                        formatMoney(totals.recurring_monthly_total)
                      )}
                    </TableCell>
                    <TableCell className="text-right text-xs tabular-nums">
                      {totals.recurring_annual_total === null ? (
                        <span className="text-ink-subtle">{UNAVAILABLE}</span>
                      ) : (
                        formatMoney(totals.recurring_annual_total)
                      )}
                    </TableCell>
                    <TableCell
                      className="text-right text-xs font-semibold tabular-nums"
                      title={
                        assessment.cost_of_ownership
                          ? `Over ${formatNumber(assessment.cost_of_ownership.horizon_months)} months`
                          : undefined
                      }
                    >
                      {assessment.cost_of_ownership ? (
                        assessment.cost_of_ownership.is_complete &&
                        assessment.cost_of_ownership.total_cost_of_ownership !== null ? (
                          formatMoney(assessment.cost_of_ownership.total_cost_of_ownership)
                        ) : (
                          <span
                            className="text-ink-subtle font-normal"
                            title={`Known minimum. Missing: ${
                              assessment.cost_of_ownership.missing.join(', ') || 'unknown components'
                            }`}
                          >
                            ≥ {formatMoney(assessment.cost_of_ownership.known_minimum)}
                          </span>
                        )
                      ) : (
                        <span className="text-ink-subtle font-normal">{UNAVAILABLE}</span>
                      )}
                    </TableCell>
                    <TableCell>
                      {totals.is_complete ? (
                        <Badge tone="success">
                          <CircleCheck className="size-3" aria-hidden="true" />
                          Complete
                        </Badge>
                      ) : (
                        <Badge tone="warning">
                          <CircleAlert className="size-3" aria-hidden="true" />
                          {assessment.missing_components.length} missing
                        </Badge>
                      )}
                    </TableCell>
                  </TableRow>
                )
              })}
            </TableBody>
          </Table>
        </CardContent>
      </Card>

      {selected ? (
        <Card>
          <CardHeader>
            <CardTitle>
              Cost detail — {siteById[selected.site_id]?.name || `Site ${selected.site_id}`}
            </CardTitle>
            <CardDescription>
              Every line records where the figure came from. Budget comparisons are
              shown underneath.
            </CardDescription>
          </CardHeader>
          <CardContent className="space-y-5">
            <CostTable assessment={selected} />

            {selected.cost_of_ownership ? (
              <OwnershipSummary ownership={selected.cost_of_ownership} />
            ) : null}

            <CostComposition assessment={selected} />

            {selected.budget_results.length > 0 ? (
              <div>
                <h4 className="section-eyebrow mb-1.5">Budget comparison</h4>
                <ul className="border-line divide-line divide-y rounded-md border">
                  {selected.budget_results.map((result) => (
                    <li
                      key={result.key}
                      className="flex flex-wrap items-center justify-between gap-3 px-3 py-2"
                    >
                      <span className="min-w-0">
                        <span className="text-ink block text-xs font-medium">{result.label}</span>
                        <span className="text-ink-subtle block text-[11px]">{result.detail}</span>
                      </span>
                      <span className="flex shrink-0 items-center gap-2">
                        {result.limit !== null ? (
                          <span className="text-ink-muted text-xs tabular-nums">
                            Budget {formatMoney(result.limit)}
                          </span>
                        ) : null}
                        <Badge
                          tone={
                            result.status === 'within_budget'
                              ? 'success'
                              : result.status === 'over_budget'
                                ? 'danger'
                                : result.status === 'partially_assessed'
                                  ? 'warning'
                                  : 'neutral'
                          }
                        >
                          {result.status === 'within_budget'
                            ? 'Within budget'
                            : result.status === 'over_budget'
                              ? 'Over budget'
                              : result.status === 'partially_assessed'
                                ? 'Partially assessed'
                                : 'Not set'}
                        </Badge>
                      </span>
                    </li>
                  ))}
                </ul>
              </div>
            ) : null}

            {selected.notes.length > 0 ? (
              <ul className="text-ink-subtle space-y-1 text-[11px]">
                {selected.notes.map((note) => (
                  <li key={note}>{note}</li>
                ))}
              </ul>
            ) : null}
          </CardContent>
        </Card>
      ) : (
        <Card>
          <CardHeader>
            <CardTitle>Cost detail</CardTitle>
            <CardDescription>Select a site to see its full cost breakdown.</CardDescription>
          </CardHeader>
          <CardContent>
            <p className="text-ink-muted text-sm">
              {formatNumber(assessments.length)} site
              {assessments.length === 1 ? '' : 's'} assessed. Choose one in the shortlist
              to see its line-by-line cost position.
            </p>
          </CardContent>
        </Card>
      )}
    </div>
  )
}
