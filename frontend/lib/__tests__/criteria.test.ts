import { describe, expect, it } from 'vitest'

import {
  distributeCategoryWeight,
  equalCategoryWeights,
  equalLeafWeights,
  normalizeWeights,
  weightSum,
} from '@/lib/criteria'
import type { CategoryNode, CriteriaTree } from '@/lib/types'

const tree: CriteriaTree = {
  categories: [
    {
      key: 'population',
      label: 'Population',
      subcategories: [
        {
          key: 'population_core',
          label: 'Population',
          criteria: [
            {
              key: 'resident_density',
              label: 'Resident density',
              direction: 'benefit',
              scoring_mode: 'monotonic',
              target_band: null,
              data_field: 'demographic_data.population',
              data_available: true,
              notes: '',
            },
            {
              key: 'projected_growth',
              label: 'Projected growth',
              direction: 'benefit',
              scoring_mode: 'monotonic',
              target_band: null,
              data_field: 'demographic_data.population',
              data_available: true,
              notes: '',
            },
          ],
        },
      ],
    },
    {
      key: 'accessibility',
      label: 'Accessibility',
      subcategories: [
        {
          key: 'accessibility_core',
          label: 'Accessibility',
          criteria: [
            {
              key: 'drive_time_reach',
              label: 'Drive-time reach',
              direction: 'benefit',
              scoring_mode: 'monotonic',
              target_band: null,
              data_field: 'isochrone_cache.geom',
              data_available: true,
              notes: '',
            },
          ],
        },
      ],
    },
  ],
  category_keys: ['population', 'accessibility'],
  leaf_keys: ['resident_density', 'projected_growth', 'drive_time_reach'],
  leaf_count: 3,
  scorable_leaf_count: 3,
  notes: '',
}

describe('weight helpers', () => {
  it('splits category weights evenly by default', () => {
    const weights = equalCategoryWeights(tree)
    expect(weightSum(weights)).toBeCloseTo(1, 10)
    expect(weights.population).toBeCloseTo(0.5, 10)
    expect(weights.accessibility).toBeCloseTo(0.5, 10)
  })

  it('splits leaf weights evenly within each category', () => {
    const leaves = equalLeafWeights(tree)
    expect(weightSum(leaves.population)).toBeCloseTo(1, 10)
    expect(leaves.population.resident_density).toBeCloseTo(0.5, 10)
  })

  it('normalises a weight vector to sum to one', () => {
    const normalized = normalizeWeights({ a: 2, b: 6 })
    expect(weightSum(normalized)).toBeCloseTo(1, 10)
    expect(normalized.a).toBeCloseTo(0.25, 10)
  })

  it('leaves an already balanced vector untouched', () => {
    const weights = { a: 0.4, b: 0.6 }
    expect(normalizeWeights(weights)).toEqual(weights)
  })

  it('returns an empty vector rather than dividing by zero', () => {
    expect(normalizeWeights({})).toEqual({})
    expect(normalizeWeights({ a: 0, b: 0 })).toEqual({ a: 0, b: 0 })
  })
})

describe('distributeCategoryWeight', () => {
  const category = tree.categories[0] as CategoryNode

  it('splits the category weight evenly when no leaf weights are set', () => {
    const result = distributeCategoryWeight(category, 0.4, undefined)
    expect(result.resident_density).toBeCloseTo(0.2, 10)
    expect(result.projected_growth).toBeCloseTo(0.2, 10)
  })

  it('honours explicit leaf weights and gives the rest an equal share', () => {
    const result = distributeCategoryWeight(category, 0.4, {
      resident_density: 0.7,
      projected_growth: 0.3,
    })
    expect(result.resident_density).toBeCloseTo(0.28, 10)
    expect(result.projected_growth).toBeCloseTo(0.12, 10)
  })

  it('gives unmentioned leaves a share of the remainder', () => {
    const result = distributeCategoryWeight(category, 0.4, { resident_density: 1 })
    expect(result.resident_density).toBeCloseTo(0.4, 10)
    expect(result.projected_growth).toBeCloseTo(0, 10)
  })

  it('always distributes the full category weight', () => {
    const result = distributeCategoryWeight(category, 0.35, {
      resident_density: 0.7,
      projected_growth: 0.3,
    })
    expect(Object.values(result).reduce((total, value) => total + value, 0)).toBeCloseTo(
      0.35,
      10,
    )
  })
})
