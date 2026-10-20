'use client'

import * as React from 'react'
import { ExternalLink, Info, MapPin, RefreshCw, Search } from 'lucide-react'

import { Badge, StatusDot } from '@/components/ui/badge'
import { Button } from '@/components/ui/button'
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from '@/components/ui/card'
import { Alert, EmptyState, ErrorState, LoadingState } from '@/components/ui/feedback'
import { fetchBrokerageSearch, fetchBrokerageSources } from '@/lib/api'
import { formatDateTime, formatDistance, formatNumber } from '@/lib/format'
import type {
  BrokerageOpportunity,
  BrokerageSearchResponse,
  BrokerageSourceStatus,
  BrokerageSourcesResponse,
} from '@/lib/types'

import { useWorkspace } from './workspace-context'

/**
 * The source status vocabulary used by the brokerage sources.
 *
 * A manual source reports the same `unavailable` status as a failed
 * automated source, so the status alone cannot be used to tell the two
 * apart; the kind of the source is what distinguishes them.
 */
const SOURCE_STATUS_TONE: Record<
  string,
  'success' | 'info' | 'warning' | 'danger' | 'neutral'
> = {
  live_source: 'success',
  recently_retrieved: 'info',
  source_date_available: 'info',
  source_date_unknown: 'neutral',
  unavailable: 'danger',
}

const SITE_STATUS_TONE: Record<string, 'success' | 'warning' | 'danger' | 'neutral'> = {
  ok: 'success',
  partial: 'warning',
  unavailable: 'danger',
}

const SITE_STATUS_LABEL: Record<string, string> = {
  ok: 'Available',
  partial: 'Partially available',
  unavailable: 'Unavailable',
}

/** A source is manual when it says so, or when it offers a direct search link. */
function isManualSource(source: { kind?: string; search_url?: string | null }): boolean {
  return source.kind === 'manual' || Boolean(source.search_url)
}

function OpportunityCard({ opportunity }: { opportunity: BrokerageOpportunity }) {
  const tone = SOURCE_STATUS_TONE[opportunity.source_status] ?? 'neutral'
  const statusLabel = opportunity.source_status_label || opportunity.source_status

  return (
    <li className="border-line rounded-md border p-3">
      <div className="flex flex-wrap items-start justify-between gap-3">
        <div className="min-w-0">
          <p className="text-ink text-[13px] font-medium">{opportunity.name}</p>
          <p className="text-ink-subtle mt-0.5 text-[11px]">
            {opportunity.service_area || 'Service area not stated'}
            {opportunity.distance_m !== null
              ? ` · ${formatDistance(opportunity.distance_m)} away`
              : ''}
          </p>
        </div>
        {opportunity.source_url ? (
          <a
            href={opportunity.source_url}
            target="_blank"
            rel="noopener noreferrer"
            className="text-info inline-flex shrink-0 items-center gap-1 text-[11px] font-medium hover:underline"
          >
            View source
            <ExternalLink className="size-3" aria-hidden="true" />
          </a>
        ) : null}
      </div>

      <dl className="text-ink-muted mt-2.5 flex flex-wrap gap-x-6 gap-y-1.5 text-[11px]">
        <div>
          <dt className="text-ink-subtle">Website</dt>
          <dd>
            {opportunity.website ? (
              <a
                href={opportunity.website}
                target="_blank"
                rel="noopener noreferrer"
                className="text-info hover:underline"
              >
                {opportunity.website}
              </a>
            ) : (
              'Not published'
            )}
          </dd>
        </div>
        {opportunity.phone ? (
          <div>
            <dt className="text-ink-subtle">Phone</dt>
            <dd>{opportunity.phone}</dd>
          </div>
        ) : null}
        {opportunity.email ? (
          <div>
            <dt className="text-ink-subtle">Email</dt>
            <dd>{opportunity.email}</dd>
          </div>
        ) : null}
        <div>
          <dt className="text-ink-subtle">Retrieved</dt>
          <dd>{formatDateTime(opportunity.retrieved_at)}</dd>
        </div>
      </dl>

      <div className="mt-2.5 flex flex-wrap items-center gap-2">
        <Badge tone="outline">Source: {opportunity.source_label}</Badge>
        <Badge tone={tone}>
          <StatusDot tone={tone} />
          {statusLabel}
        </Badge>
        {opportunity.listing_count > 0 ? (
          <span className="text-ink-muted text-[11px]">
            {formatNumber(opportunity.listing_count)} listing
            {opportunity.listing_count === 1 ? '' : 's'}
          </span>
        ) : null}
      </div>

      {opportunity.notes ? (
        <p className="text-ink-subtle mt-1.5 text-[11px] leading-relaxed">{opportunity.notes}</p>
      ) : null}
    </li>
  )
}

function SourceBlock({ source }: { source: BrokerageSourceStatus }) {
  const tone = SOURCE_STATUS_TONE[source.status] ?? 'neutral'
  const statusLabel = source.status_label || source.status
  const opportunities = source.opportunities ?? []

  return (
    <div className="border-line rounded-md border p-3">
      <div className="flex flex-wrap items-start justify-between gap-2">
        <p className="text-ink text-[13px] font-medium">{source.source_label}</p>
        <Badge tone={tone}>
          <StatusDot tone={tone} />
          {statusLabel}
        </Badge>
      </div>

      {source.publisher ? (
        <p className="text-ink-subtle mt-0.5 text-[11px]">Published by {source.publisher}</p>
      ) : null}

      {source.message ? (
        <p className="text-ink-muted mt-1.5 text-[11px] leading-relaxed">{source.message}</p>
      ) : null}

      {opportunities.length > 0 ? (
        <ul className="mt-2.5 space-y-2">
          {opportunities.map((opportunity) => (
            <OpportunityCard
              key={`${opportunity.source_key}-${opportunity.name}-${opportunity.source_url}`}
              opportunity={opportunity}
            />
          ))}
        </ul>
      ) : null}
    </div>
  )
}

/**
 * Brokerage intelligence for the recommended sites.
 *
 * Automated sources are queried live and their results are reported as
 * they are.  A source that cannot be queried automatically is reported as
 * a manual source with a direct search link, and is never presented as
 * though it had returned a listing.  No agency, contact detail or listing
 * is ever invented.
 */
export function BrokeragePanel() {
  const { scores, sites } = useWorkspace()

  const [sources, setSources] = React.useState<BrokerageSourcesResponse | null>(null)
  const [sourcesError, setSourcesError] = React.useState<string | null>(null)
  const [result, setResult] = React.useState<BrokerageSearchResponse | null>(null)
  const [loading, setLoading] = React.useState(false)
  const [error, setError] = React.useState<string | null>(null)

  const siteKey = React.useMemo(() => {
    const ranked = (scores?.sites ?? []).slice(0, 3).map((row) => String(row.site_id))
    const ids =
      ranked.length > 0
        ? ranked
        : sites.slice(0, 3).map((site) => String(site.site_id))
    return ids.join(',')
  }, [scores, sites])

  React.useEffect(() => {
    let cancelled = false
    fetchBrokerageSources()
      .then((response) => {
        if (cancelled) return
        setSources(response)
      })
      .catch((err: unknown) => {
        if (cancelled) return
        setSourcesError(
          err instanceof Error
            ? err.message
            : 'The configured brokerage sources could not be loaded.',
        )
      })
    return () => {
      cancelled = true
    }
  }, [])

  const runSearch = React.useCallback(async () => {
    const siteIds = siteKey.split(',').filter(Boolean)
    if (siteIds.length === 0) return
    setLoading(true)
    setError(null)
    try {
      const response = await fetchBrokerageSearch({
        site_ids: siteIds,
        radius_m: 5000,
        limit_per_site: 10,
      })
      setResult(response)
    } catch (err) {
      setError(
        err instanceof Error
          ? err.message
          : 'The brokerage search could not be completed.',
      )
    } finally {
      setLoading(false)
    }
  }, [siteKey])

  React.useEffect(() => {
    void runSearch()
  }, [runSearch])

  const manualSourceKeys = React.useMemo(() => {
    const keys = new Set<string>()
    for (const source of sources?.sources ?? []) {
      if (source.kind === 'manual') keys.add(source.key)
    }
    return keys
  }, [sources])

  const totalOpportunities = result?.opportunity_count ?? 0

  return (
    <div className="space-y-5">
      <Card>
        <CardHeader>
          <div className="flex flex-wrap items-start justify-between gap-3">
            <div>
              <CardTitle>Brokerage intelligence</CardTitle>
              <CardDescription>
                Searches the configured brokerage sources around your top recommended
                locations.
              </CardDescription>
            </div>
            <Button
              type="button"
              variant="outline"
              size="sm"
              onClick={() => void runSearch()}
              disabled={loading || !siteKey}
            >
              {loading ? <RefreshCw className="animate-spin" /> : <Search />}
              {loading ? 'Searching…' : 'Search again'}
            </Button>
          </div>
        </CardHeader>

        <CardContent className="space-y-4">
          {sources ? (
            <div className="border-line bg-surface-muted rounded-md border p-3">
              <h4 className="section-eyebrow mb-2">Sources</h4>
              <ul className="space-y-2">
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

          {sourcesError ? (
            <ErrorState
              title="The brokerage sources could not be loaded"
              description={sourcesError}
            />
          ) : null}
        </CardContent>
      </Card>

      {error ? (
        <ErrorState
          title="The brokerage search could not be completed"
          description={error}
          onRetry={() => void runSearch()}
        />
      ) : null}

      {loading && !result ? <LoadingState label="Searching the brokerage sources…" /> : null}

      {result && result.sites.length === 0 ? (
        <Card>
          <CardContent className="p-0">
            <EmptyState
              icon={MapPin}
              title="No site was searched"
              description="None of the recommended locations could be located in the candidate inventory, so no brokerage search was performed."
            />
          </CardContent>
        </Card>
      ) : null}

      {result
        ? result.sites.map((entry) => {
            const manualSources = entry.sources.filter(
              (source) =>
                manualSourceKeys.has(source.source_key) || isManualSource(source),
            )
            const automatedSources = entry.sources.filter(
              (source) =>
                !manualSourceKeys.has(source.source_key) && !isManualSource(source),
            )

            /**
             * The opportunities that no source reported.
             *
             * The per-source lists are the primary presentation, but a
             * result that reached the site without a source is still shown
             * rather than dropped.
             */
            const unattributed = entry.opportunities.filter((opportunity) => {
              const key = `${opportunity.source_key}|${opportunity.name}|${opportunity.source_url}`
              return !entry.sources.some((source) =>
                (source.opportunities ?? []).some(
                  (candidate) =>
                    `${candidate.source_key}|${candidate.name}|${candidate.source_url}` === key,
                ),
              )
            })

            return (
              <Card key={entry.site_id}>
                <CardHeader>
                  <div className="flex flex-wrap items-start justify-between gap-3">
                    <div>
                      <CardTitle>
                        {entry.site_name || `Site ${entry.site_id}`}
                      </CardTitle>
                      <CardDescription>{entry.message}</CardDescription>
                    </div>
                    <Badge tone={SITE_STATUS_TONE[entry.status] ?? 'neutral'}>
                      <StatusDot tone={SITE_STATUS_TONE[entry.status] ?? 'neutral'} />
                      {SITE_STATUS_LABEL[entry.status] ?? entry.status}
                    </Badge>
                  </div>
                </CardHeader>

                <CardContent className="space-y-4">
                  {entry.sources.length > 0 ? (
                    <div className="flex flex-wrap gap-2">
                      {entry.sources.map((source) => {
                        const manual =
                          manualSourceKeys.has(source.source_key) || isManualSource(source)
                        const tone = manual
                          ? 'info'
                          : (SOURCE_STATUS_TONE[source.status] ?? 'neutral')
                        const statusLabel = manual
                          ? 'Search manually'
                          : source.status_label || source.status
                        return (
                          <Badge key={source.source_key} tone={tone} title={source.message}>
                            <StatusDot tone={tone} />
                            {source.source_label}: {statusLabel}
                          </Badge>
                        )
                      })}
                    </div>
                  ) : null}

                  {manualSources.map((source) => (
                    <div
                      key={`manual-${source.source_key}`}
                      className="border-info-border bg-info-subtle rounded-md border p-3"
                    >
                      <div className="flex flex-wrap items-start justify-between gap-3">
                        <div className="min-w-0">
                          <p className="text-info text-[13px] font-medium">
                            {source.source_label}
                          </p>
                          <p className="text-ink-muted mt-0.5 text-[11px] leading-relaxed">
                            This source is not queried automatically. The result was not
                            retrieved by this platform, so nothing is shown for it here.
                          </p>
                        </div>
                        {source.search_url ? (
                          <a
                            href={source.search_url}
                            target="_blank"
                            rel="noopener noreferrer"
                            className="text-info inline-flex shrink-0 items-center gap-1 text-[11px] font-medium hover:underline"
                          >
                            Search this source
                            <ExternalLink className="size-3" aria-hidden="true" />
                          </a>
                        ) : (
                          <span className="text-ink-subtle shrink-0 text-[11px]">
                            No direct search link was provided.
                          </span>
                        )}
                      </div>
                      {source.message ? (
                        <p className="text-ink-subtle mt-1.5 text-[11px] leading-relaxed">
                          {source.message}
                        </p>
                      ) : null}
                    </div>
                  ))}

                  {automatedSources.map((source) => (
                    <SourceBlock key={`auto-${source.source_key}`} source={source} />
                  ))}

                  {unattributed.length > 0 ? (
                    <div className="border-line rounded-md border p-3">
                      <p className="text-ink text-[13px] font-medium">
                        Other agencies reported for this location
                      </p>
                      <ul className="mt-2.5 space-y-2">
                        {unattributed.map((opportunity) => (
                          <OpportunityCard
                            key={`unattributed-${opportunity.source_key}-${opportunity.name}`}
                            opportunity={opportunity}
                          />
                        ))}
                      </ul>
                    </div>
                  ) : null}

                  {automatedSources.length === 0 && manualSources.length === 0 ? (
                    <EmptyState
                      icon={Info}
                      title="No brokerage source was queried"
                      description="No brokerage source was queried for this location, so nothing can be reported about the agencies operating around it."
                    />
                  ) : null}

                  {entry.opportunities.length === 0 &&
                  automatedSources.length > 0 &&
                  automatedSources.every(
                    (source) => (source.opportunities ?? []).length === 0,
                  ) ? (
                    <EmptyState
                      icon={MapPin}
                      title="No agency was returned"
                      description="The automated sources did not return an agency for this location. This does not mean that no agency operates here."
                    />
                  ) : null}
                </CardContent>
              </Card>
            )
          })
        : null}

      {result ? (
        <Alert tone="warning" title="Before you rely on these results">
          {result.disclaimer}
        </Alert>
      ) : null}

      {result && totalOpportunities === 0 ? (
        <Alert tone="neutral" title="No agency was found">
          {`${formatNumber(totalOpportunities)} agencies or operators were returned across the recommended locations. Use the manual source links above to search the brokerage portals directly.`}
        </Alert>
      ) : null}
    </div>
  )
}
