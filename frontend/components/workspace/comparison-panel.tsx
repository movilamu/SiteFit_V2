'use client'

import * as React from 'react'
import { Check, Info } from 'lucide-react'

import { Badge } from '@/components/ui/badge'
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from '@/components/ui/card'
import { EmptyState } from '@/components/ui/feedback'
import { Table, TableBody, TableCell, TableHead, TableHeader, TableRow } from '@/components/ui/table'
import { formatMoney, formatScore, UNAVAILABLE } from '@/lib/format'
import { cn } from '@/lib/utils'

import { useWorkspace } from './workspace-context'

const MAX_SITES = 4

type Awards = {
  bestOverall: string | null
  bestValue: string | null
  lowestCost: string | null
  bestRequirementMatch: string | null
}

/**
 * Site comparison.
 *
 * The award labels (best overall, best value, lowest cost, best requirement
 * match) are only shown when the underlying data actually supports them.
 */
export function ComparisonPanel() {
  const { sites, scores, evaluation, siteById, rankOf, scoreOf } = useWorkspace()

  const [selectedIds, setSelectedIds] = React.useState<string[]>([])

  React.useEffect(() => {
    setSelectedIds((current) => {
      const valid = current.filter((id) => siteById[id])
      if (valid.length > 0) return valid
      const first = (scores?.sites ?? []).slice(0, 2).map((row) => String(row.site_id))
      return first
    })
  }, [scores, siteById])

  const toggle = (id: string) => {
    setSelectedIds((current) => {
      if (current.includes(id)) return current.filter((item) => item !== id)
      if (current.length >= MAX_SITES) return current
      return [...current, id]
    })
  }

  const selected = selectedIds
    .map((id) => siteById[id])
    .filter(Boolean)
    .map((site) => {
      const id = String(site.site_id)
      const evaluationEntry = evaluation?.sites.find((item) => item.site_id === id)
      const cost = evaluationEntry?.evaluation.cost ?? null
      return {
        id,
        name: site.name || `Site ${id}`,
        rank: rankOf(id),
        score: scoreOf(id),
        fitRatio: evaluationEntry?.fit_ratio ?? null,
        eligible: evaluationEntry?.eligible ?? null,
        cost,
      }
    })

  const awards = React.useMemo<Awards>(() => {
    if (selected.length < 2) {
      return {
        bestOverall: null,
        bestValue: null,
        lowestCost: null,
        bestRequirementMatch: null,
      }
    }

    const withScore = selected.filter((site) => site.score !== null)
    const bestOverall =
      withScore.length > 0
        ? withScore.reduce((best, site) => ((site.score ?? 0) > (best.score ?? 0) ? site : best))
            .id
        : null

    const withCost = selected.filter(
      (site) =>
        site.cost !== null &&
        site.cost !== undefined &&
        site.cost.totals.initial_investment_total !== null,
    )
    const lowestCost =
      withCost.length > 0
        ? withCost.reduce((best, site) =>
            (site.cost?.totals.initial_investment_total ?? Infinity) <
            (best.cost?.totals.initial_investment_total ?? Infinity)
              ? site
              : best,
          ).id
        : null

    // "Best value" = the highest score per unit of known initial cost.
    const valueScores = selected
      .map((site) => {
        const cost = site.cost ? site.cost.totals.initial_investment_total : null
        if (site.score === null || cost === null || cost <= 0) return null
        return { id: site.id, ratio: site.score / cost }
      })
      .filter((entry): entry is { id: string; ratio: number } => entry !== null)
    const bestValue =
      valueScores.length > 0
        ? valueScores.reduce((best, entry) => (entry.ratio > best.ratio ? entry : best)).id
        : null

    const withFit = selected.filter((site) => site.fitRatio !== null)
    const bestRequirementMatch =
      withFit.length > 0
        ? withFit.reduce((best, site) => ((site.fitRatio ?? 0) > (best.fitRatio ?? 0) ? site : best))
            .id
        : null

    return { bestOverall, bestValue, lowestCost, bestRequirementMatch }
  }, [selected])

  const awardLabels: Record<string, string> = {
    bestOverall: 'Best overall',
    bestValue: 'Best value',
    lowestCost: 'Lowest cost',
    bestRequirementMatch: 'Best requirement match',
  }

  if (sites.length === 0) {
    return (
      <Card>
        <CardContent className="p-0">
          <EmptyState
            title="Nothing to compare yet"
            description="Run an analysis to produce a ranked shortlist that can be compared side by side."
          />
        </CardContent>
      </Card>
    )
  }

  return (
    <div className="space-y-5">
      <Card>
        <CardHeader>
          <CardTitle>Compare sites</CardTitle>
          <CardDescription>
            Select two to four sites to compare their scores, requirement match and cost
            position.
          </CardDescription>
        </CardHeader>
        <CardContent className="space-y-4">
          <div className="grid gap-2 sm:grid-cols-2 lg:grid-cols-4">
            {sites.slice(0, 24).map((site) => {
              const id = String(site.site_id)
              const checked = selectedIds.includes(id)
              const disabled = !checked && selectedIds.length >= MAX_SITES
              return (
                <label
                  key={id}
                  className={cn(
                    'flex cursor-pointer items-center gap-2 rounded-md border p-2.5 text-xs transition-colors',
                    checked
                      ? 'border-primary bg-info-subtle'
                      : 'border-line hover:bg-surface-muted',
                    disabled ? 'cursor-not-allowed opacity-50' : '',
                  )}
                >
                  <input
                    type="checkbox"
                    checked={checked}
                    disabled={disabled}
                    onChange={() => toggle(id)}
                    className="size-3.5"
                  />
                  <span className="text-ink min-w-0 truncate font-medium">
                    {site.name || `Site ${id}`}
                  </span>
                </label>
              )
            })}
          </div>
          <p className="text-ink-subtle text-[11px]">
            {selectedIds.length} of {MAX_SITES} selected.
            {selectedIds.length < 2 ? ' Select at least two to compare.' : ''}
          </p>
        </CardContent>
      </Card>

      {selected.length < 2 ? (
        <Card>
          <CardContent className="p-0">
            <EmptyState
              icon={Info}
              title="Select at least two sites"
              description="Pick two or more sites above to see them compared side by side."
            />
          </CardContent>
        </Card>
      ) : (
        <Card>
          <CardHeader>
            <CardTitle>Side-by-side comparison</CardTitle>
            <CardDescription>
              Awards are shown only where the underlying data supports them.
            </CardDescription>
          </CardHeader>
          <CardContent className="p-0">
            <Table>
              <TableHeader>
                <TableRow>
                  <TableHead className="w-56">Measure</TableHead>
                  {selected.map((site) => (
                    <TableHead key={site.id}>
                      <span className="text-ink block">{site.name}</span>
                      <span className="text-ink-subtle block text-[10px] font-normal">
                        Rank {site.rank ?? '—'}
                      </span>
                      <span className="mt-1 flex flex-wrap gap-1">
                        {Object.entries(awards).map(([key, value]) =>
                          value === site.id ? (
                            <Badge key={key} tone="info" className="mt-1">
                              <Check className="size-3" aria-hidden="true" />
                              {awardLabels[key]}
                            </Badge>
                          ) : null,
                        )}
                      </span>
                    </TableHead>
                  ))}
                </TableRow>
              </TableHeader>
              <TableBody>
                <TableRow>
                  <TableCell className="text-ink-muted text-xs font-medium">Overall score</TableCell>
                  {selected.map((site) => (
                    <TableCell
                      key={site.id}
                      className="text-ink text-sm font-semibold tabular-nums"
                    >
                      {formatScore(site.score)}
                    </TableCell>
                  ))}
                </TableRow>

                <TableRow>
                  <TableCell className="text-ink-muted text-xs font-medium">
                    Requirement match
                  </TableCell>
                  {selected.map((site) => (
                    <TableCell key={site.id} className="text-xs tabular-nums">
                      {site.fitRatio === null ? (
                        <span className="text-ink-subtle">Not assessed</span>
                      ) : (
                        <span
                          className={cn(
                            'font-medium',
                            site.eligible === false ? 'text-danger' : 'text-ink',
                          )}
                        >
                          {formatScore(site.fitRatio)}
                          {site.eligible === false ? ' (excluded)' : ''}
                        </span>
                      )}
                    </TableCell>
                  ))}
                </TableRow>

                <TableRow>
                  <TableCell className="text-ink-muted text-xs font-medium">
                    Initial investment
                  </TableCell>
                  {selected.map((site) => {
                    const total = site.cost?.totals.initial_investment_total ?? null
                    const known =
                      site.cost?.totals.known_minimum_initial_investment ?? 0
                    return (
                      <TableCell key={site.id} className="text-xs tabular-nums">
                        {total === null ? (
                          <span className="text-ink-subtle">
                            {known > 0 ? `≥ ${formatMoney(known)}` : UNAVAILABLE}
                          </span>
                        ) : (
                          <span className="text-ink font-medium">{formatMoney(total)}</span>
                        )}
                      </TableCell>
                    )
                  })}
                </TableRow>

                <TableRow>
                  <TableCell className="text-ink-muted text-xs font-medium">Monthly cost</TableCell>
                  {selected.map((site) => {
                    const total = site.cost?.totals.recurring_monthly_total ?? null
                    return (
                      <TableCell key={site.id} className="text-xs tabular-nums">
                        {total === null ? (
                          <span className="text-ink-subtle">{UNAVAILABLE}</span>
                        ) : (
                          formatMoney(total)
                        )}
                      </TableCell>
                    )
                  })}
                </TableRow>

                <TableRow>
                  <TableCell className="text-ink-muted text-xs font-medium">Cost completeness</TableCell>
                  {selected.map((site) => (
                    <TableCell key={site.id} className="text-xs">
                      {site.cost === null ? (
                        <span className="text-ink-subtle">Not assessed</span>
                      ) : site.cost.totals.is_complete ? (
                        <Badge tone="success">Complete</Badge>
                      ) : (
                        <Badge tone="warning">
                          {site.cost.missing_components.length} components missing
                        </Badge>
                      )}
                    </TableCell>
                  ))}
                </TableRow>

                <TableRow>
                  <TableCell className="text-ink-muted text-xs font-medium">
                    Hard-requirement status
                  </TableCell>
                  {selected.map((site) => (
                    <TableCell key={site.id} className="text-xs">
                      {site.eligible === null ? (
                        <span className="text-ink-subtle">Not assessed</span>
                      ) : site.eligible ? (
                        <Badge tone="success">Meets requirements</Badge>
                      ) : (
                        <Badge tone="danger">Excluded</Badge>
                      )}
                    </TableCell>
                  ))}
                </TableRow>
              </TableBody>
            </Table>
          </CardContent>
        </Card>
      )}
    </div>
  )
}
