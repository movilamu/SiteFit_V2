import { render, screen, within } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { describe, expect, it, vi } from 'vitest'

import { StepParking } from '@/components/workflow/step-parking'
import { WizardProvider } from '@/components/workflow/wizard-context'

function renderStep() {
  return render(
    <WizardProvider>
      <StepParking />
    </WizardProvider>,
  )
}

describe('StepParking', () => {
  it('offers all three constraint behaviours explicitly', () => {
    renderStep()
    expect(screen.getByRole('radio', { name: /hard requirement/i })).toBeInTheDocument()
    expect(screen.getByRole('radio', { name: /preference/i })).toBeInTheDocument()
    expect(screen.getByRole('radio', { name: /flexible/i })).toBeInTheDocument()
  })

  it('states what each behaviour does to a failing site', () => {
    renderStep()
    expect(
      screen.getByText(/excluded from the shortlist/i),
    ).toBeInTheDocument()
    expect(screen.getByText(/lowers their suitability score/i)).toBeInTheDocument()
    expect(screen.getByText(/warning only/i)).toBeInTheDocument()
  })

  it('does not claim a behaviour is active until a target is set', () => {
    renderStep()
    expect(screen.getByText(/no parking target has been set/i)).toBeInTheDocument()
  })

  it('explains the consequence once a target is entered', async () => {
    const user = userEvent.setup()
    renderStep()

    const input = screen.getByLabelText(/minimum car parking spaces/i)
    await user.clear(input)
    await user.type(input, '50')

    expect(screen.getByText(/a parking target is set/i)).toBeInTheDocument()
  })

  it('lets the user change the behaviour with the keyboard', async () => {
    const user = userEvent.setup()
    renderStep()

    const flexible = screen.getByRole('radio', { name: /flexible/i })
    flexible.focus()
    await user.keyboard(' ')

    expect(flexible).toBeChecked()
    expect(screen.getByText('Selected')).toBeInTheDocument()
  })

  it('labels the parking inputs for assistive technology', () => {
    renderStep()
    const carSpaces = screen.getByLabelText(/minimum car parking spaces/i)
    const twoWheeler = screen.getByLabelText(/minimum two-wheeler spaces/i)
    const area = screen.getByLabelText(/minimum parking area/i)

    expect(carSpaces).toBeInTheDocument()
    expect(twoWheeler).toBeInTheDocument()
    expect(area).toBeInTheDocument()
  })
})
