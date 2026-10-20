'use client'

import * as React from 'react'

import {
  type Brief,
  type BriefFacility,
  type BriefRequirement,
  createBrief,
  DEFAULT_FINANCIAL,
  DEFAULT_PARKING,
  toRequirementPayload,
} from '@/lib/brief'
import type { LevelWeights } from '@/lib/types'

type WizardContextValue = {
  brief: Brief
  setBrief: React.Dispatch<React.SetStateAction<Brief>>
  update: (patch: Partial<Brief>) => void
  setRequirements: (requirements: BriefRequirement[]) => void
  setFacilities: (facilities: BriefFacility[]) => void
  setParking: (patch: Partial<Brief['parking']>) => void
  setBudgets: (budgets: Brief['financial']['budgets']) => void
  setWeights: (weights: LevelWeights) => void
  requirementPayload: () => Record<string, unknown>
  reset: () => void
}

const WizardContext = React.createContext<WizardContextValue | null>(null)

export function WizardProvider({
  initial,
  children,
}: {
  initial?: Partial<Brief>
  children: React.ReactNode
}) {
  const [brief, setBrief] = React.useState<Brief>(() => {
    const base = createBrief()
    return { ...base, ...initial, parking: { ...DEFAULT_PARKING, ...initial?.parking }, financial: { ...DEFAULT_FINANCIAL, ...initial?.financial } }
  })

  const update = React.useCallback((patch: Partial<Brief>) => {
    setBrief((current) => ({ ...current, ...patch }))
  }, [])

  const value = React.useMemo<WizardContextValue>(
    () => ({
      brief,
      setBrief,
      update,
      setRequirements: (requirements) => update({ requirements }),
      setFacilities: (facilities) => update({ facilities }),
      setParking: (patch) =>
        setBrief((current) => ({ ...current, parking: { ...current.parking, ...patch } })),
      setBudgets: (budgets) =>
        setBrief((current) => ({
          ...current,
          financial: { ...current.financial, budgets },
        })),
      setWeights: (weights) => update({ weights }),
      requirementPayload: () => toRequirementPayload(brief),
      reset: () => setBrief(createBrief()),
    }),
    [brief, update],
  )

  return <WizardContext.Provider value={value}>{children}</WizardContext.Provider>
}

export function useWizard(): WizardContextValue {
  const context = React.useContext(WizardContext)
  if (!context) {
    throw new Error('useWizard must be used inside a WizardProvider.')
  }
  return context
}
