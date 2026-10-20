'use client'

import * as React from 'react'
import { Scale, Target, Layers, TrendingUp, ShieldCheck } from 'lucide-react'

import { Card, CardContent, CardDescription, CardHeader, CardTitle } from '@/components/ui/card'
import { fetchCriteria } from '@/lib/api'
import type { CriteriaTree } from '@/lib/types'

const METHOD_STEPS = [
  {
    title: 'Filter on hard requirements',
    body: 'Any requirement the user marked as a hard requirement removes a site that fails it. Filtering happens before scoring so that non-viable sites cannot skew the comparison.',
  },
  {
    title: 'Normalise each criterion',
    body: 'Raw values are clipped to the 5th and 95th percentile of the observed candidate set, then rescaled to 0–1. Cost-oriented criteria are inverted so that lower values score higher. A target-band criterion scores highest inside its ideal range and falls off linearly on either side.',
  },
  {
    title: 'Roll the weights down the hierarchy',
    body: 'Weights are set over the eight criteria categories and optionally refined within a category. The global weight of a leaf criterion is the product of the level weights along its path. The roll-up is performed by the server so the interface and the ranking use identical arithmetic.',
  },
  {
    title: 'Aggregate and rank',
    body: 'The normalised values are aggregated using the selected method and the sites are ranked. The weighted sum is fully compensatory; the weighted product penalises a single weak criterion more sharply; the distance-to-ideal method scores each site against the best and worst observed value.',
  },
  {
    title: 'Apply the requirement penalty',
    body: 'A site that misses a preferred requirement keeps its place in the shortlist but has its score reduced by a disclosed, bounded factor. A site that meets every requirement is not penalised. A flexible requirement is reported as a warning and never reduces the score.',
  },
  {
    title: 'Stress-test the result',
    body: 'The ranking is re-tested with perturbed weights, with alternative aggregation methods and for near-ties, so that a decision maker can see how much of the result depends on their own weighting choices.',
  },
]

const METHODS = [
  {
    name: 'Weighted sum (SAW)',
    body: 'S = Σ wⱼ xⱼ. Fully compensatory: a strong criterion can offset a weak one. This is the default because it is the easiest to explain to a business audience.',
  },
  {
    name: 'Weighted product (WPM)',
    body: 'S = Π xⱼ^wⱼ. Partially compensatory: a near-zero criterion drags down the whole product, so a site with one fatal weakness cannot be rescued by strengths elsewhere.',
  },
  {
    name: 'Distance to ideal (TOPSIS)',
    body: 'Each site is scored on its weighted distance to the best and worst observed value for every criterion, and reported as relative closeness to the ideal.',
  },
]

export default function MethodologyPage() {
  const [tree, setTree] = React.useState<CriteriaTree | null>(null)

  React.useEffect(() => {
    let cancelled = false
    fetchCriteria()
      .then((response) => {
        if (!cancelled) setTree(response)
      })
      .catch(() => {
        if (!cancelled) setTree(null)
      })
    return () => {
      cancelled = true
    }
  }, [])

  return (
    <div className="mx-auto w-full max-w-[1100px] px-4 py-6 lg:px-8 lg:py-8">
      <header className="mb-6">
        <p className="section-eyebrow">Reference</p>
        <h1 className="mt-1.5 text-2xl font-semibold tracking-tight text-ink">Methodology</h1>
        <p className="text-ink-muted mt-1.5 max-w-3xl text-sm leading-relaxed">
          How the platform turns a set of stated requirements and weights into a ranked
          shortlist. Every step is deterministic and reproducible from the weights and
          requirements alone.
        </p>
      </header>

      <div className="space-y-5">
        <Card>
          <CardHeader>
            <CardTitle className="flex items-center gap-2">
              <Scale className="text-primary size-4" aria-hidden="true" />
              The analytical pipeline
            </CardTitle>
            <CardDescription>
              Applied identically to every analysis, in this order.
            </CardDescription>
          </CardHeader>
          <CardContent className="space-y-4">
            <ol className="space-y-3">
              {METHOD_STEPS.map((step, index) => (
                <li key={step.title} className="flex gap-3">
                  <span
                    className="bg-info-subtle text-info flex size-6 shrink-0 items-center justify-center rounded-full text-[11px] font-semibold"
                    aria-hidden="true"
                  >
                    {index + 1}
                  </span>
                  <div className="min-w-0">
                    <p className="text-ink text-[13px] font-medium">{step.title}</p>
                    <p className="text-ink-muted mt-0.5 text-xs leading-relaxed">{step.body}</p>
                  </div>
                </li>
              ))}
            </ol>
          </CardContent>
        </Card>

        <Card>
          <CardHeader>
            <CardTitle className="flex items-center gap-2">
              <TrendingUp className="text-primary size-4" aria-hidden="true" />
              Aggregation methods
            </CardTitle>
            <CardDescription>
              The same normalised values can be aggregated three ways. The agreement
              between them is reported as part of the sensitivity analysis.
            </CardDescription>
          </CardHeader>
          <CardContent className="grid gap-4 sm:grid-cols-3">
            {METHODS.map((method) => (
              <div key={method.name} className="border-line rounded-md border p-3">
                <p className="text-ink text-[13px] font-medium">{method.name}</p>
                <p className="text-ink-muted mt-1 text-[11px] leading-relaxed">{method.body}</p>
              </div>
            ))}
          </CardContent>
        </Card>

        <Card>
          <CardHeader>
            <CardTitle className="flex items-center gap-2">
              <Target className="text-primary size-4" aria-hidden="true" />
              Constraint behaviour
            </CardTitle>
            <CardDescription>
              How the platform treats a requirement the user has not met.
            </CardDescription>
          </CardHeader>
          <CardContent className="grid gap-4 sm:grid-cols-3">
            {[
              {
                title: 'Hard requirement',
                body: 'The site is excluded from the shortlist and the reason is recorded against it. Nothing else about the site is evaluated.',
                tone: 'border-danger-border bg-danger-subtle text-danger',
              },
              {
                title: 'Preference',
                body: 'The site is kept. Its requirement fit ratio is reduced, which lowers the final score through a disclosed, bounded penalty of at most 25 %.',
                tone: 'border-warning-border bg-warning-subtle text-warning',
              },
              {
                title: 'Flexible',
                body: 'The site is kept and the shortfall is shown as a warning. The score is never reduced on the basis of a flexible requirement.',
                tone: 'border-info-border bg-info-subtle text-info',
              },
            ].map((item) => (
              <div key={item.title} className={`rounded-md border p-3 ${item.tone}`}>
                <p className="text-[13px] font-semibold">{item.title}</p>
                <p className="text-ink-muted mt-1 text-[11px] leading-relaxed">{item.body}</p>
              </div>
            ))}
          </CardContent>
        </Card>

        <Card>
          <CardHeader>
            <CardTitle className="flex items-center gap-2">
              <Layers className="text-primary size-4" aria-hidden="true" />
              The criteria hierarchy
            </CardTitle>
            <CardDescription>
              {tree
                ? `${tree.leaf_count} leaf criteria across ${tree.category_keys.length} categories, of which ${tree.scorable_leaf_count} can be scored in the current data release.`
                : 'Loading the criteria hierarchy…'}
            </CardDescription>
          </CardHeader>
          <CardContent>
            {tree ? (
              <div className="space-y-3">
                {tree.categories.map((category) => (
                  <div key={category.key} className="border-line rounded-md border">
                    <p className="text-ink bg-surface-muted border-line border-b px-3 py-2 text-[13px] font-semibold">
                      {category.label}
                    </p>
                    <ul className="divide-line divide-y">
                      {category.subcategories.flatMap((subcategory) =>
                        subcategory.criteria.map((criterion) => (
                          <li
                            key={criterion.key}
                            className="flex flex-wrap items-center justify-between gap-3 px-3 py-2"
                          >
                            <span className="min-w-0">
                              <span className="text-ink-muted block text-xs">
                                {criterion.label}
                              </span>
                              {criterion.notes ? (
                                <span className="text-ink-subtle block text-[11px] leading-snug">
                                  {criterion.notes}
                                </span>
                              ) : null}
                            </span>
                            <span className="flex shrink-0 items-center gap-2">
                              <span className="text-ink-subtle text-[10px] tracking-[0.06em] uppercase">
                                {criterion.scoring_mode === 'target_band'
                                  ? `Target band ${criterion.target_band?.join('–')}`
                                  : (criterion.direction ?? '—')}
                              </span>
                              <span
                                className={
                                  criterion.data_available
                                    ? 'text-success text-[11px] font-medium'
                                    : 'text-warning text-[11px] font-medium'
                                }
                              >
                                {criterion.data_available ? 'Scored' : 'No data'}
                              </span>
                            </span>
                          </li>
                        )),
                      )}
                    </ul>
                  </div>
                ))}
              </div>
            ) : (
              <p className="text-ink-subtle text-xs">
                The criteria hierarchy could not be loaded.
              </p>
            )}
          </CardContent>
        </Card>

        <Card>
          <CardHeader>
            <CardTitle className="flex items-center gap-2">
              <ShieldCheck className="text-primary size-4" aria-hidden="true" />
              What the platform does not do
            </CardTitle>
          </CardHeader>
          <CardContent className="space-y-2">
            {[
              'It does not predict trading performance. A score expresses relative fit against a stated set of weights and requirements.',
              'It does not replace site visits, commercial due diligence or local market knowledge.',
              'It does not estimate a cost that has not been published. Unavailable figures are reported as unavailable.',
              'It does not apply a requirement the user has not confirmed.',
              'It does not use a language model to produce a score, a cost or a property fact.',
            ].map((item) => (
              <p key={item} className="text-ink-muted flex items-start gap-2 text-xs leading-relaxed">
                <span className="bg-ink-subtle mt-1.5 size-1 shrink-0 rounded-full" aria-hidden="true" />
                {item}
              </p>
            ))}
          </CardContent>
        </Card>
      </div>
    </div>
  )
}
