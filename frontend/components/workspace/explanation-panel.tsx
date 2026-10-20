'use client'

import * as React from 'react'
import { AlertTriangle, CircleCheck, CircleMinus, Info, TrendingDown, TrendingUp } from 'lucide-react'

import { Badge, StatusDot } from '@/components/ui/badge'
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from '@/components/ui/card'
import { ErrorState, LoadingState } from '@/components/ui/feedback'
import { Meter } from '@/components/ui/progress'
import { fetchExplanation } from '@/lib/api'
import { formatScore } from '@/lib/format'
import type { ExplanationResponse, StrengthFactor } from '@/lib/types'

import { useWorkspace } from './workspace-context'

const CHECK_TONE = {
  pass: 'success',
  fail: 'danger',
  warning: 'warning',
  unknown: 'neutral',
  not_applicable: 'neutral',
} as const

function FactorRow({ factor, kind }: { factor: StrengthFactor; kind: 'strength' | 'weakness' }) {
  const Icon = kind === 'strength' ? TrendingUp : TrendingDown
  return (
    <li className="flex items-start justify-between gap-3 py-1.5">
      <span className="flex min-w-0 items-start gap-2">
        <Icon
          className={
            kind === 'strength'
              ? 'text-success mt-0.5 size-3.5 shrink-0'
              : 'text-warning mt-0.5 size-3.5 shrink-0'
          }
          aria-hidden="true"
        />
        <span className="min-w-0">
          <span className="text-ink block text-xs font-medium">{factor.label}</span>
          <span className="text-ink-subtle block text-[11px]">
            {factor.category}
            {factor.reference_value !== null
              ? ` · ${formatScore(factor.focal_value)} vs ${formatScore(
                  factor.reference_value,
                )}`
              : ` · ${formatScore(factor.focal_value)}`}
          </span>
        </span>
      </span>
      <span className="text-ink shrink-0 text-xs font-semibold tabular-nums">
        {formatScore(factor.contribution_delta, 4)}
      </span>
    </li>
  )
}

/**
 * "Why this site?" — the explainability panel.
 *
 * The narrative is assembled by the backend from the deterministic scoring
 * engine and the requirement evaluation. Nothing here is written by a
 * language model.
 */
export function ExplanationPanel() {
  const { selectedSiteId, weights, method, brief } = useWorkspace()

  const [data, setData] = React.useState<ExplanationResponse | null>(null)
  const [loading, setLoading] = React.useState(false)
  const [error, setError] = React.useState<string | null>(null)
  const [retry, setRetry] = React.useState(0)

  React.useEffect(() => {
    if (!selectedSiteId || !weights.category_weights) return
    let cancelled = false
    setLoading(true)
    setError(null)

    fetchExplanation({
      site_id: selectedSiteId,
      level_weights: {
        category_weights: weights.category_weights,
        leaf_weights: weights.leaf_weights ?? null,
      },
      method,
      requirements: brief.confirmedAt ? briefToRequirements(brief) : undefined,
    })
      .then((response) => {
        if (!cancelled) setData(response)
      })
      .catch((err: unknown) => {
        if (!cancelled) {
          setError(
            err instanceof Error ? err.message : 'The explanation could not be generated.',
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
  }, [selectedSiteId, weights, method, brief, retry])

  if (!selectedSiteId) {
    return (
      <Card>
        <CardHeader>
          <CardTitle>Why this site?</CardTitle>
          <CardDescription>Select a site from the shortlist.</CardDescription>
        </CardHeader>
        <CardContent>
          <p className="text-ink-muted text-sm">
            Choose a site in the ranked shortlist or on the map to see the factors
            behind its score.
          </p>
        </CardContent>
      </Card>
    )
  }

  return (
    <Card>
      <CardHeader>
        <div className="flex flex-wrap items-start justify-between gap-3">
          <div>
            <CardTitle>{data?.headline ?? 'Why this site?'}</CardTitle>
            <CardDescription>
              {data?.site_name ?? 'Loading the explanation for the selected site.'}
            </CardDescription>
          </div>
          {data ? (
            <div className="flex items-center gap-3">
              <div className="text-right">
                <p className="text-ink-subtle text-[10px] tracking-[0.08em] uppercase">
                  Base score
                </p>
                <p className="text-ink text-lg font-semibold tabular-nums">
                  {formatScore(data.base_score)}
                </p>
              </div>
              {data.adjusted_score !== null &&
              Math.abs(data.adjusted_score - data.base_score) > 1e-9 ? (
                <div className="text-right">
                  <p className="text-ink-subtle text-[10px] tracking-[0.08em] uppercase">
                    After penalty
                  </p>
                  <p className="text-ink text-lg font-semibold tabular-nums">
                    {formatScore(data.adjusted_score)}
                  </p>
                </div>
              ) : null}
            </div>
          ) : null}
        </div>
      </CardHeader>

      <CardContent className="space-y-5">
        {loading && !data ? <LoadingState label="Computing the explanation." /> : null}

        {error ? (
          <ErrorState
            title="The explanation could not be generated"
            description={error}
            onRetry={() => setRetry((value) => value + 1)}
          />
        ) : null}

        {data ? (
          <>
            <p className="text-ink text-sm leading-relaxed">{data.summary}</p>

            {data.eligible === false ? (
              <div className="border-danger-border bg-danger-subtle rounded-md border px-3 py-2.5">
                <p className="text-danger flex items-center gap-1.5 text-xs font-semibold">
                  <AlertTriangle className="size-3.5" aria-hidden="true" />
                  Excluded by a hard requirement
                </p>
                <ul className="text-ink-muted mt-1 space-y-0.5 text-[11px]">
                  {data.hard_failures.map((failure) => (
                    <li key={failure.key}>
                      {failure.label}: {failure.detail}
                    </li>
                  ))}
                </ul>
              </div>
            ) : null}

            {data.strengths.length > 0 || data.weaknesses.length > 0 ? (
              <div className="grid gap-5 sm:grid-cols-2">
                <div>
                  <h4 className="section-eyebrow mb-1.5">Strongest factors</h4>
                  {data.strengths.length > 0 ? (
                    <ul className="divide-line divide-y">
                      {data.strengths.map((factor) => (
                        <FactorRow key={factor.criterion} factor={factor} kind="strength" />
                      ))}
                    </ul>
                  ) : (
                    <p className="text-ink-subtle text-xs">
                      No criterion stands out positively against the site below.
                    </p>
                  )}
                </div>
                <div>
                  <h4 className="section-eyebrow mb-1.5">Weakest factors</h4>
                  {data.weaknesses.length > 0 ? (
                    <ul className="divide-line divide-y">
                      {data.weaknesses.map((factor) => (
                        <FactorRow key={factor.criterion} factor={factor} kind="weakness" />
                      ))}
                    </ul>
                  ) : (
                    <p className="text-ink-subtle text-xs">
                      No criterion falls behind the site below.
                    </p>
                  )}
                </div>
              </div>
            ) : null}

            <div className="border-line grid gap-4 border-t pt-4 sm:grid-cols-2">
              <div className="space-y-3">
                {data.requirements.business ? (
                  <p className="text-ink-muted text-xs leading-relaxed">
                    <span className="text-ink font-medium">Business requirements: </span>
                    {data.requirements.business}
                  </p>
                ) : null}
                {data.requirements.parking ? (
                  <p className="text-ink-muted text-xs leading-relaxed">
                    <span className="text-ink font-medium">Parking: </span>
                    {data.requirements.parking}
                  </p>
                ) : null}
              </div>
              <div className="space-y-3">
                {data.requirements.facilities ? (
                  <p className="text-ink-muted text-xs leading-relaxed">
                    <span className="text-ink font-medium">Facilities: </span>
                    {data.requirements.facilities}
                  </p>
                ) : null}
                {data.cost ? (
                  <p className="text-ink-muted text-xs leading-relaxed">
                    <span className="text-ink font-medium">Cost: </span>
                    {data.cost}
                  </p>
                ) : null}
              </div>
            </div>

            {data.fit_factor < 1 ? (
              <Meter
                label="Requirement fit factor"
                value={data.fit_factor}
                max={1}
                tone="warning"
                valueLabel={formatScore(data.fit_factor)}
              />
            ) : null}

            {data.caveats.length > 0 ? (
              <div className="border-line bg-surface-muted rounded-md border px-3 py-2.5">
                <h4 className="text-ink-muted flex items-center gap-1.5 text-[11px] font-semibold tracking-[0.06em] uppercase">
                  <Info className="size-3.5" aria-hidden="true" />
                  Caveats
                </h4>
                <ul className="text-ink-muted mt-1.5 space-y-1 text-[11px] leading-relaxed">
                  {data.caveats.map((caveat) => (
                    <li key={caveat} className="flex items-start gap-1.5">
                      <CircleMinus
                        className="text-ink-subtle mt-0.5 size-3 shrink-0"
                        aria-hidden="true"
                      />
                      {caveat}
                    </li>
                  ))}
                </ul>
              </div>
            ) : null}

            <p className="text-ink-subtle flex items-start gap-1.5 text-[11px] leading-relaxed">
              <CircleCheck className="text-success mt-0.5 size-3.5 shrink-0" aria-hidden="true" />
              This explanation is generated from the scoring engine&apos;s own output. It
              does not predict trading performance.
            </p>
          </>
        ) : null}
      </CardContent>
    </Card>
  )
}

/** Convert the stored brief into the requirement payload the API expects. */
function briefToRequirements(brief: {
  acquisitionMode: string
  parking: {
    minCarSpaces: number | null
    minTwoWheelerSpaces: number | null
    minParkingAreaSqft: number | null
    behaviour: string
    scope: string
  }
  facilities: { key: string; label: string; importance: string }[]
  requirements: {
    key: string
    label: string
    importance: string
    value: unknown
    valueType: string
  }[]
  financial: {
    budgets: {
      key: string
      label: string
      limit: number | null
      behaviour: string
      scope: string
    }[]
    budgetBehaviour: string
  }
}): Record<string, unknown> {
  return {
    acquisition_mode: brief.acquisitionMode,
    parking: {
      min_car_spaces: brief.parking.minCarSpaces,
      min_two_wheeler_spaces: brief.parking.minTwoWheelerSpaces,
      min_parking_area_sqft: brief.parking.minParkingAreaSqft,
      behaviour: brief.parking.behaviour,
      scope: brief.parking.scope,
    },
    facilities: brief.facilities,
    business_requirements: brief.requirements.map((requirement) => ({
      key: requirement.key,
      label: requirement.label,
      importance: requirement.importance,
      value: requirement.value,
      value_type: requirement.valueType,
    })),
    financial: {
      acquisition_mode: brief.acquisitionMode,
      budget_behaviour: brief.financial.budgetBehaviour,
      budgets: brief.financial.budgets
        .filter((budget) => budget.limit !== null)
        .map((budget) => ({
          key: budget.key,
          label: budget.label,
          limit: budget.limit,
          behaviour: budget.behaviour,
          scope: budget.scope,
        })),
    },
  }
}
