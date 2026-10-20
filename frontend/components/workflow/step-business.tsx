'use client'

import * as React from 'react'
import { Building2, Check } from 'lucide-react'

import { Card, CardContent, CardDescription, CardHeader, CardTitle } from '@/components/ui/card'
import { Field, FieldHint, Label } from '@/components/ui/field'
import { Input, Radio, Select } from '@/components/ui/input'
import { cn } from '@/lib/utils'
import type { RequirementCatalog } from '@/lib/types'

import { useWizard } from './wizard-context'

/**
 * Step 1 — the business or site type and the acquisition mode.
 *
 * The catalogue is loaded from the API so that the interface never
 * hard-codes the list of business types.
 */
export function StepBusiness({
  catalog,
  loading,
  error,
}: {
  catalog: RequirementCatalog | null
  loading: boolean
  error: string | null
}) {
  const { brief, update, setRequirements, setFacilities } = useWizard()

  const selectBusinessType = React.useCallback(
    (businessType: string) => {
      const entry = catalog?.business_types.find((item) => item.key === businessType)
      if (!entry) return

      // Apply the catalogue's default requirement profile.  The user can
      // change every importance level on the next step.
      setRequirements(
        Object.entries(entry.requirements).map(([key, importance]) => {
          const definition = catalog?.requirements.find((item) => item.key === key)
          return {
            key,
            label: definition?.label ?? key,
            importance,
            value:
              typeof definition?.default === 'number' ||
              typeof definition?.default === 'boolean' ||
              typeof definition?.default === 'string'
                ? definition.default
                : null,
            valueType: (definition?.value_type ?? 'number') as
              | 'number'
              | 'boolean'
              | 'select',
            unit: definition?.unit ?? '',
            minimum: definition?.minimum ?? null,
            maximum: definition?.maximum ?? null,
            options: definition?.options ?? [],
            helpText: definition?.help_text ?? '',
          }
        }),
      )

      const facilities = [
        ...entry.required_facilities.map((key) => ({
          key,
          label: catalog?.facilities.find((item) => item.key === key)?.label ?? key,
          importance: 'required' as const,
        })),
        ...entry.preferred_facilities.map((key) => ({
          key,
          label: catalog?.facilities.find((item) => item.key === key)?.label ?? key,
          importance: 'preferred' as const,
        })),
      ]
      setFacilities(facilities)
      update({ businessType })
    },
    [catalog, setFacilities, setRequirements, update],
  )

  if (loading) {
    return (
      <Card>
        <CardHeader>
          <CardTitle>Business type</CardTitle>
          <CardDescription>Loading the business type catalogue…</CardDescription>
        </CardHeader>
        <CardContent>
          <div className="grid gap-3 sm:grid-cols-2 lg:grid-cols-3">
            {Array.from({ length: 9 }).map((_, index) => (
              <div key={index} className="bg-surface-muted h-20 animate-pulse rounded-lg" />
            ))}
          </div>
        </CardContent>
      </Card>
    )
  }

  if (error) {
    return (
      <Card>
        <CardHeader>
          <CardTitle>Business type</CardTitle>
          <CardDescription>The catalogue could not be loaded.</CardDescription>
        </CardHeader>
        <CardContent>
          <p className="text-danger text-sm" role="alert">
            {error}
          </p>
        </CardContent>
      </Card>
    )
  }

  const modes =
    catalog?.acquisition_modes.filter((mode) => {
      const entry = catalog.business_types.find((item) => item.key === brief.businessType)
      return !entry || entry.acquisition_modes.includes(mode.key)
    }) ?? []

  return (
    <div className="space-y-5">
      <Card>
        <CardHeader>
          <CardTitle>What kind of site are you looking for?</CardTitle>
          <CardDescription>
            This determines which questions you are asked and which facilities are
            suggested. You can change every requirement afterwards.
          </CardDescription>
        </CardHeader>
        <CardContent className="space-y-5">
          <Field
            label="Analysis name"
            htmlFor="analysis-name"
            hint="A short name you will recognise in the analysis list."
          >
            <Input
              id="analysis-name"
              value={brief.name}
              maxLength={120}
              onChange={(event) => update({ name: event.target.value })}
              placeholder="e.g. South Chennai family restaurant expansion"
            />
          </Field>

          <fieldset>
            <legend className="section-eyebrow mb-2">Business or site type</legend>
            <div className="grid gap-2 sm:grid-cols-2 lg:grid-cols-3">
              {(catalog?.business_types ?? []).map((entry) => {
                const selected = brief.businessType === entry.key
                return (
                  <button
                    key={entry.key}
                    type="button"
                    onClick={() => selectBusinessType(entry.key)}
                    aria-pressed={selected}
                    className={cn(
                      'group relative flex flex-col items-start gap-1 rounded-lg border p-3 text-left transition-colors',
                      'focus-visible:ring-ring focus-visible:ring-2 focus-visible:outline-none',
                      selected
                        ? 'border-primary bg-info-subtle'
                        : 'border-line bg-surface hover:border-line-strong hover:bg-surface-muted',
                    )}
                  >
                    <span className="flex w-full items-center gap-2">
                      {selected ? (
                        <span className="bg-primary text-primary-foreground flex size-4 shrink-0 items-center justify-center rounded-full">
                          <Check className="size-2.5" aria-hidden="true" />
                        </span>
                      ) : (
                        <Building2
                          className="text-ink-subtle size-4 shrink-0"
                          aria-hidden="true"
                        />
                      )}
                      <span className="text-ink text-[13px] font-medium">{entry.label}</span>
                    </span>
                    {entry.description ? (
                      <span className="text-ink-subtle pl-6 text-[11px] leading-snug">
                        {entry.description}
                      </span>
                    ) : null}
                  </button>
                )
              })}
            </div>
          </fieldset>
        </CardContent>
      </Card>

      {brief.businessType ? (
        <Card>
          <CardHeader>
            <CardTitle>How do you intend to occupy the site?</CardTitle>
            <CardDescription>
              This changes which cost lines the analysis assesses.
            </CardDescription>
          </CardHeader>
          <CardContent>
            <fieldset>
              <legend className="sr-only">Acquisition mode</legend>
              <div className="space-y-2">
                {modes.map((mode) => (
                  <label
                    key={mode.key}
                    className={cn(
                      'flex cursor-pointer items-start gap-2.5 rounded-lg border p-3 transition-colors',
                      brief.acquisitionMode === mode.key
                        ? 'border-primary bg-info-subtle'
                        : 'border-line hover:bg-surface-muted',
                    )}
                  >
                    <Radio
                      name="acquisition-mode"
                      value={mode.key}
                      checked={brief.acquisitionMode === mode.key}
                      onChange={() => update({ acquisitionMode: mode.key })}
                      className="mt-0.5"
                    />
                    <span>
                      <span className="text-ink block text-[13px] font-medium">
                        {mode.label}
                      </span>
                      <span className="text-ink-muted block text-[11px] leading-relaxed">
                        {mode.description}
                      </span>
                    </span>
                  </label>
                ))}
              </div>
            </fieldset>
            <FieldHint className="mt-3">
              &ldquo;Buy or lease&rdquo; compares both sets of economics wherever the
              underlying published data allows. Where a figure is not published it is
              reported as unavailable rather than estimated.
            </FieldHint>
          </CardContent>
        </Card>
      ) : null}
    </div>
  )
}
