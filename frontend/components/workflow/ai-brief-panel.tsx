'use client'

import * as React from 'react'
import { Sparkles, TriangleAlert } from 'lucide-react'

import { Alert, ErrorState } from '@/components/ui/feedback'
import { Badge } from '@/components/ui/badge'
import { Button } from '@/components/ui/button'
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from '@/components/ui/card'
import { Field, FieldHint, Label } from '@/components/ui/field'
import { Input, NumberInput, Select, Textarea } from '@/components/ui/input'
import { fetchParseRequirements } from '@/lib/api'
import { importanceLabel } from '@/lib/criteria'
import { formatNumber } from '@/lib/format'
import type {
  AcquisitionMode,
  Importance,
  ParsedRequirement,
  ParseResponse,
} from '@/lib/types'

import { useWizard } from './wizard-context'

/**
 * The AI-assisted requirement builder.
 *
 * The assistant converts natural language into a *draft*.  The draft is
 * always shown back to the user as editable fields and must be explicitly
 * applied.  The assistant never applies a requirement on its own and never
 * produces a score, a cost or a property fact.
 */
export function AiBriefPanel({
  onApplied,
}: {
  onApplied?: (message: string) => void
}) {
  const { brief, update, setRequirements, setFacilities, setParking, setBudgets } = useWizard()

  const [description, setDescription] = React.useState('')
  const [draft, setDraft] = React.useState<ParseResponse | null>(null)
  const [loading, setLoading] = React.useState(false)
  const [error, setError] = React.useState<string | null>(null)
  const [applied, setApplied] = React.useState(false)

  const interpret = async () => {
    if (description.trim().length < 3) return
    setLoading(true)
    setError(null)
    setApplied(false)
    try {
      const response = await fetchParseRequirements({
        description: description.trim(),
        business_type: brief.businessType || undefined,
      })
      setDraft(response)
    } catch (err) {
      setError(err instanceof Error ? err.message : 'The brief could not be interpreted.')
    } finally {
      setLoading(false)
    }
  }

  const applyDraft = () => {
    if (!draft) return

    if (draft.business_type) {
      update({ businessType: draft.business_type })
    }
    update({ acquisitionMode: draft.acquisition_mode as AcquisitionMode })

    setRequirements(
      draft.requirements.map((requirement) => ({
        key: requirement.key,
        label: requirement.label,
        importance: requirement.importance,
        value: (requirement.value ?? null) as number | boolean | string | null,
        valueType: requirement.value_type as 'number' | 'boolean' | 'select',
        unit: requirement.unit,
        minimum: null,
        maximum: null,
        options: [],
        helpText: requirement.source_quote,
      })),
    )

    if (draft.facilities.length > 0) {
      setFacilities(
        draft.facilities.map((facility) => ({
          key: facility.key,
          label: facility.label,
          importance: facility.importance as Importance,
        })),
      )
    }

    const parking = draft.parking as Record<string, unknown>
    setParking({
      minCarSpaces:
        typeof parking.min_car_spaces === 'number' ? parking.min_car_spaces : null,
      minTwoWheelerSpaces:
        typeof parking.min_two_wheeler_spaces === 'number'
          ? parking.min_two_wheeler_spaces
          : null,
      minParkingAreaSqft:
        typeof parking.min_parking_area_sqft === 'number'
          ? parking.min_parking_area_sqft
          : null,
      behaviour:
        parking.behaviour === 'hard' || parking.behaviour === 'flexible'
          ? parking.behaviour
          : 'preference',
    })

    const financial = draft.financial as Record<string, unknown>
    const budgets = Object.entries(financial)
      .filter(([, value]) => typeof value === 'number')
      .map(([key, value]) => ({
        key,
        label: key
          .split('_')
          .map((part) => part.charAt(0).toUpperCase() + part.slice(1))
          .join(' '),
        scope: 'acquisition',
        limit: value as number,
        behaviour: 'penalise' as const,
        appliesTo: ['buy', 'lease', 'either'] as AcquisitionMode[],
      }))
    if (budgets.length > 0) setBudgets(budgets)

    setApplied(true)
    onApplied?.('The interpreted requirements have been applied to your analysis. Review them before confirming.')
  }

  const updateDraftRequirement = (key: string, patch: Partial<ParsedRequirement>) => {
    setDraft((current) =>
      current
        ? {
            ...current,
            requirements: current.requirements.map((requirement) =>
              requirement.key === key ? { ...requirement, ...patch } : requirement,
            ),
          }
        : current,
    )
  }

  return (
    <Card>
      <CardHeader>
        <CardTitle className="flex items-center gap-2">
          <Sparkles className="text-primary size-4" aria-hidden="true" />
          Describe the site you are looking for
        </CardTitle>
        <CardDescription>
          Write the brief in your own words. The assistant turns it into editable
          requirements that you confirm before they are applied.
        </CardDescription>
      </CardHeader>
      <CardContent className="space-y-4">
        <Field
          label="Your brief"
          htmlFor="ai-brief"
          hint="For example: a premium family restaurant in Chennai with a budget of 3 crore and parking for 50 cars."
        >
          <Textarea
            id="ai-brief"
            value={description}
            onChange={(event) => setDescription(event.target.value)}
            placeholder="I want to open a premium family restaurant in Chennai with a budget of 3 crore and parking for 50 cars."
          />
        </Field>

        <Button type="button" onClick={interpret} disabled={loading || description.trim().length < 3}>
          {loading ? 'Interpreting…' : 'Interpret my brief'}
        </Button>

        {error ? (
          <ErrorState
            title="The brief could not be interpreted"
            description={error}
            onRetry={interpret}
          />
        ) : null}

        {draft ? (
          <div className="border-line bg-surface-muted space-y-4 rounded-lg border p-4">
            <div>
              <p className="section-eyebrow">AI interpreted your requirements as</p>
              <p className="text-ink mt-1.5 text-[13px] leading-relaxed">
                {draft.interpretation_summary}
              </p>
            </div>

            {draft.warnings.length > 0 ? (
              <Alert tone="warning" title="Points to check">
                <ul className="list-disc space-y-1 pl-4">
                  {draft.warnings.map((warning) => (
                    <li key={warning}>{warning}</li>
                  ))}
                </ul>
              </Alert>
            ) : null}

            {draft.requirements.length > 0 ? (
              <div>
                <p className="text-ink-muted mb-2 text-[11px] font-semibold tracking-[0.08em] uppercase">
                  Requirements
                </p>
                <ul className="divide-line divide-y rounded-md border border-line bg-surface">
                  {draft.requirements.map((requirement) => (
                    <li
                      key={requirement.key}
                      className="flex flex-col gap-2 px-3 py-2.5 sm:flex-row sm:items-center sm:justify-between"
                    >
                      <div className="min-w-0">
                        <p className="text-ink text-xs font-medium">{requirement.label}</p>
                        {requirement.source_quote ? (
                          <p className="text-ink-subtle mt-0.5 text-[11px] italic">
                            &ldquo;{requirement.source_quote}&rdquo;
                          </p>
                        ) : null}
                      </div>
                      <div className="flex shrink-0 items-center gap-2">
                        {requirement.value_type === 'number' ? (
                          <NumberInput
                            aria-label={`${requirement.label} value`}
                            className="w-32"
                            value={
                              typeof requirement.value === 'number' ? requirement.value : ''
                            }
                            onChange={(event) =>
                              updateDraftRequirement(requirement.key, {
                                value:
                                  event.target.value === '' ? null : Number(event.target.value),
                              })
                            }
                          />
                        ) : null}
                        <Select
                          aria-label={`${requirement.label} importance`}
                          className="w-[150px]"
                          value={requirement.importance}
                          onChange={(event) =>
                            updateDraftRequirement(requirement.key, {
                              importance: event.target.value as Importance,
                            })
                          }
                        >
                          <option value="required">Required</option>
                          <option value="preferred">Preferred</option>
                          <option value="not_important">Not important</option>
                        </Select>
                      </div>
                    </li>
                  ))}
                </ul>
              </div>
            ) : null}

            {Object.keys(draft.parking ?? {}).length > 0 ? (
              <div>
                <p className="text-ink-muted mb-2 text-[11px] font-semibold tracking-[0.08em] uppercase">
                  Parking
                </p>
                <div className="text-ink-muted flex flex-wrap gap-x-4 gap-y-1 text-xs">
                  {Object.entries(draft.parking).map(([key, value]) => (
                    <span key={key}>
                      <span className="text-ink-subtle capitalize">
                        {key.replace(/_/g, ' ')}:
                      </span>{' '}
                      <span className="text-ink font-medium">
                        {typeof value === 'number' ? formatNumber(value) : String(value)}
                      </span>
                    </span>
                  ))}
                </div>
              </div>
            ) : null}

            {Object.keys(draft.financial ?? {}).length > 0 ? (
              <div>
                <p className="text-ink-muted mb-2 text-[11px] font-semibold tracking-[0.08em] uppercase">
                  Financial inputs
                </p>
                <div className="text-ink-muted flex flex-wrap gap-x-4 gap-y-1 text-xs">
                  {Object.entries(draft.financial).map(([key, value]) => (
                    <span key={key}>
                      <span className="text-ink-subtle capitalize">
                        {key.replace(/_/g, ' ')}:
                      </span>{' '}
                      <span className="text-ink font-medium">
                        {typeof value === 'number' ? formatNumber(value) : String(value)}
                      </span>
                    </span>
                  ))}
                </div>
              </div>
            ) : null}

            <div className="flex flex-col gap-2 border-t border-line pt-3 sm:flex-row sm:items-center sm:justify-between">
              <p className="text-ink-subtle flex items-start gap-1.5 text-[11px] leading-relaxed">
                <TriangleAlert className="mt-0.5 size-3.5 shrink-0" aria-hidden="true" />
                Review each field before applying. Nothing changes until you apply, and
                you can still edit everything afterwards.
              </p>
              <Button type="button" onClick={applyDraft} className="shrink-0">
                Apply to my analysis
              </Button>
            </div>

            {applied ? (
              <p className="text-success text-xs" role="status">
                Applied. Review the requirements in the steps on the left before
                confirming the analysis.
              </p>
            ) : null}
          </div>
        ) : null}
      </CardContent>
    </Card>
  )
}
