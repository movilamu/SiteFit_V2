'use client'

import { DataQualityPanel } from '@/components/workspace/data-quality-panel'

export default function DataQualityPage() {
  return (
    <div className="mx-auto w-full max-w-[1100px] px-4 py-6 lg:px-8 lg:py-8">
      <header className="mb-6">
        <p className="section-eyebrow">Reference</p>
        <h1 className="mt-1.5 text-2xl font-semibold tracking-tight text-ink">Data quality</h1>
        <p className="text-ink-muted mt-1.5 max-w-3xl text-sm leading-relaxed">
          The coverage, freshness and known limitations of the data behind every
          recommendation. This applies to the platform as a whole, not to one analysis.
        </p>
      </header>
      <DataQualityPanel />
    </div>
  )
}
