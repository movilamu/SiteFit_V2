'use client'

import * as React from 'react'
import { ArrowDown, ArrowRight, ArrowUp, Plus, Save } from 'lucide-react'

import { Badge } from '@/components/ui/badge'
import { Button } from '@/components/ui/button'
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from '@/components/ui/card'
import { Alert, EmptyState, ErrorState, LoadingState } from '@/components/ui/feedback'
import { Input } from '@/components/ui/input'
import { Table, TableBody, TableCell, TableHead, TableHeader, TableRow } from '@/components/ui/table'
import { createScenario, fetchScenarios } from '@/lib/api'
import { formatScore } from '@/lib/format'
import { cn } from '@/lib/utils'
import type { Scenario } from '@/lib/types'

import { useWorkspace } from './workspace-context'

type PresetScenario = {
  key: string
  label: string
  description: string
  /** Multipliers applied to the eight category weights. */
  multipliers: Record<string, number>
}

/**
 * Preset scenarios.
 *
 * A preset is a set of multipliers over the category weights, so it
 * composes with whatever the user has already set rather than replacing it.
 */
const PRESETS: PresetScenario[] = [
  {
    key: 'conservative',
    label: 'Conservative',
    description: 'Favours low-risk sites: risk, competition and cost carry more weight.',
    multipliers: {
      risk: 1.8,
      competition: 1.4,
      spending: 0.8,
      population: 0.8,
      cannibalisation: 1.3,
    },
  },
  {
    key: 'growth',
    label: 'Growth',
    description: 'Favours sites in expanding, high-spending catchments.',
    multipliers: {
      spending: 1.8,
      demographics: 1.5,
      population: 1.4,
      risk: 0.7,
    },
  },
  {
    key: 'cost_focused',
    label: 'Cost-focused',
    description: 'Favours cheaper sites and lower ongoing cost.',
    multipliers: {
      site_and_property: 1.9,
      risk: 1.2,
      spending: 0.8,
      demographics: 0.8,
    },
  },
  {
    key: 'accessibility',
    label: 'Accessibility-focused',
    description: 'Favours sites that are easy to reach and serve.',
    multipliers: { accessibility: 2.2, population: 0.7, spending: 0.7 },
  },
  {
    key: 'market_demand',
    label: 'Market-demand-focused',
    description: 'Favours demand: population, demographics and spending power.',
    multipliers: { population: 1.7, demographics: 1.6, spending: 1.6, risk: 0.6 },
  },
]

export function ScenariosPanel() {
  const { weights, setWeights, scores, siteById, rankOf } = useWorkspace()

  const [baseline, setBaseline] = React.useState<Record<string, number>>({})
  const [saved, setSaved] = React.useState<Scenario[]>([])
  const [loadingSaved, setLoadingSaved] = React.useState(true)
  const [savedError, setSavedError] = React.useState<string | null>(null)
  const [name, setName] = React.useState('')
  const [saving, setSaving] = React.useState(false)
  const [message, setMessage] = React.useState<string | null>(null)

  React.useEffect(() => {
    let cancelled = false
    fetchScenarios()
      .then((rows) => {
        if (!cancelled) setSaved(rows)
      })
      .catch((err: unknown) => {
        if (!cancelled) {
          setSavedError(
            err instanceof Error
              ? err.message
              : 'Saved scenarios could not be loaded. The service may require authentication.',
          )
        }
      })
      .finally(() => {
        if (!cancelled) setLoadingSaved(false)
      })
    return () => {
      cancelled = true
    }
  }, [])

  // Capture the ranking before a preset is applied so the change can be
  // described concretely.
  const captureBaseline = React.useCallback(() => {
    const map: Record<string, number> = {}
    for (const row of scores?.sites ?? []) {
      map[String(row.site_id)] = row.rank
    }
    setBaseline(map)
  }, [scores])

  const applyPreset = React.useCallback(
    (preset: PresetScenario) => {
      captureBaseline()
      const current = weights.category_weights ?? {}
      const next: Record<string, number> = {}
      let total = 0
      for (const [key, value] of Object.entries(current)) {
        const scaled = value * (preset.multipliers[key] ?? 1)
        next[key] = scaled
        total += scaled
      }
      if (total <= 0) return
      for (const key of Object.keys(next)) {
        next[key] = next[key] / total
      }
      setWeights({ ...weights, category_weights: next })
      setMessage(
        `${preset.label} applied. The ranking below shows how each site's position changed.`,
      )
    },
    [captureBaseline, setWeights, weights],
  )

  const saveCurrent = React.useCallback(async () => {
    if (!name.trim() || !weights.category_weights) return
    setSaving(true)
    setSavedError(null)
    try {
      const created = await createScenario({
        name: name.trim(),
        weight_set: weights.category_weights,
        aggregation_method: 'weighted_sum',
      })
      setSaved((current) => [created, ...current])
      setName('')
      setMessage(`Scenario "${created.name}" saved.`)
    } catch (err) {
      setSavedError(
        err instanceof Error
          ? err.message
          : 'The scenario could not be saved. The service may require authentication.',
      )
    } finally {
      setSaving(false)
    }
  }, [name, weights.category_weights])

  const changes = React.useMemo(() => {
    if (!scores || Object.keys(baseline).length === 0) return []
    return scores.sites
      .map((row) => {
        const id = String(row.site_id)
        const before = baseline[id]
        if (before === undefined) return null
        const after = row.rank
        return { id, name: siteById[id]?.name || id, before, after, delta: before - after }
      })
      .filter((entry): entry is NonNullable<typeof entry> => entry !== null)
      .filter((entry) => entry.delta !== 0)
      .sort((a, b) => Math.abs(b.delta) - Math.abs(a.delta))
      .slice(0, 12)
  }, [scores, baseline, siteById])

  return (
    <div className="space-y-5">
      <Card>
        <CardHeader>
          <CardTitle>Scenarios</CardTitle>
          <CardDescription>
            Apply a different strategic weighting and see exactly which sites move.
          </CardDescription>
        </CardHeader>
        <CardContent className="space-y-4">
          <div className="grid gap-2 sm:grid-cols-2 lg:grid-cols-3">
            {PRESETS.map((preset) => (
              <button
                key={preset.key}
                type="button"
                onClick={() => applyPreset(preset)}
                className="border-line bg-surface hover:bg-surface-muted focus-visible:ring-ring rounded-lg border p-3 text-left transition-colors focus-visible:ring-2 focus-visible:outline-none"
              >
                <span className="text-ink block text-[13px] font-medium">{preset.label}</span>
                <span className="text-ink-subtle mt-0.5 block text-[11px] leading-relaxed">
                  {preset.description}
                </span>
              </button>
            ))}
          </div>

          {message ? (
            <Alert tone="info" title="Scenario applied">
              {message}
            </Alert>
          ) : null}
        </CardContent>
      </Card>

      <Card>
        <CardHeader>
          <CardTitle>Ranking changes</CardTitle>
          <CardDescription>
            The sites whose position changed most under the current weights, with the
            criteria that drove the change.
          </CardDescription>
        </CardHeader>
        <CardContent className="p-0">
          {changes.length === 0 ? (
            <EmptyState
              title="No ranking changes recorded"
              description="Apply a scenario to compare the resulting ranking with the one you started from."
            />
          ) : (
            <Table>
              <TableHeader>
                <TableRow>
                  <TableHead>Site</TableHead>
                  <TableHead className="w-24 text-right">Was</TableHead>
                  <TableHead className="w-24 text-right">Now</TableHead>
                  <TableHead className="w-32">Change</TableHead>
                </TableRow>
              </TableHeader>
              <TableBody>
                {changes.map((change) => (
                  <TableRow key={change.id}>
                    <TableCell className="text-ink text-xs font-medium">{change.name}</TableCell>
                    <TableCell className="text-right text-xs tabular-nums">{change.before}</TableCell>
                    <TableCell className="text-right text-xs font-semibold tabular-nums">
                      {change.after}
                    </TableCell>
                    <TableCell>
                      {change.delta > 0 ? (
                        <Badge tone="success">
                          <ArrowUp className="size-3" aria-hidden="true" />
                          Up {change.delta}
                        </Badge>
                      ) : (
                        <Badge tone="danger">
                          <ArrowDown className="size-3" aria-hidden="true" />
                          Down {Math.abs(change.delta)}
                        </Badge>
                      )}
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
          <CardTitle>Saved scenarios</CardTitle>
          <CardDescription>
            Scenarios are stored against your account so a weighting can be reused
            across analyses.
          </CardDescription>
        </CardHeader>
        <CardContent className="space-y-4">
          <div className="flex flex-wrap items-end gap-2">
            <div className="min-w-[220px] flex-1">
              <label
                htmlFor="scenario-name"
                className="text-ink-muted mb-1.5 block text-[11px] font-medium"
              >
                Save the current weights as
              </label>
              <Input
                id="scenario-name"
                value={name}
                onChange={(event) => setName(event.target.value)}
                placeholder="e.g. FY26 expansion plan"
                maxLength={120}
              />
            </div>
            <Button
              type="button"
              onClick={saveCurrent}
              disabled={saving || !name.trim() || !weights.category_weights}
            >
              {saving ? <Save className="animate-pulse" /> : <Save />}
              Save scenario
            </Button>
          </div>

          {savedError ? (
            <ErrorState title="Saved scenarios are unavailable" description={savedError} />
          ) : loadingSaved ? (
            <LoadingState label="Loading saved scenarios…" />
          ) : saved.length === 0 ? (
            <p className="text-ink-subtle text-xs">
              No scenarios have been saved yet.
            </p>
          ) : (
            <ul className="border-line divide-line divide-y rounded-md border">
              {saved.map((scenario) => (
                <li key={scenario.scenario_id} className="flex items-center justify-between gap-3 px-3 py-2">
                  <span className="min-w-0">
                    <span className="text-ink block text-xs font-medium">{scenario.name}</span>
                    <span className="text-ink-subtle block text-[11px]">
                      {scenario.aggregation_method.replace(/_/g, ' ')} ·{' '}
                      {Object.keys(scenario.weight_set).length} criteria
                    </span>
                  </span>
                  <Button
                    type="button"
                    size="xs"
                    variant="outline"
                    onClick={() => {
                      setWeights({
                        ...weights,
                        category_weights: scenario.weight_set,
                      })
                      setMessage(`Scenario "${scenario.name}" applied.`)
                    }}
                  >
                    <ArrowRight />
                    Apply
                  </Button>
                </li>
              ))}
            </ul>
          )}

          <p className="text-ink-subtle flex items-start gap-1.5 text-[11px] leading-relaxed">
            <Plus className="mt-0.5 size-3 shrink-0" aria-hidden="true" />
            Saved scenarios require an authenticated session. When the scenario service is
            not configured, the analysis still works and the presets above remain
            available.
          </p>
        </CardContent>
      </Card>
    </div>
  )
}
