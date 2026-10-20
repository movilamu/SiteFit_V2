'use client'

import * as React from 'react'
import { ChevronDown, ChevronRight } from 'lucide-react'

import { Card, CardContent, CardDescription, CardHeader, CardTitle } from '@/components/ui/card'
import { ErrorState, LoadingState } from '@/components/ui/feedback'
import { Table, TableBody, TableCell, TableHead, TableHeader, TableRow } from '@/components/ui/table'
import { fetchDecomposition } from '@/lib/api'
import { formatScore } from '@/lib/format'
import type { SiteDecompositionResponse } from '@/lib/types'

/**
 * The full per-criterion breakdown for a site.
 *
 * The aggregate score is produced by the scoring engine itself, so it is
 * always identical to the score shown in the ranking.
 */
export function DecompositionTable({
  siteId,
  weights,
  method = 'weighted_sum',
}: {
  siteId: string | null
  weights: Record<string, number>
  method?: string
}) {
  const [data, setData] = React.useState<SiteDecompositionResponse | null>(null)
  const [loading, setLoading] = React.useState(false)
  const [error, setError] = React.useState<string | null>(null)
  const [retry, setRetry] = React.useState(0)

  const weightKey = JSON.stringify(weights)

  React.useEffect(() => {
    if (!siteId || Object.keys(weights).length === 0) return
    let cancelled = false
    setLoading(true)
    setError(null)
    fetchDecomposition(siteId, weights, method)
      .then((response) => {
        if (!cancelled) setData(response)
      })
      .catch((err: unknown) => {
        if (!cancelled) {
          setError(
            err instanceof Error
              ? err.message
              : 'The score breakdown could not be loaded.',
          )
          setData(null)
        }
      })
      .finally(() => {
        if (!cancelled) setLoading(false)
      })
    return () => {
      cancelled = true
    }
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [siteId, method, weightKey, retry])

  if (!siteId) {
    return (
      <Card>
        <CardHeader>
          <CardTitle>Score breakdown</CardTitle>
          <CardDescription>Select a site to see its per-criterion contribution.</CardDescription>
        </CardHeader>
      </Card>
    )
  }

  if (loading && !data) {
    return (
      <Card>
        <CardContent>
          <LoadingState label="Loading the score breakdown…" />
        </CardContent>
      </Card>
    )
  }

  if (error) {
    return (
      <Card>
        <CardContent className="p-4">
          <ErrorState
            title="The score breakdown could not be loaded"
            description={error}
            onRetry={() => setRetry((value) => value + 1)}
          />
        </CardContent>
      </Card>
    )
  }

  if (!data) return null

  return (
    <Card>
      <CardHeader>
        <div className="flex flex-wrap items-start justify-between gap-3">
          <div>
            <CardTitle>Score breakdown</CardTitle>
            <CardDescription>
              Every criterion that carried weight, and what it contributed.
            </CardDescription>
          </div>
          <div className="text-right">
            <p className="text-ink-subtle text-[10px] tracking-[0.08em] uppercase">
              Total score
            </p>
            <p className="text-ink text-lg font-semibold tabular-nums">
              {formatScore(data.total_score)}
            </p>
            {data.rank ? (
              <p className="text-ink-subtle text-[11px]">Rank {data.rank}</p>
            ) : null}
          </div>
        </div>
      </CardHeader>
      <CardContent className="p-0">
        <Table>
          <TableHeader>
            <TableRow>
              <TableHead>Criterion</TableHead>
              <TableHead className="w-36">Category</TableHead>
              <TableHead className="w-28 text-right">Value</TableHead>
              <TableHead className="w-24 text-right">Weight</TableHead>
              <TableHead className="w-28 text-right">Contribution</TableHead>
            </TableRow>
          </TableHeader>
          <TableBody>
            {data.criteria.map((criterion) => (
              <TableRow key={criterion.criterion}>
                <TableCell>
                  <span className="text-ink block text-xs font-medium">{criterion.label}</span>
                  <span className="text-ink-subtle block text-[11px]">
                    {criterion.direction === 'cost'
                      ? 'Lower is better'
                      : criterion.direction === 'benefit'
                        ? 'Higher is better'
                        : 'Target band'}
                  </span>
                </TableCell>
                <TableCell className="text-ink-muted text-xs">{criterion.category}</TableCell>
                <TableCell className="text-right text-xs tabular-nums">
                  {formatScore(criterion.normalized_value)}
                </TableCell>
                <TableCell className="text-right text-xs tabular-nums">
                  {formatScore(criterion.weight, 3)}
                </TableCell>
                <TableCell className="text-ink text-right text-xs font-semibold tabular-nums">
                  {formatScore(criterion.contribution, 4)}
                </TableCell>
              </TableRow>
            ))}
          </TableBody>
        </Table>
        {data.dropped_criteria.length > 0 ? (
          <p className="text-ink-subtle border-line border-t px-4 py-2.5 text-[11px] leading-relaxed">
            {data.dropped_criteria.length} criteria had no data in the current release and
            did not contribute. Coverage of the requested weight:{' '}
            {formatScore(data.coverage * 100, 0)}%.
          </p>
        ) : null}
      </CardContent>
    </Card>
  )
}
