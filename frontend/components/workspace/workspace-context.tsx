'use client'

import * as React from 'react'

import { fetchCriteria, fetchEvaluate, fetchScores } from '@/lib/api'
import { equalCategoryWeights, equalLeafWeights } from '@/lib/criteria'
import { type Brief, toRequirementPayload } from '@/lib/brief'
import type {
  CandidateSite,
  CriteriaTree,
  EvaluateResponse,
  LevelWeights,
  ScoreResponse,
} from '@/lib/types'

import {
  fetchFilteredSites,
  type ConstraintFilters,
} from './constraint-filter'

export type WorkspaceState = {
  brief: Brief
  criteria: CriteriaTree | null
  sites: CandidateSite[]
  siteById: Record<string, CandidateSite>
  weights: LevelWeights
  method: string
  scores: ScoreResponse | null
  evaluation: EvaluateResponse | null
  selectedSiteId: string | null
  loadingSites: boolean
  loadingScores: boolean
  sitesError: string | null
  scoresError: string | null
  /** Sites removed by the hard-constraint filters, with the reasons. */
  excludedByFilter: { site_id: string; reasons: string[] }[]
  filtersActive: boolean
  setWeights: (weights: LevelWeights) => void
  setMethod: (method: string) => void
  setSelectedSiteId: (id: string | null) => void
  refreshScores: () => void
  applyFilters: (filters: ConstraintFilters) => Promise<void>
  resetFilters: () => void
  rankOf: (siteId: string) => number | null
  scoreOf: (siteId: string) => number | null
  eligibleIds: Set<string>
}

const WorkspaceContext = React.createContext<WorkspaceState | null>(null)

export function WorkspaceProvider({
  brief,
  children,
}: {
  brief: Brief
  children: React.ReactNode
}) {
  const [criteria, setCriteria] = React.useState<CriteriaTree | null>(null)
  const [sites, setSites] = React.useState<CandidateSite[]>([])
  const [weights, setWeightsState] = React.useState<LevelWeights>(brief.weights)
  const [method, setMethod] = React.useState(brief.aggregationMethod)
  const [scores, setScores] = React.useState<ScoreResponse | null>(null)
  const [evaluation, setEvaluation] = React.useState<EvaluateResponse | null>(null)
  const [selectedSiteId, setSelectedSiteId] = React.useState<string | null>(null)

  const [loadingSites, setLoadingSites] = React.useState(true)
  const [loadingScores, setLoadingScores] = React.useState(false)
  const [sitesError, setSitesError] = React.useState<string | null>(null)
  const [scoresError, setScoresError] = React.useState<string | null>(null)
  const [refreshToken, setRefreshToken] = React.useState(0)
  const [excludedByFilter, setExcludedByFilter] = React.useState<
    { site_id: string; reasons: string[] }[]
  >([])
  const [filtersActive, setFiltersActive] = React.useState(false)

  // --- Static inputs ------------------------------------------------
  React.useEffect(() => {
    let cancelled = false
    Promise.all([fetchCriteria()])
      .then(([tree]) => {
        if (cancelled) return
        setCriteria(tree)
        setWeightsState((current) => {
          if (current.category_weights) return current
          return {
            category_weights: equalCategoryWeights(tree),
            leaf_weights: equalLeafWeights(tree),
          }
        })
      })
      .catch((err: unknown) => {
        if (!cancelled) {
          setSitesError(
            err instanceof Error ? err.message : 'The criteria hierarchy could not be loaded.',
          )
        }
      })
    return () => {
      cancelled = true
    }
  }, [])

  React.useEffect(() => {
    let cancelled = false
    setLoadingSites(true)
    setSitesError(null)
    import('@/lib/api')
      .then(({ fetchSites }) => fetchSites())
      .then((response) => {
        if (cancelled) return
        setSites(response.sites ?? [])
        setSelectedSiteId((current) => current ?? (response.sites?.[0] ? String(response.sites[0].site_id) : null))
      })
      .catch((err: unknown) => {
        if (!cancelled) {
          setSitesError(
            err instanceof Error
              ? err.message
              : 'The candidate site inventory could not be loaded.',
          )
        }
      })
      .finally(() => {
        if (!cancelled) setLoadingSites(false)
      })
    return () => {
      cancelled = true
    }
  }, [refreshToken])

  // --- Scoring ------------------------------------------------------
  const scoreRequest = React.useMemo(() => {
    if (!weights.category_weights) return null
    return {
      level_weights: {
        category_weights: weights.category_weights,
        leaf_weights: weights.leaf_weights ?? null,
      },
      method,
    }
  }, [weights, method])

  React.useEffect(() => {
    if (!scoreRequest) return
    let cancelled = false
    setLoadingScores(true)
    setScoresError(null)

    fetchScores(scoreRequest)
      .then((response) => {
        if (!cancelled) setScores(response)
      })
      .catch((err: unknown) => {
        if (!cancelled) {
          setScoresError(
            err instanceof Error ? err.message : 'The ranking could not be calculated.',
          )
        }
      })
      .finally(() => {
        if (!cancelled) setLoadingScores(false)
      })

    return () => {
      cancelled = true
    }
  }, [scoreRequest, refreshToken])

  // --- Requirement evaluation ---------------------------------------
  const requirementPayload = React.useMemo(
    () => toRequirementPayload(brief),
    [brief],
  )

  React.useEffect(() => {
    if (!brief.confirmedAt) return
    let cancelled = false
    fetchEvaluate({ requirements: requirementPayload, penalty_rate: 0.25 })
      .then((response) => {
        if (!cancelled) setEvaluation(response)
      })
      .catch(() => {
        // The evaluation is advisory: a failure must not blank the ranking.
        if (!cancelled) setEvaluation(null)
      })
    return () => {
      cancelled = true
    }
  }, [requirementPayload, brief.confirmedAt, refreshToken])

  const applyFilters = React.useCallback(async (filters: ConstraintFilters) => {
    const response = await fetchFilteredSites(filters)
    setSites(response.sites ?? [])
    setExcludedByFilter(
      (response.excluded ?? []).map((entry) => ({
        site_id: String(entry.site_identifier),
        reasons: entry.reasons ?? [],
      })),
    )
    setFiltersActive(true)
    setSelectedSiteId((current) => {
      if (current && (response.sites ?? []).some((site) => String(site.site_id) === current)) {
        return current
      }
      const first = response.sites?.[0]
      return first ? String(first.site_id) : null
    })
  }, [])

  const resetFilters = React.useCallback(() => {
    setExcludedByFilter([])
    setFiltersActive(false)
    setRefreshToken((value) => value + 1)
  }, [])

  const siteById = React.useMemo(() => {
    const map: Record<string, CandidateSite> = {}
    for (const site of sites) {
      map[String(site.site_id)] = site
    }
    return map
  }, [sites])

  const rankById = React.useMemo(() => {
    const map: Record<string, number> = {}
    for (const row of scores?.sites ?? []) {
      map[String(row.site_id)] = row.rank
    }
    return map
  }, [scores])

  const scoreById = React.useMemo(() => {
    const map: Record<string, number> = {}
    for (const row of scores?.sites ?? []) {
      map[String(row.site_id)] = row.score
    }
    return map
  }, [scores])

  const eligibleIds = React.useMemo(() => {
    const set = new Set<string>()
    for (const site of evaluation?.sites ?? []) {
      if (site.eligible) set.add(site.site_id)
    }
    return set
  }, [evaluation])

  const value = React.useMemo<WorkspaceState>(
    () => ({
      brief,
      criteria,
      sites,
      siteById,
      weights,
      method,
      scores,
      evaluation,
      selectedSiteId,
      loadingSites,
      loadingScores,
      sitesError,
      scoresError,
      excludedByFilter,
      filtersActive,
      setWeights: setWeightsState,
      setMethod,
      setSelectedSiteId,
      refreshScores: () => setRefreshToken((value) => value + 1),
      applyFilters,
      resetFilters,
      rankOf: (siteId) => rankById[siteId] ?? null,
      scoreOf: (siteId) => scoreById[siteId] ?? null,
      eligibleIds,
    }),
    [
      brief,
      criteria,
      sites,
      siteById,
      weights,
      method,
      scores,
      evaluation,
      selectedSiteId,
      loadingSites,
      loadingScores,
      sitesError,
      scoresError,
      rankById,
      scoreById,
      eligibleIds,
      excludedByFilter,
      filtersActive,
      applyFilters,
      resetFilters,
    ],
  )

  return <WorkspaceContext.Provider value={value}>{children}</WorkspaceContext.Provider>
}

export function useWorkspace(): WorkspaceState {
  const context = React.useContext(WorkspaceContext)
  if (!context) {
    throw new Error('useWorkspace must be used inside a WorkspaceProvider.')
  }
  return context
}
