import { describe, expect, it } from 'vitest'

import { createBrief, toRequirementPayload } from '@/lib/brief'

describe('toRequirementPayload', () => {
  it('maps the parking behaviour through explicitly', () => {
    const brief = createBrief('Test')
    brief.parking = {
      minCarSpaces: 50,
      minTwoWheelerSpaces: 20,
      minParkingAreaSqft: 2000,
      behaviour: 'hard',
      scope: 'site',
    }

    const payload = toRequirementPayload(brief) as Record<string, any>
    expect(payload.parking.behaviour).toBe('hard')
    expect(payload.parking.min_car_spaces).toBe(50)
    expect(payload.parking.min_two_wheeler_spaces).toBe(20)
    expect(payload.parking.min_parking_area_sqft).toBe(2000)
  })

  it('drops budgets that have no limit rather than sending a null', () => {
    const brief = createBrief('Test')
    brief.financial = {
      budgetBehaviour: 'penalise',
      budgets: [
        {
          key: 'purchase_budget',
          label: 'Purchase budget',
          scope: 'acquisition',
          limit: null,
          behaviour: 'penalise',
          appliesTo: ['buy', 'either'],
        },
        {
          key: 'monthly_rent_budget',
          label: 'Monthly rent budget',
          scope: 'recurring_monthly',
          limit: 250000,
          behaviour: 'penalise',
          appliesTo: ['lease', 'either'],
        },
      ],
    }

    const payload = toRequirementPayload(brief) as Record<string, any>
    expect(payload.financial.budgets).toHaveLength(1)
    expect(payload.financial.budgets[0].key).toBe('monthly_rent_budget')
  })

  it('passes the acquisition mode through', () => {
    const brief = createBrief('Test')
    brief.acquisitionMode = 'lease'
    const payload = toRequirementPayload(brief) as Record<string, any>
    expect(payload.acquisition_mode).toBe('lease')
  })

  it('carries the importance level for every assessed requirement', () => {
    const brief = createBrief('Test')
    brief.requirements = [
      {
        key: 'seating_capacity',
        label: 'Seating capacity',
        importance: 'required',
        value: 40,
        valueType: 'number',
        unit: 'covers',
        minimum: 0,
        maximum: null,
        options: [],
        helpText: '',
      },
      {
        key: 'kitchen_required',
        label: 'Kitchen required',
        importance: 'not_important',
        value: true,
        valueType: 'boolean',
        unit: '',
        minimum: null,
        maximum: null,
        options: [],
        helpText: '',
      },
    ]

    const payload = toRequirementPayload(brief) as Record<string, any>
    expect(payload.business_requirements).toHaveLength(2)
    expect(payload.business_requirements[0].importance).toBe('required')
    expect(payload.business_requirements[1].importance).toBe('not_important')
  })
})
