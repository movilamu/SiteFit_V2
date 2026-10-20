'use client'

import * as React from 'react'
import { useRouter } from 'next/navigation'
import { ArrowLeft, ArrowRight } from 'lucide-react'

import { ErrorState } from '@/components/ui/feedback'
import { Button } from '@/components/ui/button'
import { fetchRequirementCatalog } from '@/lib/api'
import { persistProject } from '@/lib/brief'
import type { RequirementCatalog } from '@/lib/types'

import { AiBriefPanel } from '@/components/workflow/ai-brief-panel'
import { StepBusiness } from '@/components/workflow/step-business'
import { StepFacilities } from '@/components/workflow/step-facilities'
import { StepFinancial } from '@/components/workflow/step-financial'
import { StepLocation } from '@/components/workflow/step-location'
import { StepParking } from '@/components/workflow/step-parking'
import { StepRequirements } from '@/components/workflow/step-requirements'
import { StepReview } from '@/components/workflow/step-review'
import { WizardProvider, useWizard } from '@/components/workflow/wizard-context'
import {
  WIZARD_STEPS,
  WIZARD_STEPS as STEPS,
  WizardStepper,
  type WizardStepId,
} from '@/components/workflow/wizard-stepper'

export default function NewAnalysisPage() {
  return (
    <WizardProvider>
      <NewAnalysisInner />
    </WizardProvider>
  )
}

function NewAnalysisInner() {
  const router = useRouter()
  const { brief } = useWizard()

  const [catalog, setCatalog] = React.useState<RequirementCatalog | null>(null)
  const [loading, setLoading] = React.useState(true)
  const [error, setError] = React.useState<string | null>(null)
  const [retry, setRetry] = React.useState(0)

  const [step, setStep] = React.useState<WizardStepId>('business')
  const [completed, setCompleted] = React.useState<Set<WizardStepId>>(new Set())
  const [confirming, setConfirming] = React.useState(false)
  const [confirmError, setConfirmError] = React.useState<string | null>(null)

  React.useEffect(() => {
    let cancelled = false
    setLoading(true)
    setError(null)
    fetchRequirementCatalog()
      .then((response) => {
        if (!cancelled) setCatalog(response)
      })
      .catch((err: unknown) => {
        if (!cancelled) {
          setError(
            err instanceof Error
              ? err.message
              : 'The requirement catalogue could not be loaded.',
          )
        }
      })
      .finally(() => {
        if (!cancelled) setLoading(false)
      })
    return () => {
      cancelled = true
    }
  }, [retry])

  const stepIndex = STEPS.findIndex((item) => item.id === step)
  const isLast = stepIndex === STEPS.length - 1

  const goNext = React.useCallback(() => {
    setCompleted((current) => new Set(current).add(step))
    const next = STEPS[stepIndex + 1]
    if (next) setStep(next.id)
  }, [step, stepIndex])

  const goBack = React.useCallback(() => {
    const previous = STEPS[stepIndex - 1]
    if (previous) setStep(previous.id)
  }, [stepIndex])

  const confirm = React.useCallback(async () => {
    setConfirming(true)
    setConfirmError(null)
    try {
      const confirmed = { ...brief, confirmedAt: new Date().toISOString() }
      const saved = await persistProject(confirmed)
      router.push(`/analyses/${saved.id}`)
    } catch (err) {
      setConfirmError(
        err instanceof Error
          ? err.message
          : 'The analysis could not be saved.',
      )
    } finally {
      setConfirming(false)
    }
  }, [brief, router])

  const businessTypeLabel =
    catalog?.business_types.find((entry) => entry.key === brief.businessType)?.label ?? ''

  const canLeaveStep = (target: WizardStepId): boolean => {
    if (target === 'requirements' || target === 'facilities' || target === 'financial') {
      return brief.businessType !== ''
    }
    return true
  }

  return (
    <div className="mx-auto w-full max-w-[1400px] px-4 py-6 lg:px-8 lg:py-8">
      <header className="mb-6">
        <p className="section-eyebrow">New site-selection analysis</p>
        <h1 className="mt-1.5 text-2xl font-semibold tracking-tight text-ink">
          Define what a good site looks like
        </h1>
        <p className="text-ink-muted mt-1.5 max-w-3xl text-sm leading-relaxed">
          Work through the requirements in order. Every question is editable, and the
          platform will not apply anything until you confirm it.
        </p>
      </header>

      <div className="grid gap-6 lg:grid-cols-[264px_minmax(0,1fr)]">
        <aside className="lg:sticky lg:top-6 lg:self-start">
          <WizardStepper
            current={step}
            completed={completed}
            onNavigate={(target) => canLeaveStep(target) && setStep(target)}
          />
        </aside>

        <div className="min-w-0 space-y-5">
          {step === 'business' ? (
            <StepBusiness catalog={catalog} loading={loading} error={error} />
          ) : null}

          {step === 'location' ? <StepLocation /> : null}

          {step === 'requirements' ? (
            <div className="space-y-5">
              <AiBriefPanel />
              <StepRequirements />
            </div>
          ) : null}

          {step === 'parking' ? <StepParking /> : null}

          {step === 'facilities' ? (
            <StepFacilities facilities={catalog?.facilities ?? []} />
          ) : null}

          {step === 'financial' ? <StepFinancial catalog={catalog} /> : null}

          {step === 'review' ? (
            <StepReview
              businessTypeLabel={businessTypeLabel}
              onConfirm={confirm}
              confirming={confirming}
            />
          ) : null}

          {error && step !== 'business' ? (
            <ErrorState
              title="The catalogue could not be loaded"
              description={error}
              onRetry={() => setRetry((value) => value + 1)}
            />
          ) : null}

          <div className="flex items-center justify-between gap-3 border-t border-line pt-5">
            <Button
              type="button"
              variant="outline"
              onClick={goBack}
              disabled={stepIndex === 0}
            >
              <ArrowLeft />
              Back
            </Button>
            <div className="text-ink-subtle text-[11px]">
              Step {stepIndex + 1} of {STEPS.length}
            </div>
            {isLast ? null : (
              <Button type="button" onClick={goNext}>
                Continue
                <ArrowRight />
              </Button>
            )}
          </div>
        </div>
      </div>
    </div>
  )
}
