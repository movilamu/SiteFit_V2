'use client'

import * as React from 'react'
import { ExternalLink, Info, MapPin, RefreshCw, Search } from 'lucide-react'

import { Badge, StatusDot } from '@/components/ui/badge'
import { Button } from '@/components/ui/button'
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from '@/components/ui/card'
import { Alert, EmptyState, ErrorState, LoadingState } from '@/components/ui/feedback'
import { Input } from '@/components/ui/input'
import { fetchPropertySearch, fetchPropertySources } from '@/lib/api'
import { formatDistance, formatMoney, formatNumber } from '@/lib/format'
import type { PropertySearchResponse, PropertySourcesResponse } from '@/lib/types'

import { useWorkspace } from './workspace-context'

const STATUS_TONE: Record<string, 'success' | 'info' | 'warning' | 'danger' | 'neutral'> = {
  ok: 'success',
  partial: 'warning',
  unavailable: 'danger',
  no_results: 'neutral',
  timeout: 'warning',
  rate_limited: 'warning',
  error: 'danger',
  not_configured: 'neutral',
  disabled: 'neutral',
}

const STATUS_LABEL: Record<string, string> = {
  ok: 'Available',
  partial: 'Partially available',
  unavailable: 'Unavailable',
  no_results: 'No results',
  timeout: 'Timed out',
  rate_limited: 'Rate limited',
  error: 'Error',
  not_configured: 'Not configured',
  disabled: 'Disabled',
}

/**
 * Property and brokerage intelligence.
 *
 * Opportunities come from live retrievals against public or
 * operator-configured sources.  When a source is unavailable the panel says
 * so explicitly instead of showing an empty list that could be mistaken for
 * "nothing is available".
 */
export function PropertyPanel() {
  const { sites, scores, brief } = useWorkspace()

  const [sources, setSources] = React.useState<PropertySourcesResponse | null>(null)
  const [result, setResult] = React.useState<PropertySearchResponse | null>(null)
  const [loading, setLoading] = React.useState(false)
  const [error, setError] = React.useState<string | null>(null)
  const [radius, setRadius] = React.useState(1500)

  const topSiteIds = React.useMemo(() => {
    const ranked = (scores?.sites ?? []).slice(0, 3).map((row) => String(row.site_id))
    if (ranked.length > 0) return ranked
    return sites.slice(0, 3).map((site) => String(site.site_id))
  }, [scores, sites])

  /**
   * The keys of the sources that cannot be queried automatically.
   *
   * A manual source reports the same `unavailable` status as a source
   * that failed, so the kind of the source is what tells the two apart.
   */
  const manualSourceKeys = React.useMemo(() => {
    const keys = new Set<string>()
    for (const source of sources?.sources ?? []) {
      if (source.kind === 'manual') keys.add(source.key)
    }
    return keys
  }, [sources])

  React.useEffect(() => {
    let cancelled = false
    fetchPropertySources()
      .then((response) => {
        if (!cancelled) setSources(response)
      })
      .catch(() => {
        if (!cancelled) setSources(null)
      })
    return () => {
      cancelled = true
    }
  }, [])

  const runSearch = React.useCallback(async () => {
    if (topSiteIds.length === 0) return
    setLoading(true)
    setError(null)
    try {
      const response = await fetchPropertySearch({
        site_ids: topSiteIds,
        radius_m: radius,
        business_type: brief.businessType || null,
        acquisition_mode: brief.acquisitionMode,
        limit_per_site: 10,
      })
      setResult(response)
    } catch (err) {
      setError(
        err instanceof Error ? err.message : 'The property search could not be completed.',
      )
    } finally {
      setLoading(false)
    }
  }, [topSiteIds, radius, brief.businessType, brief.acquisitionMode])

  React.useEffect(() => {
    if (topSiteIds.length === 0) return
    void runSearch()
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [topSiteIds.join(',')])

  return (
    <div className="space-y-5">
      <Card>
        <CardHeader>
          <div className="flex flex-wrap items-start justify-between gap-3">
            <div>
              <CardTitle>Property & brokerage intelligence</CardTitle>
              <CardDescription>
                Searches the configured public sources around your top three ranked
                locations.
              </CardDescription>
            </div>
            <Button
              type="button"
              variant="outline"
              size="sm"
              onClick={runSearch}
              disabled={loading || topSiteIds.length === 0}
            >
              {loading ? <RefreshCw className="animate-spin" /> : <Search />}
              {loading ? 'Searching…' : 'Search again'}
            </Button>
          </div>
        </CardHeader>

        <CardContent className="space-y-4">
          <div className="flex flex-wrap items-end gap-4">
            <div className="w-full sm:w-64">
              <label
                htmlFor="property-radius"
                className="text-ink-muted mb-1.5 block text-[11px] font-medium"
              >
                Search radius: {formatNumber(radius)} m
              </label>
              <Input
                id="property-radius"
                type="range"
                min={200}
                max={5000}
                step={100}
                value={radius}
                onChange={(event) => setRadius(Number(event.target.value))}
                className="h-9 p-0"
              />
            </div>
            <p className="text-ink-subtle text-[11px]">
              Searching around {topSiteIds.length} recommended location
              {topSiteIds.length === 1 ? '' : 's'}.
            </p>
          </div>

          {sources ? (
            <div className="border-line bg-surface-muted rounded-md border p-3">
              <h4 className="section-eyebrow mb-2">Sources</h4>
              <ul className="space-y-1.5">
                {sources.sources.map((source) => {
                  const manual = source.kind === 'manual'
                  const tone = manual ? 'info' : source.enabled ? 'success' : 'neutral'
                  return (
                    <li key={source.key} className="flex items-start justify-between gap-3">
                      <span className="min-w-0">
                        <span className="text-ink block text-xs font-medium">{source.label}</span>
                        <span className="text-ink-subtle block text-[11px] leading-snug">
                          {source.description}
                        </span>
                        {manual ? (
                          <span className="text-ink-subtle mt-0.5 block text-[11px] leading-snug">
                            Listings on this source are not retrieved automatically.
                          </span>
                        ) : null}
                        {manual && source.homepage_url ? (
                          <a
                            href={source.homepage_url}
                            target="_blank"
                            rel="noopener noreferrer"
                            className="text-info mt-1 inline-flex items-center gap-1 text-[11px] font-medium hover:underline"
                          >
                            Search this source
                            <ExternalLink className="size-3" aria-hidden="true" />
                          </a>
                        ) : null}
                      </span>
                      <Badge tone={tone}>
                        <StatusDot tone={tone} />
                        {manual ? 'Manual' : source.enabled ? 'Enabled' : 'Not configured'}
                      </Badge>
                    </li>
                  )
                })}
              </ul>
              {sources.notes.length > 0 ? (
                <ul className="text-ink-subtle mt-2.5 space-y-1 text-[11px] leading-relaxed">
                  {sources.notes.map((note) => (
                    <li key={note}>{note}</li>
                  ))}
                </ul>
              ) : null}
            </div>
          ) : null}
        </CardContent>
      </Card>

      {error ? (
        <ErrorState
          title="The property search could not be completed"
          description={error}
          onRetry={runSearch}
        />
      ) : null}

      {loading && !result ? <LoadingState label="Searching external sources…" /> : null}

      {result ? (
        result.sites.map((entry) => (
          <Card key={entry.site_id}>
            <CardHeader>
              <div className="flex flex-wrap items-start justify-between gap-3">
                <div>
                  <CardTitle>{entry.site_name || `Site ${entry.site_id}`}</CardTitle>
                  <CardDescription>{entry.message}</CardDescription>
                </div>
                <Badge tone={STATUS_TONE[entry.status] ?? 'neutral'}>
                  <StatusDot tone={STATUS_TONE[entry.status] ?? 'neutral'} />
                  {STATUS_LABEL[entry.status] ?? entry.status}
                </Badge>
              </div>
            </CardHeader>
            <CardContent className="space-y-3">
              {entry.sources.length > 0 ? (
                <div className="flex flex-wrap gap-2">
                  {entry.sources.map((source) => {
                    const manual =
                      manualSourceKeys.has(source.key) || Boolean(source.search_url)
                    const tone = manual
                      ? 'info'
                      : (STATUS_TONE[source.status] ?? 'neutral')
                    const statusLabel = manual
                      ? 'Search manually'
                      : (STATUS_LABEL[source.status] ?? source.status)
                    return (
                      <Badge key={source.key} tone={tone} title={source.message}>
                        <StatusDot tone={tone} />
                        {source.label}: {statusLabel}
                      </Badge>
                    )
                  })}
                </div>
              ) : null}

              {entry.sources
                .filter(
                  (source) =>
                    (manualSourceKeys.has(source.key) || Boolean(source.search_url)) &&
                    source.search_url,
                )
                .map((source) => (
                  <div
                    key={`manual-${source.key}`}
                    className="border-info-border bg-info-subtle rounded-md border p-3"
                  >
                    <div className="flex flex-wrap items-start justify-between gap-3">
                      <div className="min-w-0">
                        <p className="text-info text-[13px] font-medium">{source.label}</p>
                        <p className="text-ink-muted mt-0.5 text-[11px] leading-relaxed">
                          This source is not queried automatically. The result was not
                          retrieved by this platform, so nothing is shown for it here.
                        </p>
                      </div>
                      <a
                        href={source.search_url ?? undefined}
                        target="_blank"
                        rel="noopener noreferrer"
                        className="text-info inline-flex shrink-0 items-center gap-1 text-[11px] font-medium hover:underline"
                      >
                        Search this source
                        <ExternalLink className="size-3" aria-hidden="true" />
                      </a>
                    </div>
                    {source.message ? (
                      <p className="text-ink-subtle mt-1.5 text-[11px] leading-relaxed">
                        {source.message}
                      </p>
                    ) : null}
                  </div>
                ))}

              {entry.opportunities.length === 0 ? (
                <EmptyState
                  icon={MapPin}
                  title="No opportunities returned"
                  description="No source returned a usable result for this location. This does not mean that nothing is available."
                />
              ) : (
                <ul className="space-y-3">
                  {entry.opportunities.map((opportunity) => (
                    <li
                      key={`${opportunity.source_key}-${opportunity.title}-${opportunity.source_url ?? ''}`}
                      className="border-line rounded-md border p-3"
                    >
                      <div className="flex flex-wrap items-start justify-between gap-3">
                        <div className="min-w-0">
                          <p className="text-ink text-[13px] font-medium">
                            {opportunity.title}
                          </p>
                          <p className="text-ink-subtle mt-0.5 text-[11px]">
                            {opportunity.location || 'Location not stated'}
                            {opportunity.distance_m !== null
                              ? ` · ${formatDistance(opportunity.distance_m)} away`
                              : ''}
                          </p>
                        </div>
                        {opportunity.source_url ? (
                          <a
                            href={opportunity.source_url}
                            target="_blank"
                            rel="noopener noreferrer nofollow"
                            className="text-info inline-flex shrink-0 items-center gap-1 text-[11px] font-medium hover:underline"
                          >
                            View original listing
                            <ExternalLink className="size-3" aria-hidden="true" />
                          </a>
                        ) : null}
                      </div>

                      <dl className="text-ink-muted mt-2.5 grid grid-cols-2 gap-x-4 gap-y-1.5 text-[11px] sm:grid-cols-4">
                        <div>
                          <dt className="text-ink-subtle">Type</dt>
                          <dd>{opportunity.property_type || 'Not stated'}</dd>
                        </div>
                        <div>
                          <dt className="text-ink-subtle">Area</dt>
                          <dd>
                            {opportunity.area_sqft === null
                              ? 'Not stated'
                              : `${formatNumber(opportunity.area_sqft)} sq ft`}
                          </dd>
                        </div>
                        <div>
                          <dt className="text-ink-subtle">Price</dt>
                          <dd>
                            {opportunity.purchase_price !== null
                              ? formatMoney(opportunity.purchase_price)
                              : opportunity.monthly_rent !== null
                                ? `${formatMoney(opportunity.monthly_rent)} / month`
                                : 'Not published'}
                          </dd>
                        </div>
                        <div>
                          <dt className="text-ink-subtle">Broker</dt>
                          <dd>{opportunity.broker_name || 'Not stated'}</dd>
                        </div>
                      </dl>

                      <div className="mt-2.5 flex flex-wrap items-center gap-2">
                        <Badge tone="outline">Source: {opportunity.source_label}</Badge>
                        {opportunity.price_provenance === 'unavailable' ? (
                          <Badge tone="warning">
                            <StatusDot tone="warning" />
                            Price not published
                          </Badge>
                        ) : (
                          <Badge tone="success">
                            <StatusDot tone="success" />
                            Listed price
                          </Badge>
                        )}
                        {opportunity.broker_contact ? (
                          <span className="text-ink-muted text-[11px]">
                            Contact: {opportunity.broker_contact}
                          </span>
                        ) : null}
                      </div>
                    </li>
                  ))}
                </ul>
              )}
            </CardContent>
          </Card>
        ))
      ) : null}

      {result ? (
        <Alert tone="warning" title="Before you rely on these listings">
          {result.disclaimer}
        </Alert>
      ) : null}

      {!loading && !result && !error ? (
        <Card>
          <CardContent className="p-0">
            <EmptyState
              icon={Info}
              title="No search has been run"
              description="Choose a search radius and run the search to look for property and brokerage opportunities around your recommended locations."
              action={
                <Button type="button" onClick={runSearch}>
                  <Search />
                  Run the search
                </Button>
              }
            />
          </CardContent>
        </Card>
      ) : null}
    </div>
  )
}
