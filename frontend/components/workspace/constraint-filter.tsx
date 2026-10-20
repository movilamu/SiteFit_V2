'use client'

import * as React from 'react'
import { Filter, RotateCcw } from 'lucide-react'

import { Button } from '@/components/ui/button'
import { Field, FieldHint, Label } from '@/components/ui/field'
import { Checkbox, NumberInput, Select } from '@/components/ui/input'
import { fetchSites } from '@/lib/api'
import type { SitesListResponse } from '@/lib/types'
const TENURE_OPTIONS = ['lease', 'freehold', 'licence']

export type ConstraintFilters = {
  minUnitSize: number | null
  maxRent: number | null
  tenures: string[]
}

const EMPTY: ConstraintFilters = { minUnitSize: null, maxRent: null, tenures: [] }

/**
 * Hard-constraint filters.
 *
 * These are the physical and legal viability filters.  A site that fails
 * one of them is removed from the shortlist, and the reasons are shown so
 * the exclusion is never silent.
 */
export function ConstraintFilter({
  onApply,
  onReset,
  applying,
  excludedCount,
}: {
  onApply: (filters: ConstraintFilters) => Promise<unknown>
  onReset: () => void
  applying: boolean
  excludedCount: number
}) {
  const [filters, setFilters] = React.useState<ConstraintFilters>(EMPTY)
  const [open, setOpen] = React.useState(false)
  const [error, setError] = React.useState<string | null>(null)

  const activeCount =
    (filters.minUnitSize !== null ? 1 : 0) +
    (filters.maxRent !== null ? 1 : 0) +
    (filters.tenures.length > 0 ? 1 : 0)

  const toggleTenure = (tenure: string) => {
    setFilters((current) => ({
      ...current,
      tenures: current.tenures.includes(tenure)
        ? current.tenures.filter((item) => item !== tenure)
        : [...current.tenures, tenure],
    }))
  }

  const apply = async () => {
    setError(null)
    try {
      await onApply(filters)
    } catch (err) {
      setError(err instanceof Error ? err.message : 'The filters could not be applied.')
    }
  }

  const reset = () => {
    setFilters(EMPTY)
    setError(null)
    onReset()
  }

  return (
    <div className="border-line rounded-md border">
      <button
        type="button"
        onClick={() => setOpen((value) => !value)}
        aria-expanded={open}
        className="focus-visible:ring-ring flex w-full items-center gap-2 px-3 py-2 text-left focus-visible:ring-2 focus-visible:outline-none"
      >
        <Filter className="text-ink-subtle size-3.5 shrink-0" aria-hidden="true" />
        <span className="text-ink text-[13px] font-medium">Hard constraints</span>
        {activeCount > 0 ? (
          <span className="bg-info-subtle text-info rounded px-1.5 py-0.5 text-[10px] font-semibold">
            {activeCount} active
          </span>
        ) : null}
        {excludedCount > 0 ? (
          <span className="text-danger ml-auto text-[11px]">
            {excludedCount} site{excludedCount === 1 ? '' : 's'} excluded
          </span>
        ) : null}
      </button>

      {open ? (
        <div className="border-line space-y-4 border-t px-3 py-3">
          <div className="grid gap-3 sm:grid-cols-2">
            <Field
              label="Minimum unit size"
              htmlFor="filter-min-unit-size"
              hint="Excludes sites with a smaller floor area."
            >
              <NumberInput
                id="filter-min-unit-size"
                min={0}
                step={100}
                suffix="sq ft"
                value={filters.minUnitSize ?? ''}
                onChange={(event) =>
                  setFilters((current) => ({
                    ...current,
                    minUnitSize:
                      event.target.value === '' ? null : Number(event.target.value),
                  }))
                }
              />
            </Field>

            <Field
              label="Maximum rent"
              htmlFor="filter-max-rent"
              hint="Excludes sites whose recorded rent exceeds this figure."
            >
              <NumberInput
                id="filter-max-rent"
                min={0}
                step={1000}
                suffix="₹"
                value={filters.maxRent ?? ''}
                onChange={(event) =>
                  setFilters((current) => ({
                    ...current,
                    maxRent: event.target.value === '' ? null : Number(event.target.value),
                  }))
                }
              />
            </Field>
          </div>

          <fieldset>
            <legend className="text-ink mb-1.5 text-xs font-medium">Accepted tenure</legend>
            <div className="flex flex-wrap gap-3">
              {TENURE_OPTIONS.map((tenure) => (
                <label key={tenure} className="flex cursor-pointer items-center gap-1.5 text-xs">
                  <Checkbox
                    checked={filters.tenures.includes(tenure)}
                    onChange={() => toggleTenure(tenure)}
                  />
                  <span className="text-ink-muted capitalize">{tenure}</span>
                </label>
              ))}
            </div>
            <FieldHint className="mt-1.5">
              Leave every tenure unticked to accept all of them.
            </FieldHint>
          </fieldset>

          {error ? (
            <p className="text-danger text-[11px]" role="alert">
              {error}
            </p>
          ) : null}

          <div className="flex flex-wrap items-center gap-2">
            <Button type="button" size="sm" onClick={apply} disabled={applying}>
              {applying ? 'Applying…' : 'Apply filters'}
            </Button>
            <Button
              type="button"
              size="sm"
              variant="ghost"
              onClick={reset}
              disabled={activeCount === 0}
            >
              <RotateCcw />
              Clear
            </Button>
          </div>
        </div>
      ) : null}
    </div>
  )
}

/** Build the query string for the site list endpoint. */
export function constraintQuery(filters: ConstraintFilters): string {
  const params = new URLSearchParams()
  if (filters.minUnitSize !== null) {
    params.set('min_unit_size', String(filters.minUnitSize))
  }
  if (filters.maxRent !== null) {
    params.set('max_rent', String(filters.maxRent))
  }
  if (filters.tenures.length > 0) {
    params.set('required_tenure', filters.tenures.join(','))
  }
  return params.toString()
}

/** Fetch the filtered site list. */
export async function fetchFilteredSites(filters: ConstraintFilters) {
  const query = constraintQuery(filters)
  return fetchSites(query)
}
