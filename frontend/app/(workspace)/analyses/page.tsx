'use client'

import * as React from 'react'
import Link from 'next/link'
import { ClipboardList, MapPinned, Trash2 } from 'lucide-react'

import { Badge } from '@/components/ui/badge'
import { Button } from '@/components/ui/button'
import { Card, CardContent } from '@/components/ui/card'
import { EmptyState } from '@/components/ui/feedback'
import { fetchProjects, removeProject, type Brief } from '@/lib/brief'
import { formatDateTime } from '@/lib/format'

/**
 * Explains where the analyses are stored.
 *
 * When Supabase is not configured the analyses live in this browser only,
 * and the user must be told that plainly rather than discovering it later.
 */
function LocalModeNotice() {
  const [configured, setConfigured] = React.useState<boolean | null>(null)

  React.useEffect(() => {
    let cancelled = false
    import('@/lib/supabase/config')
      .then(({ isSupabaseConfigured }) => {
        if (!cancelled) setConfigured(isSupabaseConfigured)
      })
      .catch(() => {
        if (!cancelled) setConfigured(false)
      })
    return () => {
      cancelled = true
    }
  }, [])

  if (configured !== false) return null

  return (
    <div className="border-warning-border bg-warning-subtle rounded-lg border px-4 py-3">
      <p className="text-warning text-sm font-medium">
        Analyses are stored in this browser only
      </p>
      <p className="text-ink-muted mt-1 text-xs leading-relaxed">
        Supabase is not configured, so there is no account to sign in with and the
        analyses are not shared between users or devices. Configure Supabase and
        sign in with Google to save them securely.
      </p>
    </div>
  )
}

export default function AnalysesPage() {
  const [briefs, setBriefs] = React.useState<Brief[]>([])
  const [loaded, setLoaded] = React.useState(false)
  const [error, setError] = React.useState<string | null>(null)

  React.useEffect(() => {
    let cancelled = false
    fetchProjects()
      .then((rows) => {
        if (!cancelled) setBriefs(rows)
      })
      .catch((err: unknown) => {
        if (!cancelled) {
          setError(
            err instanceof Error
              ? err.message
              : 'The analyses could not be loaded.',
          )
        }
      })
      .finally(() => {
        if (!cancelled) setLoaded(true)
      })
    return () => {
      cancelled = true
    }
  }, [])

  const remove = async (id: string) => {
    try {
      await removeProject(id)
      setBriefs(await fetchProjects())
    } catch (err) {
      setError(
        err instanceof Error ? err.message : 'The analysis could not be deleted.',
      )
    }
  }

  return (
    <div className="mx-auto w-full max-w-[1200px] px-4 py-6 lg:px-8 lg:py-8">
      <header className="mb-6 flex flex-col gap-4 sm:flex-row sm:items-end sm:justify-between">
        <div>
          <p className="section-eyebrow">Analyses</p>
          <h1 className="mt-1.5 text-2xl font-semibold tracking-tight text-ink">
            Site-selection analyses
          </h1>
          <p className="text-ink-muted mt-1.5 max-w-2xl text-sm leading-relaxed">
            Each analysis holds its own requirements, weights and results. Analyses are
            saved to your account; export the report to share or archive a copy.
          </p>
        </div>
        <Button className="shrink-0" nativeButton={false} render={<Link href="/analyses/new" />}>
          <MapPinned />
          New analysis
        </Button>
      </header>

      {error ? (
        <div className="border-danger-border bg-danger-subtle rounded-lg border px-4 py-3">
          <p className="text-danger text-sm font-medium">
            The analyses could not be loaded
          </p>
          <p className="text-ink-muted mt-1 text-xs">{error}</p>
        </div>
      ) : null}

      {!loaded ? (
        <div className="space-y-3">
          {Array.from({ length: 3 }).map((_, index) => (
            <div key={index} className="bg-surface-muted h-24 animate-pulse rounded-lg" />
          ))}
        </div>
      ) : briefs.length === 0 ? (
        <Card>
          <CardContent className="p-0">
            <EmptyState
              icon={ClipboardList}
              title="No analyses yet"
              description="Start a site-selection analysis to define your business type, requirements and budgets, then rank the candidate locations against them."
              action={
                <Button nativeButton={false} render={<Link href="/analyses/new" />}>Start an analysis</Button>
              }
            />
          </CardContent>
        </Card>
      ) : (
        <div className="space-y-4">
          <LocalModeNotice />

          <ul className="grid gap-3 md:grid-cols-2 xl:grid-cols-3">
          {briefs.map((brief) => (
            <li key={brief.id}>
              <Card className="flex h-full flex-col">
                <CardContent className="flex flex-1 flex-col p-5">
                  <div className="flex items-start justify-between gap-3">
                    <h2 className="text-ink min-w-0 text-sm font-semibold">
                      <Link
                        href={`/analyses/${brief.id}`}
                        className="hover:text-primary focus-visible:ring-ring rounded focus-visible:ring-2 focus-visible:outline-none"
                      >
                        {brief.name || 'Untitled analysis'}
                      </Link>
                    </h2>
                    <Badge tone={brief.confirmedAt ? 'success' : 'neutral'}>
                      {brief.confirmedAt ? 'Analysed' : 'Draft'}
                    </Badge>
                  </div>

                  <dl className="text-ink-muted mt-3 space-y-1.5 text-xs">
                    <div className="flex justify-between gap-3">
                      <dt className="text-ink-subtle">Business type</dt>
                      <dd className="truncate">{brief.businessType || 'Not set'}</dd>
                    </div>
                    <div className="flex justify-between gap-3">
                      <dt className="text-ink-subtle">Acquisition</dt>
                      <dd className="capitalize">{brief.acquisitionMode}</dd>
                    </div>
                    <div className="flex justify-between gap-3">
                      <dt className="text-ink-subtle">Search area</dt>
                      <dd className="truncate">
                        {brief.location.city || 'Not set'}
                      </dd>
                    </div>
                    <div className="flex justify-between gap-3">
                      <dt className="text-ink-subtle">Last updated</dt>
                      <dd>{formatDateTime(brief.updatedAt)}</dd>
                    </div>
                  </dl>

                  <div className="mt-4 flex items-center gap-2 pt-1">
                    <Button
                      size="sm"
                      variant="outline"
                      className="flex-1"
                      nativeButton={false} render={<Link href={`/analyses/${brief.id}`} />}
                    >
                      Open
                    </Button>
                    <Button
                      type="button"
                      size="icon-sm"
                      variant="ghost"
                      onClick={() => remove(brief.id)}
                      aria-label={`Delete ${brief.name || 'analysis'}`}
                    >
                      <Trash2 />
                    </Button>
                  </div>
                </CardContent>
              </Card>
            </li>
          ))}
          </ul>
        </div>
      )}
    </div>
  )
}
