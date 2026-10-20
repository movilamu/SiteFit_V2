'use client'

import * as React from 'react'
import { AlertTriangle, Info, RefreshCw } from 'lucide-react'

import { Badge } from '@/components/ui/badge'
import { Button } from '@/components/ui/button'
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from '@/components/ui/card'
import { HorizontalBarChart } from '@/components/ui/chart'
import { ErrorState, LoadingState, Alert } from '@/components/ui/feedback'
import { Table, TableBody, TableCell, TableHead, TableHeader, TableRow } from '@/components/ui/table'
import {
  apiFetch,
  fetchCrossMethod,
  fetchNearTies,
  fetchStability,
  fetchThresholds,
} from '@/lib/api'
import { formatScore } from '@/lib/format'
import { weightsQueryParams } from '@/lib/criteria'
import type {
  CrossMethodAgreement,
  NearTieCluster,
  StabilityRow,
  ThresholdRow,
} from '@/lib/types'

import { useWorkspace } from './workspace-context'

type SensitivityData = {
  thresholds: ThresholdRow[]
  stability: StabilityRow[]
  nearTies: NearTieCluster[]
  crossMethod: CrossMethodAgreement
  reversals: {
    reversals: {
      site_a: string
      site_b: string
      reversal_rate: number
      risk: string
      baseline_a_rank: number
      baseline_b_rank: number
    }[]
    high_risk_count: number
  }
}

function stabilityTone(percentage: number): 'success' | 'warning' | 'danger' {
  if (percentage >= 90) return 'success'
  if (percentage >= 60) return 'warning'
  return 'danger'
}

function stabilityLabel(percentage: number): string {
  if (percentage >= 90) return 'Stable'
  if (percentage >= 60) return 'Moderately sensitive'
  return 'Highly sensitive'
}

/**
 * Sensitivity analysis.
 *
 * The analytical outputs are shown in full for analysts, and are also
 * translated into plain language so that a decision maker can act on them
 * without reading the method.
 */
export function SensitivityPanel() {
  const { weights, method, siteById } = useWorkspace()

  const [data, setData] = React.useState<SensitivityData | null>(null)
  const [loading, setLoading] = React.useState(false)
  const [error, setError] = React.useState<string | null>(null)
  const [retry, setRetry] = React.useState(0)

  const label = (siteId: string) => siteById[siteId]?.name || siteId

  const load = React.useCallback(async () => {
    if (!weights.category_weights) return
    setLoading(true)
    setError(null)
    try {
      // The sensitivity endpoints take leaf weights, so the category
      // weights are rolled down through the same model the ranking uses.
      const rollup = await apiFetch<{ leaf_weights: Record<string, number> }>(
        '/criteria/rollup',
        {
          method: 'POST',
          body: {
            category_weights: weights.category_weights,
            leaf_weights: weights.leaf_weights ?? null,
          },
        },
      )
      if (!rollup?.leaf_weights) {
        throw new Error('The weights could not be resolved for analysis.')
      }
      const leafWeights = rollup.leaf_weights

      const [thresholds, stability, nearTies, crossMethod, reversals] = await Promise.all([
        fetchThresholds(leafWeights, method),
        fetchStability(leafWeights, method),
        fetchNearTies(leafWeights, method),
        fetchCrossMethod(leafWeights, method),
        apiFetch<SensitivityData['reversals']>(
          `/sensitivity/rank-reversals?${weightsQueryParams(leafWeights, method).toString()}`,
        ),
      ])
      setData({ thresholds, stability, nearTies, crossMethod, reversals })
    } catch (err) {
      setError(
        err instanceof Error ? err.message : 'The sensitivity analysis could not be completed.',
      )
    } finally {
      setLoading(false)
    }
  }, [weights, method])

  React.useEffect(() => {
    void load()
  }, [load, retry])

  const leastStable = React.useMemo(() => {
    if (!data?.stability.length) return null
    return [...data.stability].sort(
      (a, b) => a.stability_percentage - b.stability_percentage,
    )[0]
  }, [data])

  const nearestTie = React.useMemo(() => {
    // A cluster of one site is not a near tie, so it is not reported.
    const clusters = (data?.nearTies ?? []).filter((cluster) => cluster.site_ids.length >= 2)
    return clusters[0] ?? null
  }, [data])

  const sensitiveCriteria = React.useMemo(
    () =>
      (data?.thresholds ?? [])
        .filter((row) => row.delta !== null && row.threshold_weight !== null)
        .sort((a, b) => Math.abs(a.delta ?? 0) - Math.abs(b.delta ?? 0))
        .slice(0, 5),
    [data],
  )

  return (
    <div className="space-y-5">
      <Card>
        <CardHeader>
          <div className="flex flex-wrap items-start justify-between gap-3">
            <div>
              <CardTitle>How robust is this ranking?</CardTitle>
              <CardDescription>
                The ranking is re-tested with perturbed weights, alternative aggregation
                methods and near-tie detection.
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
              Re-run
            </Button>
          </div>
        </CardHeader>
        <CardContent className="space-y-4">
          {loading && !data ? <LoadingState label="Running the sensitivity analysis…" /> : null}

          {error ? (
            <ErrorState
              title="The sensitivity analysis could not be completed"
              description={error}
              onRetry={() => setRetry((value) => value + 1)}
            />
          ) : null}

          {data ? (
            <div className="grid gap-3 sm:grid-cols-3">
              <div className="border-line rounded-md border p-3">
                <p className="section-eyebrow">Rank stability</p>
                {leastStable ? (
                  <>
                    <p className="text-ink mt-1.5 text-[13px] font-medium">
                      {label(leastStable.site_id)} holds its rank under{' '}
                      {leastStable.stability_percentage.toFixed(0)}% of the weight
                      changes tested.
                    </p>
                    <Badge tone={stabilityTone(leastStable.stability_percentage)} className="mt-2">
                      {stabilityLabel(leastStable.stability_percentage)}
                    </Badge>
                  </>
                ) : (
                  <p className="text-ink-muted mt-1.5 text-xs">Not available.</p>
                )}
              </div>

              <div className="border-line rounded-md border p-3">
                <p className="section-eyebrow">Near ties</p>
                {nearestTie ? (
                  <>
                    <p className="text-ink mt-1.5 text-[13px] font-medium">
                      {nearestTie.site_ids.map(label).join(', ')} score within{' '}
                      {formatScore(nearestTie.score_range, 4)} of each other.
                    </p>
                    <Badge tone="warning" className="mt-2">
                      Their order could change with a small change in weights
                    </Badge>
                  </>
                ) : (
                  <p className="text-ink-muted mt-1.5 text-xs">
                    No near ties were detected.
                  </p>
                )}
              </div>

              <div className="border-line rounded-md border p-3">
                <p className="section-eyebrow">Method agreement</p>
                {data.crossMethod ? (
                  <>
                    <p className="text-ink mt-1.5 text-[13px] font-medium">
                      The three aggregation methods agree at{' '}
                      {(data.crossMethod.overall_agreement * 100).toFixed(0)}% (Spearman).
                    </p>
                    <Badge
                      tone={
                        data.crossMethod.overall_agreement >= 0.8
                          ? 'success'
                          : data.crossMethod.overall_agreement >= 0.5
                            ? 'warning'
                            : 'danger'
                      }
                      className="mt-2"
                    >
                      {data.crossMethod.flagged_sites.length === 0
                        ? 'No site flagged'
                        : `${data.crossMethod.flagged_sites.length} site${
                            data.crossMethod.flagged_sites.length === 1 ? '' : 's'
                          } flagged`}
                    </Badge>
                  </>
                ) : (
                  <p className="text-ink-muted mt-1.5 text-xs">Not available.</p>
                )}
              </div>
            </div>
          ) : null}
        </CardContent>
      </Card>

      {data ? (
        <>
          <Card>
            <CardHeader>
              <CardTitle>Critical weight thresholds</CardTitle>
              <CardDescription>
                How far each criterion&apos;s weight must move before the leading site
                changes. The most sensitive criteria are listed first.
              </CardDescription>
            </CardHeader>
            <CardContent className="p-0">
              {sensitiveCriteria.length === 0 ? (
                <p className="text-ink-subtle px-5 py-6 text-xs">
                  No criterion changes the leading site within a plausible range, so the
                  top of the ranking is insensitive to the weights.
                </p>
              ) : (
                <Table>
                  <TableHeader>
                    <TableRow>
                      <TableHead>Criterion</TableHead>
                      <TableHead className="text-right">Current</TableHead>
                      <TableHead className="text-right">Threshold</TableHead>
                      <TableHead className="text-right">Change</TableHead>
                      <TableHead>New leader</TableHead>
                    </TableRow>
                  </TableHeader>
                  <TableBody>
                    {sensitiveCriteria.map((row) => (
                      <TableRow key={row.criterion}>
                        <TableCell className="text-ink text-xs font-medium">
                          {row.criterion.replace(/_/g, ' ')}
                        </TableCell>
                        <TableCell className="text-right text-xs tabular-nums">
                          {row.current_weight.toFixed(3)}
                        </TableCell>
                        <TableCell className="text-right text-xs tabular-nums">
                          {row.threshold_weight?.toFixed(3) ?? '—'}
                        </TableCell>
                        <TableCell className="text-right text-xs tabular-nums">
                          {row.delta !== null ? (
                            <Badge
                              tone={
                                Math.abs(row.delta) < 0.1
                                  ? 'warning'
                                  : Math.abs(row.delta) < 0.25
                                    ? 'info'
                                    : 'danger'
                              }
                            >
                              {row.delta > 0 ? '+' : ''}
                              {row.delta.toFixed(3)}
                            </Badge>
                          ) : (
                            '—'
                          )}
                        </TableCell>
                        <TableCell className="text-ink-muted text-xs">
                          {row.new_top_site ? label(String(row.new_top_site)) : '—'}
                        </TableCell>
                      </TableRow>
                    ))}
                  </TableBody>
                </Table>
              )}
            </CardContent>
          </Card>

          <Card>
            <CardHeader>
              <CardTitle>Rank stability by site</CardTitle>
              <CardDescription>
                The share of weight perturbations under which each site keeps its current
                rank.
              </CardDescription>
            </CardHeader>
            <CardContent className="p-0">
              <Table>
                <TableHeader>
                  <TableRow>
                    <TableHead>Site</TableHead>
                    <TableHead className="w-20 text-right">Rank</TableHead>
                    <TableHead className="w-40">Stability</TableHead>
                    <TableHead className="w-32 text-right">% retained</TableHead>
                  </TableRow>
                </TableHeader>
                <TableBody>
                  {data.stability.slice(0, 25).map((row) => (
                    <TableRow key={row.site_id}>
                      <TableCell className="text-ink text-xs font-medium">
                        {label(row.site_id)}
                      </TableCell>
                      <TableCell className="text-right text-xs tabular-nums">
                        {row.current_rank}
                      </TableCell>
                      <TableCell>
                        <Badge tone={stabilityTone(row.stability_percentage)}>
                          {stabilityLabel(row.stability_percentage)}
                        </Badge>
                      </TableCell>
                      <TableCell className="text-right text-xs font-semibold tabular-nums">
                        {row.stability_percentage.toFixed(0)}%
                      </TableCell>
                    </TableRow>
                  ))}
                </TableBody>
              </Table>

              <div className="border-line border-t px-5 py-4">
                <h4 className="section-eyebrow mb-2">Rank retention at a glance</h4>
                <HorizontalBarChart
                  data={data.stability.slice(0, 25).map((row) => ({
                    key: row.site_id,
                    label: label(row.site_id),
                    value: row.stability_percentage,
                    tone: stabilityTone(row.stability_percentage),
                  }))}
                  max={100}
                  formatValue={(value) => `${value.toFixed(0)}%`}
                />
              </div>
            </CardContent>
          </Card>

          <Card>
            <CardHeader>
              <CardTitle>Rank reversal risk</CardTitle>
              <CardDescription>
                The pairs of sites whose order is least stable. A pair that swaps
                places under a plausible change of weights should not be read as
                a firm ordering.
              </CardDescription>
            </CardHeader>
            <CardContent className="space-y-2">
              {data.reversals.reversals.length === 0 ? (
                <p className="text-ink-subtle text-xs">
                  No pair of sites changed order under the weight variations tested.
                </p>
              ) : (
                data.reversals.reversals.slice(0, 8).map((pair) => (
                  <div
                    key={`${pair.site_a}-${pair.site_b}`}
                    className="border-line flex flex-wrap items-center justify-between gap-3 rounded-md border px-3 py-2"
                  >
                    <span className="min-w-0 text-xs">
                      <span className="text-ink font-medium">
                        {label(pair.site_a)} and {label(pair.site_b)}
                      </span>
                      <span className="text-ink-subtle ml-2">
                        {' '}
                        ranks {pair.baseline_a_rank} and {pair.baseline_b_rank}
                      </span>
                    </span>
                    <Badge
                      tone={
                        pair.risk === 'high'
                          ? 'danger'
                          : pair.risk === 'moderate'
                            ? 'warning'
                            : 'neutral'
                      }
                    >
                      {(pair.reversal_rate * 100).toFixed(0)}% reversal risk
                    </Badge>
                  </div>
                ))
              )}
            </CardContent>
          </Card>

          <Card>
            <CardHeader>
              <CardTitle>Near-tie groups</CardTitle>
              <CardDescription>
                Sites whose scores are close enough that small changes in the weights
                could reorder them.
              </CardDescription>
            </CardHeader>
            <CardContent className="space-y-2">
              {data.nearTies.filter((cluster) => cluster.site_ids.length >= 2).length === 0 ? (
                <p className="text-ink-subtle text-xs">
                  No near-tie groups were detected in the current ranking.
                </p>
              ) : (
                data.nearTies
                  .filter((cluster) => cluster.site_ids.length >= 2)
                  .map((cluster) => (
                    <div key={cluster.cluster_rank} className="border-line rounded-md border p-3">
                      <p className="text-ink text-xs font-medium">
                        Group starting at rank {cluster.cluster_rank}
                      </p>
                      <p className="text-ink-muted mt-0.5 text-[11px]">
                        {cluster.site_ids.map(label).join(', ')} — score range{' '}
                        {formatScore(cluster.score_range, 4)}
                      </p>
                    </div>
                  ))
              )}
            </CardContent>
          </Card>
        </>
      ) : null}

      <Alert tone="neutral" title="How to read this">
        <span className="flex items-start gap-1.5">
          <Info className="mt-0.5 size-3.5 shrink-0" aria-hidden="true" />
          <span>
            A high sensitivity means the ranking depends heavily on the weights you
            chose rather than on the underlying data. In that case the shortlist should
            be read together with the requirement evaluation, not on its own.
          </span>
        </span>
      </Alert>
    </div>
  )
}
