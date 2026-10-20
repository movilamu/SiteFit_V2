'use client'

import * as React from 'react'

import { Card, CardContent, CardDescription, CardHeader, CardTitle } from '@/components/ui/card'
import { Field, FieldHint, Label } from '@/components/ui/field'
import { Checkbox, Input, NumberInput, Select } from '@/components/ui/input'
import { importanceDescription, importanceLabel } from '@/lib/criteria'
import { formatNumber } from '@/lib/format'
import type { Importance } from '@/lib/types'

import { useWizard } from './wizard-context'
import type { BriefRequirement } from '@/lib/brief'

const IMPORTANCE_OPTIONS: Importance[] = ['required', 'preferred', 'not_important']

/** A single requirement row: importance, value and a short explanation. */
export function RequirementRow({
  label,
  importance,
  onImportanceChange,
  value,
  valueType,
  unit,
  minimum,
  maximum,
  options,
  helpText,
  onValueChange,
}: {
  label: string
  importance: Importance
  onImportanceChange: (importance: Importance) => void
  value: number | boolean | string | null
  valueType: 'number' | 'boolean' | 'select'
  unit: string
  minimum: number | null
  maximum: number | null
  options: string[]
  helpText: string
  onValueChange: (value: number | boolean | string | null) => void
}) {
  const inputId = React.useId()

  return (
    <div className="border-line flex flex-col gap-3 border-b px-5 py-4 last:border-b-0 lg:flex-row lg:items-start lg:gap-6">
      <div className="min-w-0 flex-1">
        <Label htmlFor={inputId}>{label}</Label>
        <p className="text-ink-subtle mt-0.5 text-[11px] leading-relaxed">
          {helpText || importanceDescription(importance)}
        </p>
      </div>

      <div className="grid shrink-0 gap-3 sm:grid-cols-2 lg:w-[420px]">
        <Field label="Importance" htmlFor={`${inputId}-importance`}>
          <Select
            id={`${inputId}-importance`}
            value={importance}
            onChange={(event) => onImportanceChange(event.target.value as Importance)}
          >
            {IMPORTANCE_OPTIONS.map((option) => (
              <option key={option} value={option}>
                {importanceLabel(option)}
              </option>
            ))}
          </Select>
        </Field>

        <Field label="Target" htmlFor={inputId}>
          {importance === 'not_important' ? (
            <p className="text-ink-subtle border-line bg-surface-muted flex h-9 items-center rounded-md border px-3 text-xs">
              Not assessed
            </p>
          ) : valueType === 'boolean' ? (
            <label className="border-line bg-surface flex h-9 items-center gap-2 rounded-md border px-3">
              <Checkbox
                id={inputId}
                checked={Boolean(value)}
                onChange={(event) => onValueChange(event.target.checked)}
              />
              <span className="text-ink-muted text-xs">Required at the site</span>
            </label>
          ) : valueType === 'select' ? (
            <Select
              id={inputId}
              value={typeof value === 'string' ? value : ''}
              onChange={(event) => onValueChange(event.target.value)}
            >
              <option value="">Not specified</option>
              {options.map((option) => (
                <option key={option} value={option}>
                  {option}
                </option>
              ))}
            </Select>
          ) : (
            <NumberInput
              id={inputId}
              suffix={unit}
              min={minimum ?? undefined}
              max={maximum ?? undefined}
              value={value === null || value === undefined ? '' : String(value)}
              onChange={(event) => {
                const raw = event.target.value
                onValueChange(raw === '' ? null : Number(raw))
              }}
            />
          )}
        </Field>
      </div>
    </div>
  )
}

/**
 * Step 3 — the business-specific requirements.
 *
 * Every importance level is editable: the catalogue's default profile is a
 * starting point, not a decision the user has to accept.
 */
export function StepRequirements() {
  const { brief, setRequirements } = useWizard()

  const updateRequirement = React.useCallback(
    (key: string, patch: Partial<BriefRequirement>) => {
      setRequirements(
        brief.requirements.map((requirement) =>
          requirement.key === key ? { ...requirement, ...patch } : requirement,
        ),
      )
    },
    [brief.requirements, setRequirements],
  )

  if (brief.requirements.length === 0) {
    return (
      <Card>
        <CardHeader>
          <CardTitle>Business requirements</CardTitle>
          <CardDescription>No requirements have been set for this analysis.</CardDescription>
        </CardHeader>
        <CardContent>
          <p className="text-ink-muted text-sm">
            Choose a business type on the first step to load its requirement profile.
          </p>
        </CardContent>
      </Card>
    )
  }

  const requiredCount = brief.requirements.filter((item) => item.importance === 'required').length
  const preferredCount = brief.requirements.filter((item) => item.importance === 'preferred').length

  return (
    <Card>
      <CardHeader>
        <CardTitle>Business requirements</CardTitle>
        <CardDescription>
          These are the conditions the site itself must meet. {requiredCount} required,{' '}
          {preferredCount} preferred.
        </CardDescription>
      </CardHeader>
      <CardContent className="p-0">
        {brief.requirements.map((requirement) => (
          <RequirementRow
            key={requirement.key}
            label={requirement.label}
            importance={requirement.importance}
            onImportanceChange={(importance) =>
              updateRequirement(requirement.key, { importance })
            }
            value={requirement.value}
            valueType={requirement.valueType}
            unit={requirement.unit}
            minimum={requirement.minimum}
            maximum={requirement.maximum}
            options={requirement.options}
            helpText={requirement.helpText}
            onValueChange={(value) => updateRequirement(requirement.key, { value })}
          />
        ))}
      </CardContent>
      <div className="border-line bg-surface-muted border-t px-5 py-3">
        <FieldHint>
          A requirement marked as <strong>required</strong> excludes any site that
          fails it. A <strong>preferred</strong> requirement keeps the site but lowers
          its suitability score. <strong>Not important</strong> requirements are not
          assessed at all.
        </FieldHint>
      </div>
    </Card>
  )
}
