'use client'

import * as React from 'react'
import { LocateFixed } from 'lucide-react'

import { Card, CardContent, CardDescription, CardHeader, CardTitle } from '@/components/ui/card'
import { Field, FieldHint, Label } from '@/components/ui/field'
import { Input, Slider } from '@/components/ui/input'
import { formatNumber } from '@/lib/format'

import { LocationPicker } from './location-picker'
import { useWizard } from './wizard-context'

/**
 * Step 2 — the geographic search area.
 *
 * The map is the primary control; the numeric fields below mirror it so
 * the same information is available to keyboard and screen-reader users.
 */
export function StepLocation() {
  const { brief, update } = useWizard()

  const center = brief.location.center
  const radiusKm = brief.location.radiusKm

  const setCenter = React.useCallback(
    (next: { latitude: number; longitude: number }) => {
      update({
        location: { ...brief.location, mode: 'radius', center: next },
      })
    },
    [brief.location, update],
  )

  return (
    <div className="space-y-5">
      <Card>
        <CardHeader>
          <CardTitle>Where should the platform look?</CardTitle>
          <CardDescription>
            Define the search area. Candidate sites are ranked relative to the sites
            found inside it, so a wider area changes the comparison.
          </CardDescription>
        </CardHeader>
        <CardContent className="space-y-5">
          <Field
            label="City or locality"
            htmlFor="location-city"
            hint="A label for the search area. It is used in the report and in the map heading."
          >
            <Input
              id="location-city"
              value={brief.location.city}
              maxLength={120}
              onChange={(event) =>
                update({ location: { ...brief.location, city: event.target.value } })
              }
              placeholder="e.g. Adyar, Chennai"
            />
          </Field>

          <LocationPicker
            center={center}
            radiusKm={radiusKm}
            onChange={({ center: next, radiusKm: nextRadius }) => {
              update({
                location: { ...brief.location, mode: 'radius', center: next, radiusKm: nextRadius },
              })
            }}
          />

          <div className="grid gap-4 sm:grid-cols-2">
            <Field
              label={`Search radius: ${formatNumber(radiusKm, { maximumFractionDigits: 1 })} km`}
              htmlFor="search-radius"
            >
              <Slider
                id="search-radius"
                min={0.5}
                max={25}
                step={0.5}
                value={radiusKm}
                onChange={(event) =>
                  update({ location: { ...brief.location, radiusKm: Number(event.target.value) } })
                }
              />
            </Field>

            <Field
              label="Centre coordinates"
              htmlFor="location-latitude"
              hint="Set by clicking the map. You can also type the coordinates directly."
            >
              <div className="flex items-center gap-2">
                <Input
                  id="location-latitude"
                  inputMode="decimal"
                  value={center ? center.latitude.toFixed(5) : ''}
                  onChange={(event) => {
                    const latitude = Number(event.target.value)
                    if (!Number.isFinite(latitude)) return
                    setCenter({ latitude, longitude: center?.longitude ?? 80.27 })
                  }}
                  placeholder="Latitude"
                />
                <Input
                  aria-label="Longitude"
                  inputMode="decimal"
                  value={center ? center.longitude.toFixed(5) : ''}
                  onChange={(event) => {
                    const longitude = Number(event.target.value)
                    if (!Number.isFinite(longitude)) return
                    setCenter({ latitude: center?.latitude ?? 13.08, longitude })
                  }}
                  placeholder="Longitude"
                />
              </div>
            </Field>
          </div>

          {center ? (
            <p className="text-ink-muted flex items-center gap-1.5 text-[11px]">
              <LocateFixed className="size-3.5" aria-hidden="true" />
              Search centre set at {center.latitude.toFixed(5)}, {center.longitude.toFixed(5)}.
            </p>
          ) : (
            <FieldHint>
              Click the map or type coordinates to set the search centre. Until a centre
              is set the analysis uses the full candidate inventory.
            </FieldHint>
          )}
        </CardContent>
      </Card>
    </div>
  )
}
