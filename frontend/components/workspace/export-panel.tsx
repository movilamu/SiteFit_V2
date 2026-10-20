'use client'

import * as React from 'react'
import { Download, FileText, Printer, RefreshCw } from 'lucide-react'

import { Button } from '@/components/ui/button'
import { Alert } from '@/components/ui/feedback'
import { apiFetchBlob, fetchReportExportFormats } from '@/lib/api'
import type { ReportExportFormat, ReportExportFormatKey } from '@/lib/types'

/**
 * Export the executive report.
 *
 * The formats are described by the API rather than hard-coded here, so a
 * format the backend can produce is never missing from the interface and
 * a format the backend cannot produce is never offered.  The file is
 * downloaded as a blob, so the workspace is not navigated away from while
 * the export is produced.
 */
export function ExportPanel({ report }: { report: Record<string, unknown> | null }) {
  const [formats, setFormats] = React.useState<ReportExportFormat[] | null>(null)
  const [formatsError, setFormatsError] = React.useState<string | null>(null)
  const [busy, setBusy] = React.useState<ReportExportFormatKey | null>(null)
  const [error, setError] = React.useState<string | null>(null)
  const [failedFormat, setFailedFormat] = React.useState<ReportExportFormatKey | null>(null)
  const [message, setMessage] = React.useState<string | null>(null)

  React.useEffect(() => {
    let cancelled = false
    fetchReportExportFormats()
      .then((response) => {
        if (cancelled) return
        setFormats(response.formats ?? [])
      })
      .catch((err: unknown) => {
        if (cancelled) return
        setFormats([])
        setFormatsError(
          err instanceof Error
            ? err.message
            : 'The available export formats could not be loaded.',
        )
      })
    return () => {
      cancelled = true
    }
  }, [])

  const runExport = React.useCallback(
    async (format: ReportExportFormatKey) => {
      if (!report) return
      setBusy(format)
      setError(null)
      setFailedFormat(null)
      setMessage(null)
      try {
        const blob = await apiFetchBlob('/reports/export', {
          method: 'POST',
          body: { report, format },
        })
        const url = URL.createObjectURL(blob)
        const anchor = document.createElement('a')
        anchor.href = url
        anchor.download = `site-selection-report.${format}`
        anchor.rel = 'noopener'
        document.body.appendChild(anchor)
        anchor.click()
        anchor.remove()
        window.setTimeout(() => URL.revokeObjectURL(url), 0)
        setMessage('The report was exported.')
      } catch (err) {
        setFailedFormat(format)
        setError(
          err instanceof Error ? err.message : 'The report could not be exported.',
        )
      } finally {
        setBusy(null)
      }
    },
    [report],
  )

  const print = React.useCallback(() => {
    window.print()
  }, [])

  if (!report) {
    return (
      <div className="border-line rounded-md border p-4">
        <p className="text-ink text-[13px] font-medium">No report to export yet</p>
        <p className="text-ink-muted mt-1 text-[11px] leading-relaxed">
          Generate the report first, then export it.
        </p>
        <div className="mt-3">
          <Button type="button" variant="outline" size="sm" onClick={print}>
            <Printer />
            Print
          </Button>
        </div>
      </div>
    )
  }

  return (
    <div className="border-line rounded-md border p-4">
      <div className="flex flex-wrap items-start justify-between gap-3">
        <div className="min-w-0">
          <p className="text-ink text-[13px] font-medium">Export the report</p>
          <p className="text-ink-muted mt-0.5 text-[11px] leading-relaxed">
            The exported file contains the same report that is shown here, together
            with the weighting configuration and the requirement set that produced
            the ranking.
          </p>
        </div>
        <Button type="button" variant="outline" size="sm" onClick={print}>
          <Printer />
          Print
        </Button>
      </div>

      {formatsError ? (
        <p className="text-danger mt-3 text-[11px] leading-relaxed" role="alert">
          {formatsError}
        </p>
      ) : null}

      {formats && formats.length > 0 ? (
        <ul className="mt-3 space-y-2.5">
          {formats.map((format) => (
            <li key={format.key} className="min-w-0">
              <div className="flex flex-wrap items-center gap-3">
                <Button
                  type="button"
                  size="sm"
                  variant={format.key === 'pdf' ? 'default' : 'outline'}
                  onClick={() => void runExport(format.key)}
                  disabled={busy !== null}
                  aria-busy={busy === format.key}
                >
                  {busy === format.key ? (
                    <RefreshCw className="animate-spin" />
                  ) : (
                    <Download />
                  )}
                  {busy === format.key
                    ? `Exporting ${format.label}…`
                    : `Export ${format.label}`}
                </Button>
                <p className="text-ink-subtle min-w-0 text-[11px] leading-relaxed">
                  {format.description}
                </p>
              </div>
            </li>
          ))}
        </ul>
      ) : null}

      {!formats && !formatsError ? (
        <p className="text-ink-subtle mt-3 flex items-center gap-1.5 text-[11px]">
          <FileText className="size-3" aria-hidden="true" />
          Loading the available formats…
        </p>
      ) : null}

      {error ? (
        <Alert tone="danger" title="The export failed" className="mt-3">
          <p>{error}</p>
          {failedFormat ? (
            <div className="mt-2">
              <Button
                type="button"
                variant="outline"
                size="sm"
                onClick={() => void runExport(failedFormat)}
                disabled={busy !== null}
              >
                <RefreshCw />
                Try again
              </Button>
            </div>
          ) : null}
        </Alert>
      ) : null}

      {message ? (
        <p className="text-success mt-3 text-[11px] leading-relaxed" role="status">
          {message}
        </p>
      ) : null}
    </div>
  )
}
