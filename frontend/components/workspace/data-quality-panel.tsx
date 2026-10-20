'use client'

import * as React from 'react'
import { AlertTriangle, CircleCheck, Info, RefreshCw } from 'lucide-react'

import { Badge, StatusDot } from '@/components/ui/badge'
import { Button } from '@/components/ui/button'
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from '@/components/ui/card'
import { ErrorState, LoadingState } from '@/components/ui/feedback'
import { Meter } from '@/components/ui/progress'
import { Table, TableBody, TableCell, TableHead, TableHeader, TableRow } from '@/components/ui/table'
import { fetchDataQuality } from '@/lib/api'
import { formatPercent } from '@/lib/format'
import type { DataQualityResponse } from '@/lib/types'

const GRADE_TONE = {
  good: 'success',
  fair: 'warning',
  poor: 'danger',
} as const

const SEVERITY_TONE = {
  high: 'danger',
  medium: 'warning',
  low: 'neutral',
} as const

/**
 * Data quality and confidence.
 *
 * Every figure here is a deterministic coverage or freshness measure taken
 * from the platform's own records.  No synthetic confidence score is
 * produced, and the known limitations are stated rather than hidden.
 */
export function DataQualityPanel() {
  const [data, setData] = React.useState<DataQualityResponse | null>(null)
  const [loading, setLoading] = React.useState(true)
  const [error, setError] = React.useState<string | null>(null)
  const [retry, setRetry] = React.useState(0)

  React.useEffect(() => {
    let cancelled = false
    setLoading(true)
    setError(null)
    fetchDataQuality()
      .then((response) => {
        if (!cancelled) setData(response)
      })
      .catch((err: unknown) => {
        if (!cancelled) {
          setError(
            err instanceof Error ? err.message : 'The data quality report could not be loaded.',
          )
        }
      })
      .finally(() => {
        if (!cancelled) setLoading(false)
      })
    return () => {
      cancelled = true
    }
  }, [retry])

  if (loading && !data) {
    return (
      <Card>
        <CardHeader>
          <CardTitle>Data quality</CardTitle>
          <CardDescription>Assessing coverage across the data sources…</CardDescription>
        </CardHeader>
        <CardContent>
          <LoadingState label="Loading the data quality report…" />
        </CardContent>
      </Card>
    )
  }

  if (error) {
    return (
      <Card>
        <CardHeader>
          <CardTitle>Data quality</CardTitle>
        </CardHeader>
        <CardContent>
          <ErrorState
            title="The data quality report could not be loaded"
            description={error}
            onRetry={() => setRetry((value) => value + 1)}
          />
        </CardContent>
      </Card>
    )
  }

  if (!data) return null

  const summary = data.summary

  return (
    <div className="space-y-5">
      <Card>
        <CardHeader>
          <div className="flex flex-wrap items-start justify-between gap-3">
            <div>
              <CardTitle>Data quality & confidence</CardTitle>
              <CardDescription>
                What the evidence behind this analysis can and cannot support.
              </CardDescription>
            </div>
            <Button
              type="button"
              variant="outline"
              size="sm"
              onClick={() => setRetry((value) => value + 1)}
              disabled={loading}
            >
              {loading ? <RefreshCw className="animate-spin" /> : <RefreshCw />}
              Refresh
            </Button>
          </div>
        </CardHeader>
        <CardContent className="space-y-4">
          <div className="grid gap-3 sm:grid-cols-3">
            <div className="border-line rounded-md border p-3">
              <p className="section-eyebrow">Criterion coverage</p>
              <p className="text-ink mt-1.5 text-lg font-semibold tabular-nums">
                {formatPercent(summary.criteria_coverage, 0)}
              </p>
              <Badge tone={GRADE_TONE[summary.criteria_coverage_grade as keyof typeof GRADE_TONE] ?? 'neutral'} className="mt-1.5">
                {summary.criteria_coverage_grade}
              </Badge>
            </div>
            <div className="border-line rounded-md border p-3">
              <p className="section-eyebrow">Source availability</p>
              <p className="text-ink mt-1.5 text-lg font-semibold tabular-nums">
                {summary.usable_source_count} of {summary.total_source_count}
              </p>
              <p className="text-ink-subtle mt-1 text-[11px]">tables could be queried</p>
            </div>
            <div className="border-line rounded-md border p-3">
              <p className="section-eyebrow">Backtest</p>
              <p className="text-ink mt-1.5 text-lg font-semibold">
                {summary.backtest_available ? 'Available' : 'Not available'}
              </p>
              <p className="text-ink-subtle mt-1 text-[11px]">
                {summary.backtest_available
                  ? 'The model can be validated against trading performance.'
                  : 'No own-estate records to validate against yet.'}
              </p>
            </div>
          </div>

          <Meter
            label="Criterion coverage"
            value={summary.criteria_coverage}
            max={1}
            tone={
              summary.criteria_coverage_grade === 'good'
                ? 'success'
                : summary.criteria_coverage_grade === 'fair'
                  ? 'warning'
                  : 'danger'
            }
            valueLabel={formatPercent(summary.criteria_coverage, 0)}
          />

          <p className="text-ink-subtle text-[11px] leading-relaxed">
            {summary.grading_rule}
          </p>
        </CardContent>
      </Card>

      <Card>
        <CardHeader>
          <CardTitle>Source coverage</CardTitle>
          <CardDescription>
            Which underlying datasets could be queried for this analysis.
          </CardDescription>
        </CardHeader>
        <CardContent className="p-0">
          <Table>
            <TableHeader>
              <TableRow>
                <TableHead>Source</TableHead>
                <TableHead>Origin</TableHead>
                <TableHead className="w-40">Status</TableHead>
              </TableRow>
            </TableHeader>
            <TableBody>
              {data.sources.map((source) => (
                <TableRow key={source.table}>
                  <TableCell className="text-ink text-xs font-medium">{source.label}</TableCell>
                  <TableCell className="text-ink-muted text-xs">{source.origin}</TableCell>
                  <TableCell>
                    {source.available ? (
                      <Badge tone={source.has_rows ? 'success' : 'warning'}>
                        <StatusDot tone={source.has_rows ? 'success' : 'warning'} />
                        {source.has_rows ? 'Has records' : 'No records'}
                      </Badge>
                    ) : (
                      <Badge tone="neutral">
                        <StatusDot tone="neutral" />
                        Unavailable
                      </Badge>
                    )}
                  </TableCell>
                </TableRow>
              ))}
            </TableBody>
          </Table>
        </CardContent>
      </Card>

      <Card>
        <CardHeader>
          <CardTitle>Criterion availability</CardTitle>
          <CardDescription>
            Criteria without data in the current release are excluded from scoring and
            their weight is redistributed.
          </CardDescription>
        </CardHeader>
        <CardContent className="p-0">
          <Table>
            <TableHeader>
              <TableRow>
                <TableHead>Criterion</TableHead>
                <TableHead>Category</TableHead>
                <TableHead className="w-32">Direction</TableHead>
                <TableHead className="w-40">Status</TableHead>
              </TableRow>
            </TableHeader>
            <TableBody>
              {data.criteria.map((criterion) => (
                <TableRow key={criterion.criterion}>
                  <TableCell className="text-ink text-xs font-medium">{criterion.label}</TableCell>
                  <TableCell className="text-ink-muted text-xs">{criterion.category}</TableCell>
                  <TableCell className="text-ink-muted text-xs capitalize">
                    {criterion.direction ?? 'Target band'}
                  </TableCell>
                  <TableCell>
                    {criterion.data_available ? (
                      <Badge tone="success">
                        <CircleCheck className="size-3" aria-hidden="true" />
                        Scored
                      </Badge>
                    ) : (
                      <Badge tone="warning">
                        <AlertTriangle className="size-3" aria-hidden="true" />
                        No data
                      </Badge>
                    )}
                  </TableCell>
                </TableRow>
              ))}
            </TableBody>
          </Table>
        </CardContent>
      </Card>

      <Card>
        <CardHeader>
          <CardTitle>Known limitations</CardTitle>
          <CardDescription>
            These constraints apply to every result in this platform and are not specific
            to one analysis.
          </CardDescription>
        </CardHeader>
        <CardContent className="space-y-3">
          {data.limitations.map((limitation) => (
            <div key={limitation.id} className="border-line rounded-md border p-3">
              <div className="flex flex-wrap items-start justify-between gap-2">
                <p className="text-ink text-[13px] font-medium">{limitation.title}</p>
                <Badge tone={SEVERITY_TONE[limitation.severity as keyof typeof SEVERITY_TONE] ?? 'neutral'}>
                  {limitation.severity} impact
                </Badge>
              </div>
              <p className="text-ink-muted mt-1 text-xs leading-relaxed">{limitation.detail}</p>
            </div>
          ))}
        </CardContent>
      </Card>

      <p className="text-ink-subtle flex items-start gap-1.5 text-[11px] leading-relaxed">
        <Info className="mt-0.5 size-3.5 shrink-0" aria-hidden="true" />
        The grade above measures how much of the configured model the available data can
        support. It is not a measure of how accurate the ranking is.
      </p>
    </div>
  )
}
