import { render, screen } from '@testing-library/react'
import { describe, expect, it } from 'vitest'

import {
  ChartFrame,
  ColumnChart,
  HorizontalBarChart,
  StackedBar,
} from '@/components/ui/chart'

describe('HorizontalBarChart', () => {
  it('renders a labelled bar for every row', () => {
    render(
      <HorizontalBarChart
        data={[
          { key: 'a', label: 'Guindy', value: 90, tone: 'success' },
          { key: 'b', label: 'Adyar', value: 45, tone: 'warning' },
        ]}
        formatValue={(value) => `${value}%`}
      />,
    )

    expect(screen.getByText('Guindy')).toBeInTheDocument()
    expect(screen.getByText('Adyar')).toBeInTheDocument()
    expect(screen.getByText('90%')).toBeInTheDocument()
    expect(screen.getByText('45%')).toBeInTheDocument()
  })

  it('exposes the data to assistive technology as an image with a summary', () => {
    render(
      <HorizontalBarChart
        data={[{ key: 'a', label: 'Guindy', value: 90 }]}
        formatValue={(value) => `${value}%`}
      />,
    )

    const figure = screen.getByRole('img')
    expect(figure).toBeInTheDocument()
    expect(figure.getAttribute('aria-label')).toContain('Guindy')
    expect(figure.getAttribute('aria-label')).toContain('90%')
  })

  it('renders an honest empty state rather than a blank chart', () => {
    render(<HorizontalBarChart data={[]} />)
    expect(screen.getByText(/no variation to show/i)).toBeInTheDocument()
  })

  it('renders zero values without collapsing the layout', () => {
    render(
      <HorizontalBarChart
        data={[
          { key: 'a', label: 'Guindy', value: 0 },
          { key: 'b', label: 'Adyar', value: 0 },
        ]}
      />,
    )

    expect(screen.getByText('Guindy')).toBeInTheDocument()
    expect(screen.getByText('Adyar')).toBeInTheDocument()
  })
})

describe('ColumnChart', () => {
  it('renders a column for every row with its value', () => {
    render(
      <ColumnChart
        data={[
          { key: 'a', label: 'Site 1', value: 0.74 },
          { key: 'b', label: 'Site 2', value: 0.51 },
        ]}
        formatValue={(value) => value.toFixed(2)}
      />,
    )

    expect(screen.getByText('Site 1')).toBeInTheDocument()
    expect(screen.getByText('0.74')).toBeInTheDocument()
    expect(screen.getByText('0.51')).toBeInTheDocument()
  })

  it('renders an honest empty state', () => {
    render(<ColumnChart data={[]} />)
    expect(screen.getByText(/no variation to show/i)).toBeInTheDocument()
  })
})

describe('StackedBar', () => {
  it('lists every segment in the legend, including a zero segment', () => {
    render(
      <StackedBar
        segments={[
          { key: 'acquisition', label: 'Acquisition', value: 3_000_000, tone: 'info' },
          { key: 'setup', label: 'Setup', value: 750_000, tone: 'success' },
          { key: 'recurring', label: 'Recurring', value: 0, tone: 'warning' },
        ]}
        formatValue={(value) => String(value)}
      />,
    )

    expect(screen.getByText('Acquisition')).toBeInTheDocument()
    expect(screen.getByText('Setup')).toBeInTheDocument()
    expect(screen.getByText('Recurring')).toBeInTheDocument()
  })

  it('reports an unavailable component as unavailable rather than as zero', () => {
    render(
      <StackedBar
        segments={[
          { key: 'acquisition', label: 'Acquisition', value: 3_000_000, tone: 'info' },
          { key: 'setup', label: 'Setup', value: null, tone: 'success' },
        ]}
      />,
    )

    expect(screen.getByText('Unavailable')).toBeInTheDocument()
  })

  it('still produces a summary when nothing is known', () => {
    render(<StackedBar segments={[]} />)

    const figure = screen.getByRole('img')
    expect(figure.getAttribute('aria-label')).toContain('No variation to show')
  })
})

describe('ChartFrame', () => {
  it('renders the title and description', () => {
    render(
      <ChartFrame title="Cost composition" description="Over 60 months">
        <div>chart body</div>
      </ChartFrame>,
    )

    expect(screen.getByText('Cost composition')).toBeInTheDocument()
    expect(screen.getByText('Over 60 months')).toBeInTheDocument()
    expect(screen.getByText('chart body')).toBeInTheDocument()
  })
})
