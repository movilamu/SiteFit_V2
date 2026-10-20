'use client'

import * as React from 'react'
import { AlertTriangle, Check, Info, MapPin } from 'lucide-react'

import { Badge, StatusDot } from '@/components/ui/badge'
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from '@/components/ui/card'
import { EmptyState, ErrorState, LoadingState } from '@/components/ui/feedback'
import { Input } from '@/components/ui/input'
import { Table, TableBody, TableCell, TableHead, TableHeader, TableRow } from '@/components/ui/table'
import { scoreBand } from '@/lib/pilot-map'
import { formatScore } from '@/lib/format'
import type { CandidateSite } from '@/lib/types'
import { cn } from '@/lib/utils'

import { useWorkspace } from './workspace-context'
import { ConstraintFilter } from './constraint-filter'

const BAND_TONE = {
  strong: 'success',
  moderate: 'info',
  weak: 'warning',
  poor: 'danger',
} as const

const BAND_LABEL = {
  strong: 'Strong',
  moderate: 'Moderate',
  weak: 'Weak',
  poor: 'Poor',
} as const

/**
 * The ranked shortlist.
 *
 * The list and the map are two views of the same selection, so clicking
 * either one selects the same site.
 */
export function RankingPanel() {
  const {
    sites,
    scores,
    scoresError,
    loadingSites,
    loadingScores,
    sitesError,
    selectedSiteId,
    setSelectedSiteId,
    rankOf,
    scoreOf,
    evaluation,
    eligibleIds,
    excludedByFilter,
    applyFilters,
    resetFilters,
  } = useWorkspace()

  const [query, setQuery] = React.useState('')
  const [applyingFilters, setApplyingFilters] = React.useState(false)

  const exclusionReasons = React.useMemo(() => {
    const map: Record<string, string[]> = {}
    for (const entry of excludedByFilter) {
      map[entry.site_id] = entry.reasons
    }
    return map
  }, [excludedByFilter])

  const rows = React.useMemo(() => {
    const scored = new Map((scores?.sites ?? []).map((row) => [String(row.site_id), row]))
    const list = sites
      .map((site) => {
        const id = String(site.site_id)
        return {
          id,
          name: site.name || `Site ${id}`,
          place: readPlace(site),
          rank: rankOf(id),
          score: scoreOf(id),
          excluded: evaluation ? !eligibleIds.has(id) : false,
          exclusionReason:
            evaluation?.sites.find((item) => item.site_id === id)?.evaluation.hard_failures[0]
              ?.detail ?? exclusionReasons[id]?.join(' '),
        }
      })
      .filter((row) => {
        if (!query.trim()) return true
        const needle = query.trim().toLowerCase()
        return (
          row.name.toLowerCase().includes(needle) || row.place.toLowerCase().includes(needle)
        )
      })

    return list.sort((a, b) => {
      if (a.rank !== null && b.rank !== null) return a.rank - b.rank
      if (a.rank !== null) return -1
      if (b.rank !== null) return 1
      return a.name.localeCompare(b.name)
    })
  }, [sites, scores, rankOf, scoreOf, evaluation, eligibleIds, query, exclusionReasons])

  const excludedCount = rows.filter((row) => row.excluded).length

  if (sitesError) {
    return (
      <Card>
        <CardHeader>
          <CardTitle>Ranked shortlist</CardTitle>
          <CardDescription>The candidate inventory could not be loaded.</CardDescription>
        </CardHeader>
        <CardContent>
          <ErrorState title="No candidate sites" description={sitesError} />
        </CardContent>
      </Card>
    )
  }

  return (
    <Card>
      <CardHeader>
        <div className="flex flex-wrap items-start justify-between gap-3">
          <div>
            <CardTitle>Ranked shortlist</CardTitle>
            <CardDescription>
              {loadingScores
                ? 'Recalculating the ranking…'
                : `${rows.length} candidate site${rows.length === 1 ? '' : 's'} ranked${
                    excludedCount > 0 ? `, ${excludedCount} excluded by a hard requirement` : ''
                  }.`}
            </CardDescription>
          </div>
          <Input
            value={query}
            onChange={(event) => setQuery(event.target.value)}
            placeholder="Filter by name or area"
            aria-label="Filter the shortlist"
            className="w-full sm:w-56"
          />
        </div>
      </CardHeader>

      <CardContent className="space-y-3 p-0">
        <div className="px-5 pt-4">
          <ConstraintFilter
            applying={applyingFilters}
            excludedCount={excludedByFilter.length}
            onApply={async (filters) => {
              setApplyingFilters(true)
              try {
                await applyFilters(filters)
              } finally {
                setApplyingFilters(false)
              }
            }}
            onReset={resetFilters}
          />
        </div>

        {scoresError ? (
          <div className="px-5 pb-4">
            <ErrorState
              title="The ranking could not be calculated"
              description={scoresError}
            />
          </div>
        ) : null}

        {loadingSites ? (
          <LoadingState label="Loading candidate sites…" />
        ) : rows.length === 0 ? (
          <EmptyState
            icon={MapPin}
            title="No candidate sites to rank"
            description="The candidate inventory is empty for this search area. Widen the search radius or check the ingestion pipeline."
          />
        ) : (
          <Table>
            <TableHeader>
              <TableRow>
                <TableHead className="w-14">Rank</TableHead>
                <TableHead>Site</TableHead>
                <TableHead className="w-40">Position</TableHead>
                <TableHead className="w-28 text-right">Score</TableHead>
                <TableHead className="w-36">Assessment</TableHead>
              </TableRow>
            </TableHeader>
            <TableBody>
              {rows.map((row) => {
                const band = scoreBand(row.score)
                const isSelected = row.id === selectedSiteId
                return (
                  <TableRow
                    key={row.id}
                    onClick={() => setSelectedSiteId(row.id)}
                    tabIndex={0}
                    onKeyDown={(event) => {
                      if (event.key === 'Enter' || event.key === ' ') {
                        event.preventDefault()
                        setSelectedSiteId(row.id)
                      }
                    }}
                    aria-selected={isSelected}
                    className={cn(
                      'cursor-pointer',
                      isSelected ? 'bg-info-subtle hover:bg-info-subtle' : '',
                    )}
                  >
                    <TableCell className="text-ink text-xs font-semibold tabular-nums">
                      {row.rank ?? '—'}
                    </TableCell>
                    <TableCell>
                      <div className="flex items-center gap-2">
                        {isSelected ? (
                          <Check className="text-primary size-3.5 shrink-0" aria-hidden="true" />
                        ) : null}
                        <span className="text-ink font-medium">{row.name}</span>
                      </div>
                      {row.excluded ? (
                        <p className="text-danger mt-0.5 flex items-start gap-1 text-[11px]">
                          <AlertTriangle className="mt-0.5 size-3 shrink-0" aria-hidden="true" />
                          {row.exclusionReason ?? 'Excluded by a hard requirement.'}
                        </p>
                      ) : null}
                    </TableCell>
                    <TableCell className="text-ink-muted text-xs">{row.place}</TableCell>
                    <TableCell className="text-ink text-right text-xs font-semibold tabular-nums">
                      {formatScore(row.score)}
                    </TableCell>
                    <TableCell>
                      {row.excluded ? (
                        <Badge tone="danger">Excluded</Badge>
                      ) : row.score !== null ? (
                        <Badge tone={BAND_TONE[band]}>
                          <StatusDot tone={BAND_TONE[band]} />
                          {BAND_LABEL[band]}
                        </Badge>
                      ) : (
                        <Badge tone="neutral">
                          <Info className="size-3" aria-hidden="true" />
                          Not scored
                        </Badge>
                      )}
                    </TableCell>
                  </TableRow>
                )
              })}
            </TableBody>
          </Table>
        )}
      </CardContent>
    </Card>
  )
}

function readPlace(site: CandidateSite): string {
  const attributes = site.attributes ?? {}
  const city =
    (typeof attributes.city === 'string' && attributes.city) ||
    (typeof attributes.locality === 'string' && attributes.locality) ||
    (typeof attributes.district === 'string' && attributes.district) ||
    ''
  const area =
    (typeof attributes.locality === 'string' && attributes.locality) ||
    (typeof attributes.area === 'string' && attributes.area) ||
    ''
  if (area && city && area !== city) return `${area}, ${city}`
  if (city) return city
  if (area) return area

  // The site has no place name recorded, but its position is.  Showing
  // the coordinates is honest; claiming that nothing is recorded is not.
  const latitude = site.coordinates?.latitude
  const longitude = site.coordinates?.longitude
  if (typeof latitude === 'number' && typeof longitude === 'number') {
    return `${latitude.toFixed(4)}, ${longitude.toFixed(4)}`
  }
  return 'Location not recorded'
}
