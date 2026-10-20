'use client'

import * as React from 'react'
import { AlertTriangle, CheckCircle2, Info, Scale } from 'lucide-react'

import { Card, CardContent, CardDescription, CardHeader, CardTitle } from '@/components/ui/card'
import { Field, FieldHint, Label } from '@/components/ui/field'
import { NumberInput, Radio } from '@/components/ui/input'
import { cn } from '@/lib/utils'
import type { ConstraintBehaviour } from '@/lib/types'

import { useWizard } from './wizard-context'

const BEHAVIOURS: {
  key: ConstraintBehaviour
  label: string
  description: string
  icon: React.ComponentType<{ className?: string }>
  tone: 'danger' | 'warning' | 'info'
}[] = [
  {
    key: 'hard',
    label: 'Hard requirement',
    description: 'Sites that fail the parking requirement are excluded from the shortlist.',
    icon: AlertTriangle,
    tone: 'danger',
  },
  {
    key: 'preference',
    label: 'Preference',
    description: 'Sites are kept. Failing the requirement lowers their suitability score.',
    icon: Scale,
    tone: 'warning',
  },
  {
    key: 'flexible',
    label: 'Flexible',
    description: 'Sites are kept and the shortfall is shown as a warning only.',
    icon: Info,
    tone: 'info',
  },
]

const TONE_CLASSES: Record<string, string> = {
  danger: 'border-danger-border bg-danger-subtle text-danger',
  warning: 'border-warning-border bg-warning-subtle text-warning',
  info: 'border-info-border bg-info-subtle text-info',
}

/**
 * Step 4 — the parking requirement and, crucially, how it behaves.
 *
 * The behaviour is never chosen silently: the user makes an explicit
 * choice and the consequence of that choice is spelled out.
 */
export function StepParking() {
  const { brief, setParking } = useWizard()
  const parking = brief.parking

  const hasTarget =
    parking.minCarSpaces !== null ||
    parking.minTwoWheelerSpaces !== null ||
    parking.minParkingAreaSqft !== null

  return (
    <div className="space-y-5">
      <Card>
        <CardHeader>
          <CardTitle>Parking</CardTitle>
          <CardDescription>
            Set the minimum parking the site must provide. Leave a field empty if it does
            not matter.
          </CardDescription>
        </CardHeader>
        <CardContent className="space-y-5">
          <div className="grid gap-4 sm:grid-cols-3">
            <Field
              label="Minimum car parking spaces"
              htmlFor="min-car-spaces"
              hint="Number of cars the site must be able to hold."
            >
              <NumberInput
                id="min-car-spaces"
                min={0}
                step={1}
                suffix="spaces"
                value={parking.minCarSpaces ?? ''}
                onChange={(event) =>
                  setParking({
                    minCarSpaces:
                      event.target.value === '' ? null : Number(event.target.value),
                  })
                }
              />
            </Field>

            <Field
              label="Minimum two-wheeler spaces"
              htmlFor="min-two-wheeler"
              hint="Number of two-wheelers the site must be able to hold."
            >
              <NumberInput
                id="min-two-wheeler"
                min={0}
                step={1}
                suffix="spaces"
                value={parking.minTwoWheelerSpaces ?? ''}
                onChange={(event) =>
                  setParking({
                    minTwoWheelerSpaces:
                      event.target.value === '' ? null : Number(event.target.value),
                  })
                }
              />
            </Field>

            <Field
              label="Minimum parking area"
              htmlFor="min-parking-area"
              hint="Total paved parking area required."
            >
              <NumberInput
                id="min-parking-area"
                min={0}
                step={50}
                suffix="sq ft"
                value={parking.minParkingAreaSqft ?? ''}
                onChange={(event) =>
                  setParking({
                    minParkingAreaSqft:
                      event.target.value === '' ? null : Number(event.target.value),
                  })
                }
              />
            </Field>
          </div>
        </CardContent>
      </Card>

      <Card>
        <CardHeader>
          <CardTitle>How should the parking requirement behave?</CardTitle>
          <CardDescription>
            This determines what happens to a site that does not meet the requirement
            above.
          </CardDescription>
        </CardHeader>
        <CardContent>
          <fieldset>
            <legend className="sr-only">Parking constraint behaviour</legend>
            <div className="space-y-2">
              {BEHAVIOURS.map((behaviour) => {
                const selected = parking.behaviour === behaviour.key
                const Icon = behaviour.icon
                return (
                  <label
                    key={behaviour.key}
                    className={cn(
                      'flex cursor-pointer items-start gap-3 rounded-lg border p-3 transition-colors',
                      selected
                        ? 'border-primary bg-info-subtle'
                        : 'border-line hover:bg-surface-muted',
                    )}
                  >
                    <Radio
                      name="parking-behaviour"
                      value={behaviour.key}
                      checked={selected}
                      onChange={() => setParking({ behaviour: behaviour.key })}
                      className="mt-0.5"
                    />
                    <span className="min-w-0">
                      <span className="flex items-center gap-2">
                        <Icon className="size-4 shrink-0" aria-hidden="true" />
                        <span className="text-ink text-[13px] font-medium">
                          {behaviour.label}
                        </span>
                        {selected ? (
                          <span
                            className={cn(
                              'rounded-md border px-1.5 py-0.5 text-[10px] font-semibold',
                              TONE_CLASSES[behaviour.tone],
                            )}
                          >
                            Selected
                          </span>
                        ) : null}
                      </span>
                      <span className="text-ink-muted mt-0.5 block text-[11px] leading-relaxed">
                        {behaviour.description}
                      </span>
                    </span>
                  </label>
                )
              })}
            </div>
          </fieldset>

          {hasTarget ? (
            <p className="text-ink-muted mt-4 flex items-start gap-2 text-[11px] leading-relaxed">
              <CheckCircle2 className="text-success mt-0.5 size-3.5 shrink-0" aria-hidden="true" />
              A parking target is set. With the current behaviour, sites that do not
              meet it will be {parking.behaviour === 'hard' ? 'excluded' : 'kept and flagged'}.
            </p>
          ) : (
            <p className="text-ink-subtle mt-4 text-[11px] leading-relaxed">
              No parking target has been set, so parking is not assessed. Set at least
              one target to activate the behaviour above.
            </p>
          )}
        </CardContent>
      </Card>
    </div>
  )
}
