'use client'

import * as React from 'react'
import Link from 'next/link'
import { FileText, MapPinned } from 'lucide-react'

import { Button } from '@/components/ui/button'
import { Card, CardContent } from '@/components/ui/card'
import { EmptyState } from '@/components/ui/feedback'
import { fetchProjects, type Brief } from '@/lib/brief'
import { formatDateTime } from '@/lib/format'

export default function ReportsPage() {
  const [briefs, setBriefs] = React.useState<Brief[]>([])

  React.useEffect(() => {
    let cancelled = false
    fetchProjects()
      .then((rows) => {
        if (!cancelled) setBriefs(rows)
      })
      .catch(() => {
        if (!cancelled) setBriefs([])
      })
    return () => {
      cancelled = true
    }
  }, [])

  const withReports = briefs.filter((brief) => brief.confirmedAt)

  return (
    <div className="mx-auto w-full max-w-[1000px] px-4 py-6 lg:px-8 lg:py-8">
      <header className="mb-6">
        <p className="section-eyebrow">Reference</p>
        <h1 className="mt-1.5 text-2xl font-semibold tracking-tight text-ink">Reports</h1>
        <p className="text-ink-muted mt-1.5 max-w-3xl text-sm leading-relaxed">
          Executive decision reports are generated from within each analysis, where the
          ranking, cost position and data quality findings are already available.
        </p>
      </header>

      {withReports.length === 0 ? (
        <Card>
          <CardContent className="p-0">
            <EmptyState
              icon={FileText}
              title="No analyses are ready to report"
              description="Confirm the requirements of an analysis and generate its executive report from the workspace."
              action={
                <Button nativeButton={false} render={<Link href="/analyses/new" />}>
                  <MapPinned />
                  Start an analysis
                </Button>
              }
            />
          </CardContent>
        </Card>
      ) : (
        <ul className="space-y-3">
          {withReports.map((brief) => (
            <li key={brief.id}>
              <Card>
                <CardContent className="flex flex-wrap items-center justify-between gap-3 p-5">
                  <div className="min-w-0">
                    <p className="text-ink text-sm font-semibold">{brief.name}</p>
                    <p className="text-ink-subtle mt-0.5 text-[11px]">
                      {brief.businessType || 'Business type not set'} · updated{' '}
                      {formatDateTime(brief.updatedAt)}
                    </p>
                  </div>
                  <Button
                    size="sm"
                    variant="outline"
                    nativeButton={false} render={<Link href={`/analyses/${brief.id}`} />}
                  >
                    Open report
                  </Button>
                </CardContent>
              </Card>
            </li>
          ))}
        </ul>
      )}
    </div>
  )
}
