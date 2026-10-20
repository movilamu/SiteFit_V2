'use client'

import * as React from 'react'
import { Search } from 'lucide-react'

import { Card, CardContent, CardDescription, CardHeader, CardTitle } from '@/components/ui/card'
import { Field, FieldHint, Label } from '@/components/ui/field'
import { Input, Select } from '@/components/ui/input'
import { importanceLabel } from '@/lib/criteria'
import type { FacilityDefinition, Importance } from '@/lib/types'

import { useWizard } from './wizard-context'

const IMPORTANCE_OPTIONS: Importance[] = ['required', 'preferred', 'not_important']

/**
 * Step 5 — the standard facility list.
 *
 * The full list is shown so the user can classify every facility, rather
 * than only the ones the catalogue suggested.  A filter makes the list
 * manageable without hiding anything.
 */
export function StepFacilities({ facilities }: { facilities: FacilityDefinition[] }) {
  const { brief, setFacilities } = useWizard()
  const [query, setQuery] = React.useState('')

  const importanceByKey = React.useMemo(() => {
    const map: Record<string, Importance> = {}
    for (const facility of brief.facilities) {
      map[facility.key] = facility.importance
    }
    return map
  }, [brief.facilities])

  const setImportance = React.useCallback(
    (key: string, importance: Importance) => {
      const label = facilities.find((item) => item.key === key)?.label ?? key
      const existing = brief.facilities.find((item) => item.key === key)
      if (existing) {
        setFacilities(
          brief.facilities.map((item) =>
            item.key === key ? { ...item, importance } : item,
          ),
        )
      } else {
        setFacilities([...brief.facilities, { key, label, importance }])
      }
    },
    [brief.facilities, facilities, setFacilities],
  )

  const visible = React.useMemo(() => {
    const needle = query.trim().toLowerCase()
    if (!needle) return facilities
    return facilities.filter(
      (facility) =>
        facility.label.toLowerCase().includes(needle) ||
        facility.category.toLowerCase().includes(needle),
    )
  }, [facilities, query])

  const requiredCount = Object.values(importanceByKey).filter((value) => value === 'required').length
  const preferredCount = Object.values(importanceByKey).filter((value) => value === 'preferred').length

  return (
    <Card>
      <CardHeader>
        <CardTitle>Facilities</CardTitle>
        <CardDescription>
          Classify each facility as required, preferred or not important. {requiredCount}{' '}
          required, {preferredCount} preferred.
        </CardDescription>
      </CardHeader>
      <CardContent className="space-y-4">
        <Field label="Filter facilities" htmlFor="facility-filter">
          <div className="relative">
            <Search
              className="text-ink-subtle pointer-events-none absolute top-1/2 left-3 size-3.5 -translate-y-1/2"
              aria-hidden="true"
            />
            <Input
              id="facility-filter"
              value={query}
              onChange={(event) => setQuery(event.target.value)}
              placeholder="e.g. loading, power, parking"
              className="pl-8"
            />
          </div>
        </Field>

        <div className="border-line divide-line divide-y rounded-lg border">
          {visible.length === 0 ? (
            <p className="text-ink-subtle px-4 py-6 text-center text-xs">
              No facility matches &ldquo;{query}&rdquo;.
            </p>
          ) : (
            visible.map((facility) => (
              <div
                key={facility.key}
                className="flex items-center justify-between gap-4 px-4 py-2.5"
              >
                <div className="min-w-0">
                  <Label htmlFor={`facility-${facility.key}`} className="block">
                    {facility.label}
                  </Label>
                  <span className="text-ink-subtle text-[11px] capitalize">
                    {facility.category}
                  </span>
                </div>
                <Select
                  id={`facility-${facility.key}`}
                  value={importanceByKey[facility.key] ?? 'not_important'}
                  onChange={(event) =>
                    setImportance(facility.key, event.target.value as Importance)
                  }
                  className="w-[170px] shrink-0"
                >
                  {IMPORTANCE_OPTIONS.map((option) => (
                    <option key={option} value={option}>
                      {importanceLabel(option)}
                    </option>
                  ))}
                </Select>
              </div>
            ))
          )}
        </div>

        <FieldHint>
          Facility data comes from the ingested property and map records. Where a
          facility is not recorded for a site, the platform reports it as unknown
          rather than as a failure.
        </FieldHint>
      </CardContent>
    </Card>
  )
}
