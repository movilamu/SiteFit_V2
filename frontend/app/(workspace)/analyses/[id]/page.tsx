'use client'

import * as React from 'react'
import Link from 'next/link'
import { useParams } from 'next/navigation'
import { ArrowLeft, Map as MapIcon } from 'lucide-react'

import { Badge } from '@/components/ui/badge'
import { Button } from '@/components/ui/button'
import { Card, CardContent } from '@/components/ui/card'
import { EmptyState, LoadingState } from '@/components/ui/feedback'
import { Tabs, TabsContent, TabsList, TabsTrigger } from '@/components/ui/tabs'
import SitesMap from '@/components/sites-map'
import { fetchProject, persistProject, type Brief } from '@/lib/brief'

import { BrokeragePanel } from '@/components/workspace/brokerage-panel'
import { ComparisonPanel } from '@/components/workspace/comparison-panel'
import { CostPanel } from '@/components/workspace/cost-panel'
import { DataQualityPanel } from '@/components/workspace/data-quality-panel'
import { DecompositionTable } from '@/components/workspace/decomposition-table'
import { ExplanationPanel } from '@/components/workspace/explanation-panel'
import { PropertyPanel } from '@/components/workspace/property-panel'
import { RankingPanel } from '@/components/workspace/ranking-panel'
import { ReportPanel } from '@/components/workspace/report-panel'
import { ScenariosPanel } from '@/components/workspace/scenarios-panel'
import { SensitivityPanel } from '@/components/workspace/sensitivity-panel'
import { WeightPanel } from '@/components/workspace/weight-panel'
import { WorkspaceProvider, useWorkspace } from '@/components/workspace/workspace-context'

export default function AnalysisWorkspacePage() {
  const params = useParams<{ id: string }>()
  const [brief, setBrief] = React.useState<Brief | null>(null)
  const [loaded, setLoaded] = React.useState(false)
  const [error, setError] = React.useState<string | null>(null)

  React.useEffect(() => {
    const id = Array.isArray(params?.id) ? params.id[0] : params?.id
    if (!id) return
    let cancelled = false
    fetchProject(id)
      .then((loaded) => {
        if (!cancelled) setBrief(loaded)
      })
      .catch((err: unknown) => {
        if (!cancelled) {
          setError(
            err instanceof Error
              ? err.message
              : 'The analysis could not be opened.',
          )
        }
      })
      .finally(() => {
        if (!cancelled) setLoaded(true)
      })
    return () => {
      cancelled = true
    }
  }, [params])

  if (!loaded) {
    return (
      <div className="px-4 py-10">
        <LoadingState label="Opening the analysis…" />
      </div>
    )
  }

  if (!brief) {
    return (
      <div className="mx-auto w-full max-w-3xl px-4 py-10">
        <Card>
          <CardContent className="p-0">
            <EmptyState
              title={error ? 'The analysis could not be opened' : 'Analysis not found'}
              description={
                error ??
                'This analysis could not be found. It may have been deleted, or it may belong to a different account.'
              }
              action={
                <Button nativeButton={false} render={<Link href="/analyses" />}>
                  <ArrowLeft />
                  Back to analyses
                </Button>
              }
            />
          </CardContent>
        </Card>
      </div>
    )
  }

  return (
    <WorkspaceProvider brief={brief}>
      <Workspace />
    </WorkspaceProvider>
  )
}

function Workspace() {
  const { brief, sites, scores, selectedSiteId, setSelectedSiteId, siteById, eligibleIds, method } =
    useWorkspace()

  const mapSites = React.useMemo(
    () =>
      sites
        .map((site) => {
          const id = String(site.site_id)
          const ranked = scores?.sites.find((row) => String(row.site_id) === id)
          return {
            id,
            name: site.name || `Site ${id}`,
            latitude: site.coordinates.latitude,
            longitude: site.coordinates.longitude,
            rank: ranked?.rank ?? 0,
            score: ranked?.score ?? null,
            excluded: eligibleIds.size > 0 && !eligibleIds.has(id),
          }
        })
        .sort((a, b) => a.rank - b.rank),
    [sites, scores, eligibleIds],
  )

  const selectedSite = selectedSiteId ? siteById[selectedSiteId] : null

  return (
    <div className="mx-auto w-full max-w-[1600px] px-4 py-6 lg:px-6 lg:py-8">
      <header className="mb-5 flex flex-col gap-3 lg:flex-row lg:items-start lg:justify-between">
        <div className="min-w-0">
          <Link
            href="/analyses"
            className="text-ink-muted hover:text-ink inline-flex items-center gap-1 text-[11px] font-medium"
          >
            <ArrowLeft className="size-3" aria-hidden="true" />
            All analyses
          </Link>
          <h1 className="text-ink mt-1.5 text-2xl font-semibold tracking-tight">
            {brief.name || 'Untitled analysis'}
          </h1>
          <div className="text-ink-muted mt-1.5 flex flex-wrap items-center gap-2 text-xs">
            <Badge tone="outline">{brief.businessType || 'Business type not set'}</Badge>
            <Badge tone="outline" className="capitalize">
              {brief.acquisitionMode}
            </Badge>
            {brief.location.city ? (
              <Badge tone="outline">{brief.location.city}</Badge>
            ) : null}
            {brief.confirmedAt ? (
              <Badge tone="success">Requirements confirmed</Badge>
            ) : (
              <Badge tone="warning">Draft — requirements not confirmed</Badge>
            )}
          </div>
        </div>
      </header>

      <div className="grid gap-5 xl:grid-cols-[320px_minmax(0,1fr)]">
        <aside className="xl:sticky xl:top-6 xl:self-start">
          <WeightPanel />
        </aside>

        <div className="min-w-0 space-y-5">
          <div className="grid gap-5 2xl:grid-cols-[minmax(0,1.15fr)_minmax(0,1fr)]">
            <Card className="overflow-hidden">
              <div className="border-line relative h-[420px] w-full">
                <SitesMap
                  sites={mapSites}
                  selectedSiteId={selectedSiteId}
                  onSelectSite={setSelectedSiteId}
                  catchment={null}
                  focus={
                    selectedSite
                      ? {
                          latitude: selectedSite.coordinates.latitude,
                          longitude: selectedSite.coordinates.longitude,
                        }
                      : null
                  }
                />
              </div>
              <div className="border-line text-ink-subtle flex flex-wrap items-center gap-x-4 gap-y-1 border-t px-4 py-2.5 text-[11px]">
                <span className="text-ink font-medium">Market map</span>
                <span className="flex items-center gap-1.5">
                  <span className="bg-success inline-block size-2 rounded-full" aria-hidden="true" />
                  Strong
                </span>
                <span className="flex items-center gap-1.5">
                  <span className="bg-info inline-block size-2 rounded-full" aria-hidden="true" />
                  Moderate
                </span>
                <span className="flex items-center gap-1.5">
                  <span className="bg-warning inline-block size-2 rounded-full" aria-hidden="true" />
                  Weak
                </span>
                <span className="flex items-center gap-1.5">
                  <span className="bg-danger inline-block size-2 rounded-full" aria-hidden="true" />
                  Poor
                </span>
                <span className="ml-auto">
                  Markers show the rank. Click a marker to inspect the site.
                </span>
              </div>
            </Card>

            <RankingPanel />
          </div>

          <Tabs defaultValue="explanation">
            <TabsList>
              <TabsTrigger value="explanation">Why this site</TabsTrigger>
              <TabsTrigger value="comparison">Comparison</TabsTrigger>
              <TabsTrigger value="cost">Cost analysis</TabsTrigger>
              <TabsTrigger value="property">Property intelligence</TabsTrigger>
              <TabsTrigger value="brokerage">Brokerage intelligence</TabsTrigger>
              <TabsTrigger value="scenarios">Scenarios</TabsTrigger>
              <TabsTrigger value="sensitivity">Sensitivity</TabsTrigger>
              <TabsTrigger value="quality">Data quality</TabsTrigger>
              <TabsTrigger value="report">Report</TabsTrigger>
            </TabsList>

            <TabsContent value="explanation" className="space-y-5 pt-5">
              <ExplanationPanel />
              <DecompositionTable
                siteId={selectedSiteId}
                weights={scores?.effective_weights ?? {}}
                method={method}
              />
            </TabsContent>
            <TabsContent value="comparison" className="pt-5">
              <ComparisonPanel />
            </TabsContent>
            <TabsContent value="cost" className="pt-5">
              <CostPanel />
            </TabsContent>
            <TabsContent value="property" className="pt-5">
              <PropertyPanel />
            </TabsContent>
            <TabsContent value="brokerage" className="pt-5">
              <BrokeragePanel />
            </TabsContent>
            <TabsContent value="scenarios" className="pt-5">
              <ScenariosPanel />
            </TabsContent>
            <TabsContent value="sensitivity" className="pt-5">
              <SensitivityPanel />
            </TabsContent>
            <TabsContent value="quality" className="pt-5">
              <DataQualityPanel />
            </TabsContent>
            <TabsContent value="report" className="pt-5">
              <ReportPanel />
            </TabsContent>
          </Tabs>
        </div>
      </div>
    </div>
  )
}
