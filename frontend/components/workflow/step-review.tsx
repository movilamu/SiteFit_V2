'use client'

import * as React from 'react'
import { AlertTriangle, Check, CircleDashed } from 'lucide-react'

import { Badge } from '@/components/ui/badge'
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from '@/components/ui/card'
import { Field, FieldHint, Label } from '@/components/ui/field'
import { Textarea } from '@/components/ui/input'
import { importanceLabel } from '@/lib/criteria'
import { formatMoney, formatNumber } from '@/lib/format'
import { cn } from '@/lib/utils'

import { useWizard } from './wizard-context'

/**
 * Render a requirement's target value for the review summary.
 *
 * A requirement that has not been given a value is reported as "Not set"
 * rather than as a number, so a blank field is never mistaken for a zero.
 */
function describeRequirementValue(requirement: {
  value: number | boolean | string | null
  valueType: string
  unit: string
}): string {
  const { value, valueType, unit } = requirement
  if (value === null || value === undefined || value === '') return 'Not set'
  if (valueType === 'boolean') return value ? 'Yes' : 'No'
  if (valueType === 'select') return String(value)
  const numeric = Number(value)
  if (!Number.isFinite(numeric)) return String(value)
  return `${formatNumber(numeric)}${unit ? ` ${unit}` : ''}`
}

function SummaryRow({
  label,
  value,
  emphasis,
}: {
  label: string
  value: React.ReactNode
  emphasis?: boolean
}) {
  return (
    <div className="flex items-baseline justify-between gap-4 py-1.5">
      <span className="text-ink-muted shrink-0 text-[11px] font-medium tracking-[0.04em] uppercase">
        {label}
      </span>
      <span
        className={cn(
          'min-w-0 text-right text-[13px]',
          emphasis ? 'text-ink font-medium' : 'text-ink-muted',
        )}
      >
        {value}
      </span>
    </div>
  )
}

function RequirementSummary({
  title,
  items,
  emptyText,
}: {
  title: string
  items: { key: string; label: string; importance: string; detail: string }[]
  emptyText: string
}) {
  return (
    <div className="border-line border-t px-5 py-4">
      <h4 className="section-eyebrow mb-2">{title}</h4>
      {items.length === 0 ? (
        <p className="text-ink-subtle text-xs">{emptyText}</p>
      ) : (
        <ul className="space-y-1.5">
          {items.map((item) => (
            <li key={item.key} className="flex items-start justify-between gap-3">
              <span className="text-ink-muted min-w-0 text-xs">{item.label}</span>
              <span className="flex shrink-0 items-center gap-2">
                {item.detail ? (
                  <span className="text-ink text-xs tabular-nums">{item.detail}</span>
                ) : null}
                <Badge
                  tone={
                    item.importance === 'required'
                      ? 'danger'
                      : item.importance === 'preferred'
                        ? 'warning'
                        : 'neutral'
                  }
                >
                  {importanceLabel(item.importance as never)}
                </Badge>
              </span>
            </li>
          ))}
        </ul>
      )}
    </div>
  )
}

/**
 * Step 7 — review and confirm.
 *
 * Nothing influences the ranking until the requirements are confirmed
 * here, which is also the point at which the platform states plainly what
 * it is and is not able to do.
 */
export function StepReview({
  businessTypeLabel,
  onConfirm,
  confirming,
}: {
  businessTypeLabel: string
  onConfirm: () => void
  confirming: boolean
}) {
  const { brief, update } = useWizard()

  const parkingItems = [
    brief.parking.minCarSpaces !== null
      ? {
          key: 'cars',
          label: 'Car parking spaces',
          importance: 'required',
          detail: `≥ ${formatNumber(brief.parking.minCarSpaces)}`,
        }
      : null,
    brief.parking.minTwoWheelerSpaces !== null
      ? {
          key: 'two-wheeler',
          label: 'Two-wheeler spaces',
          importance: 'required',
          detail: `≥ ${formatNumber(brief.parking.minTwoWheelerSpaces)}`,
        }
      : null,
    brief.parking.minParkingAreaSqft !== null
      ? {
          key: 'area',
          label: 'Parking area',
          importance: 'required',
          detail: `≥ ${formatNumber(brief.parking.minParkingAreaSqft)} sq ft`,
        }
      : null,
  ].filter(Boolean) as { key: string; label: string; importance: string; detail: string }[]

  const businessItems = brief.requirements
    .filter((requirement) => requirement.importance !== 'not_important')
    .map((requirement) => ({
      key: requirement.key,
      label: requirement.label,
      importance: requirement.importance,
      detail: describeRequirementValue(requirement),
    }))

  const facilityItems = brief.facilities
    .filter((facility) => facility.importance !== 'not_important')
    .map((facility) => ({
      key: facility.key,
      label: facility.label,
      importance: facility.importance,
      detail: '',
    }))

  const budgetItems = brief.financial.budgets
    .filter((budget) => budget.limit !== null)
    .map((budget) => ({
      key: budget.key,
      label: budget.label,
      importance: budget.behaviour === 'hard' ? 'required' : 'preferred',
      detail: formatMoney(budget.limit),
    }))

  const confirmed = brief.confirmedAt !== null

  return (
    <div className="space-y-5">
      <Card>
        <CardHeader>
          <CardTitle>Review your requirements</CardTitle>
          <CardDescription>
            These are the conditions the analysis will apply. Nothing influences the
            ranking until you confirm them.
          </CardDescription>
        </CardHeader>
        <CardContent className="px-5 py-4">
          <SummaryRow label="Analysis" value={brief.name || 'Untitled analysis'} emphasis />
          <SummaryRow label="Business type" value={businessTypeLabel || 'Not selected'} emphasis />
          <SummaryRow
            label="Acquisition"
            value={
              brief.acquisitionMode === 'buy'
                ? 'Buy'
                : brief.acquisitionMode === 'lease'
                  ? 'Lease'
                  : 'Buy or lease'
            }
          />
          <SummaryRow
            label="Search area"
            value={
              brief.location.center
                ? `${brief.location.city || 'Selected area'} · ${
                    brief.location.radiusKm
                  } km radius`
                : brief.location.city || 'Whole candidate inventory'
            }
          />
        </CardContent>

        <RequirementSummary
          title="Business requirements"
          items={businessItems}
          emptyText="No business requirements have been set."
        />
        <RequirementSummary
          title="Parking"
          items={parkingItems}
          emptyText="No parking target has been set, so parking is not assessed."
        />
        <RequirementSummary
          title="Facilities"
          items={facilityItems}
          emptyText="No facilities have been classified."
        />
        <RequirementSummary
          title="Budgets"
          items={budgetItems}
          emptyText="No budgets have been set."
        />

        <div className="border-line border-t px-5 py-4">
          <Field
            label="Notes for the report"
            htmlFor="analysis-notes"
            hint="Optional context for reviewers of the executive report."
          >
            <Textarea
              id="analysis-notes"
              value={brief.notes}
              maxLength={2000}
              onChange={(event) => update({ notes: event.target.value })}
              placeholder="e.g. Prefer sites within 2 km of an existing store to limit cannibalisation."
            />
          </Field>
        </div>
      </Card>

      <Card>
        <CardHeader>
          <CardTitle>What this analysis will and will not do</CardTitle>
        </CardHeader>
        <CardContent className="space-y-3">
          <div className="flex items-start gap-2.5">
            <Check className="text-success mt-0.5 size-4 shrink-0" aria-hidden="true" />
            <p className="text-ink-muted text-xs leading-relaxed">
              It will rank the candidate sites inside your search area against the
              criteria and weights you set, apply your requirements as filters and
              penalties, and explain every result in plain terms.
            </p>
          </div>
          <div className="flex items-start gap-2.5">
            <AlertTriangle className="text-warning mt-0.5 size-4 shrink-0" aria-hidden="true" />
            <p className="text-ink-muted text-xs leading-relaxed">
              It will not predict trading performance, and it does not replace site
              visits, commercial due diligence or local market knowledge. A high score
              means better fit against your stated criteria, not a guaranteed success.
            </p>
          </div>
          <div className="flex items-start gap-2.5">
            <CircleDashed className="text-ink-subtle mt-0.5 size-4 shrink-0" aria-hidden="true" />
            <p className="text-ink-muted text-xs leading-relaxed">
              Where data is missing it will say so. Unavailable costs, unknown facilities
              and uncovered criteria are reported rather than estimated.
            </p>
          </div>

          <div className="border-line bg-surface-muted mt-4 flex flex-col gap-3 rounded-lg border p-4 sm:flex-row sm:items-center sm:justify-between">
            <div className="min-w-0">
              <p className="text-ink text-[13px] font-medium">
                {confirmed ? 'Requirements confirmed' : 'Confirm to run the analysis'}
              </p>
              <p className="text-ink-muted mt-0.5 text-[11px] leading-relaxed">
                {confirmed
                  ? 'You can still change any requirement and re-run the analysis.'
                  : 'Confirming applies your requirements to the candidate sites and produces a ranked shortlist.'}
              </p>
            </div>
            <button
              type="button"
              onClick={onConfirm}
              disabled={confirming}
              className="bg-primary text-primary-foreground hover:bg-primary/90 focus-visible:ring-ring inline-flex h-9 shrink-0 items-center justify-center gap-2 rounded-md px-4 text-[13px] font-medium transition-colors focus-visible:ring-2 focus-visible:outline-none disabled:opacity-60"
            >
              {confirming ? 'Running analysis…' : confirmed ? 'Re-run analysis' : 'Confirm and analyse'}
            </button>
          </div>
        </CardContent>
      </Card>
    </div>
  )
}
