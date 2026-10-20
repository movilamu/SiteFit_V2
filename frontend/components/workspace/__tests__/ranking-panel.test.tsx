import { render, screen, waitFor, within } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { beforeEach, describe, expect, it, vi } from 'vitest'

vi.mock('@/lib/api', () => ({
  fetchCriteria: vi.fn(),
  fetchScores: vi.fn(),
  fetchEvaluate: vi.fn(),
  fetchSites: vi.fn(),
}))

import { fetchCriteria, fetchEvaluate, fetchScores, fetchSites } from '@/lib/api'

import { RankingPanel } from '@/components/workspace/ranking-panel'
import { WorkspaceProvider } from '@/components/workspace/workspace-context'
import { createBrief } from '@/lib/brief'

const criteria = {
  categories: [],
  category_keys: [],
  leaf_keys: [],
  leaf_count: 0,
  scorable_leaf_count: 0,
  notes: '',
}

function mockApi(overrides: { sites?: any[]; scores?: any; sitesError?: string } = {}) {
  vi.mocked(fetchCriteria).mockResolvedValue(criteria as never)
  vi.mocked(fetchScores).mockResolvedValue(
    (overrides.scores ?? {
      method: 'weighted_sum',
      sites: [],
      effective_weights: {},
      dropped_criteria: [],
      coverage: 1,
    }) as never,
  )
  vi.mocked(fetchEvaluate).mockResolvedValue({
    sites: [],
    evaluated_count: 0,
    eligible_count: 0,
    excluded_count: 0,
    penalty_rate: 0.25,
    notes: [],
  } as never)
  if (overrides.sitesError) {
    vi.mocked(fetchSites).mockRejectedValue(new Error(overrides.sitesError) as never)
  } else {
    vi.mocked(fetchSites).mockResolvedValue({
      count: overrides.sites?.length ?? 0,
      filters_applied: {},
      sites: overrides.sites ?? [],
      excluded: [],
    } as never)
  }
}

function renderRanking() {
  return render(
    <WorkspaceProvider brief={createBrief('Test analysis')}>
      <RankingPanel />
    </WorkspaceProvider>,
  )
}

describe('RankingPanel', () => {
  beforeEach(() => {
    mockApi()
  })

  it('shows a loading state while the inventory is being fetched', async () => {
    mockApi()
    renderRanking()
    expect(screen.getByText(/loading candidate sites/i)).toBeInTheDocument()
    await waitFor(() => {
      expect(screen.queryByText(/loading candidate sites/i)).not.toBeInTheDocument()
    })
  })

  it('shows an empty state when there are no candidate sites', async () => {
    mockApi({ sites: [] })
    renderRanking()
    await waitFor(() => {
      expect(screen.getByText(/no candidate sites to rank/i)).toBeInTheDocument()
    })
  })

  it('shows an error state with the reason when the inventory cannot be loaded', async () => {
    mockApi({ sitesError: 'Candidate inventory is unavailable.' })
    renderRanking()
    await waitFor(() => {
      expect(screen.getByText(/candidate inventory is unavailable/i)).toBeInTheDocument()
    })
  })

  it('lists the ranked sites with their score and band', async () => {
    mockApi({
      sites: [
        {
          site_id: 'site-1',
          name: 'Anna Salai',
          coordinates: { latitude: 13.05, longitude: 80.24 },
          unit_size: 1500,
          rent: 200000,
          tenure: 'lease',
          status: 'active',
          attractiveness: 0.8,
          attributes: { city: 'Chennai' },
        },
        {
          site_id: 'site-2',
          name: 'T Nagar',
          coordinates: { latitude: 13.04, longitude: 80.22 },
          unit_size: 900,
          rent: 120000,
          tenure: 'lease',
          status: 'active',
          attractiveness: 0.6,
          attributes: { city: 'Chennai' },
        },
      ],
      scores: {
        method: 'weighted_sum',
        sites: [
          { rank: 1, site_id: 'site-1', score: 0.81 },
          { rank: 2, site_id: 'site-2', score: 0.42 },
        ],
        effective_weights: {},
        dropped_criteria: [],
        coverage: 1,
      },
    })

    renderRanking()
    await waitFor(() => {
      expect(screen.getByText('Anna Salai')).toBeInTheDocument()
    })
    expect(screen.getByText('T Nagar')).toBeInTheDocument()
    // The score arrives with the ranking, which resolves independently of
    // the inventory.
    expect(await screen.findByText('0.810')).toBeInTheDocument()
    expect(screen.getByText('0.420')).toBeInTheDocument()
    expect(screen.getByText('Strong')).toBeInTheDocument()
    expect(screen.getByText('Moderate')).toBeInTheDocument()
  })

  it('selects a site with the keyboard', async () => {
    const user = userEvent.setup()
    mockApi({
      sites: [
        {
          site_id: 'site-1',
          name: 'Anna Salai',
          coordinates: { latitude: 13.05, longitude: 80.24 },
          unit_size: null,
          rent: null,
          tenure: null,
          status: 'active',
          attractiveness: null,
          attributes: {},
        },
      ],
      scores: {
        method: 'weighted_sum',
        sites: [{ rank: 1, site_id: 'site-1', score: 0.7 }],
        effective_weights: {},
        dropped_criteria: [],
        coverage: 1,
      },
    })

    renderRanking()
    const row = await screen.findByText('Anna Salai')
    const rowElement = row.closest('tr') as HTMLElement
    rowElement.focus()
    await user.keyboard('{Enter}')

    await waitFor(() => {
      expect(rowElement).toHaveAttribute('aria-selected', 'true')
    })
  })

  it('exposes the hard-constraint filters', async () => {
    renderRanking()
    const filter = await screen.findByRole('button', { name: /hard constraints/i })
    expect(filter).toBeInTheDocument()
  })
})
