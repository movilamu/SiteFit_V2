import * as Sentry from '@sentry/nextjs'

import { getSupabase } from './supabase/client'
import type {
  CriteriaTree,
  EvaluateResponse,
  ExplanationResponse,
  ParseResponse,
  PropertySearchResponse,
  PropertySourcesResponse,
  RollupResponse,
  Scenario,
  ScenarioWithRanking,
  ScoreResponse,
  SiteDecompositionResponse,
  SitesListResponse,
  DataQualityResponse,
  CrossMethodAgreement,
  NearTieCluster,
  StabilityRow,
  ThresholdRow,
  BusinessProfile,
  RequirementCatalog,
  BrokerageSearchResponse,
  BrokerageSourcesResponse,
  ReportExportFormatsResponse,
} from './types'

/**
 * The FastAPI origin.
 *
 * Requests are made to same-origin `/api/...` paths, which
 * `next.config.mjs` rewrites to the backend.  The backend URL therefore
 * never reaches the browser and no CORS negotiation is needed in
 * production.
 */
export const API_BASE_URL =
  (typeof process !== 'undefined' && process.env.NEXT_PUBLIC_API_BASE_URL?.replace(/\/+$/, '')) ||
  ''

/** Prefix used for the server-side API proxy. */
export const API_PREFIX = '/api'

export function apiUrl(path: string): string {
  const normalized = path.startsWith('/') ? path : `/${path}`
  return `${API_BASE_URL}${API_PREFIX}${normalized}`
}

/**
 * Parse an API error response and report the failure to Sentry.
 *
 * Only the status, route and message are captured: no site, demographic or
 * cost payload is ever attached to an error report.
 */
export async function readApiError(response: Response, fallback: string): Promise<string> {
  let message = `${fallback} (${response.status})`
  try {
    const body = await response.json()
    if (typeof body?.detail === 'string') {
      message = body.detail
    } else if (Array.isArray(body?.detail)) {
      message = body.detail
        .map((item: { msg?: string }) => item?.msg || JSON.stringify(item))
        .join('; ')
    } else if (body?.detail) {
      message = JSON.stringify(body.detail)
    }
  } catch {
    // Keep the fallback message.
  }

  Sentry.captureMessage(`API Error: ${response.status} ${response.url || fallback}`, {
    level: 'error',
    extra: {
      status: response.status,
      statusText: response.statusText,
      url: response.url,
      detail: message,
    },
  })

  return message
}

/** Capture an exception raised while talking to the API. */
export function captureApiError(error: unknown, context?: Record<string, unknown>): void {
  Sentry.captureException(error, { extra: context })
}

type RequestOptions = Omit<RequestInit, 'body'> & { body?: unknown }

/**
 * Read the Supabase access token of the current browser session.
 *
 * `null` is returned when Supabase is not configured, when nobody is signed
 * in, or when the request is made on the server.  The user-owned API
 * endpoints reject an anonymous request, so the token is what turns the
 * call into an authenticated one.
 */
async function resolveAccessToken(): Promise<string | null> {
  if (typeof window === 'undefined') return null
  const supabase = getSupabase()
  if (!supabase) return null
  try {
    const { data } = await supabase.auth.getSession()
    return data.session?.access_token ?? null
  } catch {
    return null
  }
}

/**
 * Perform a JSON request against the API.
 *
 * The Supabase access token is sent as a bearer token whenever a session
 * exists, so the API can verify the caller and scope the data to the
 * signed-in user.
 *
 * Throws an `Error` carrying the server's message so that every caller
 * can present the same actionable text.
 */
export async function apiFetch<T>(path: string, options: RequestOptions = {}): Promise<T> {
  const { body, headers, ...rest } = options
  const accessToken = await resolveAccessToken()

  const response = await fetch(apiUrl(path), {
    ...rest,
    headers: {
      Accept: 'application/json',
      ...(body !== undefined ? { 'Content-Type': 'application/json' } : {}),
      ...(accessToken ? { Authorization: `Bearer ${accessToken}` } : {}),
      ...(headers as Record<string, string> | undefined),
    },
    body: body !== undefined ? JSON.stringify(body) : undefined,
  })

  if (!response.ok) {
    throw new Error(await readApiError(response, `Request to ${path} failed`))
  }

  if (response.status === 204) {
    return undefined as T
  }

  return (await response.json()) as T
}

/**
 * Perform a request that returns a file rather than JSON.
 *
 * The report exports are downloaded as a blob so that the browser can save
 * the artefact under a sensible name without navigating away from the
 * workspace, and so the response never has to be parsed as JSON.
 */
export async function apiFetchBlob(path: string, options: RequestOptions = {}): Promise<Blob> {
  const { body, headers, ...rest } = options
  const accessToken = await resolveAccessToken()

  const response = await fetch(apiUrl(path), {
    ...rest,
    headers: {
      Accept: '*/*',
      ...(body !== undefined ? { 'Content-Type': 'application/json' } : {}),
      ...(accessToken ? { Authorization: `Bearer ${accessToken}` } : {}),
      ...(headers as Record<string, string> | undefined),
    },
    body: body !== undefined ? JSON.stringify(body) : undefined,
  })

  if (!response.ok) {
    throw new Error(await readApiError(response, `Request to ${path} failed`))
  }

  return response.blob()
}

// ---------------------------------------------------------------------------
// Endpoints
// ---------------------------------------------------------------------------

export const fetchCriteria = () => apiFetch<CriteriaTree>('/criteria')

export const fetchRequirementCatalog = () => apiFetch<RequirementCatalog>('/requirements/catalog')

export const fetchBusinessProfile = (businessType: string) =>
  apiFetch<BusinessProfile>(`/requirements/profile/${encodeURIComponent(businessType)}`)

export const fetchSites = (query = '') =>
  apiFetch<SitesListResponse>(query ? `/sites?${query}` : '/sites')

export type ScoreRequest = {
  weights?: Record<string, number>
  level_weights?: { category_weights: Record<string, number> | null; leaf_weights: Record<string, Record<string, number>> | null }
  method: string
}

export const fetchScores = (body: ScoreRequest) =>
  apiFetch<ScoreResponse>('/score', { method: 'POST', body })

export const fetchDecomposition = (siteId: string, weights: Record<string, number>, method: string) => {
  const params = new URLSearchParams({ weights: JSON.stringify(weights), method })
  return apiFetch<SiteDecompositionResponse>(
    `/sites/${encodeURIComponent(siteId)}/decomposition?${params.toString()}`,
  )
}

export const fetchRollup = (body: {
  category_weights?: Record<string, number> | null
  leaf_weights?: Record<string, Record<string, number>> | null
}) => apiFetch<RollupResponse>('/criteria/rollup', { method: 'POST', body })

export const fetchEvaluate = (body: {
  requirements: Record<string, unknown>
  penalty_rate?: number
  site_ids?: string[]
}) => apiFetch<EvaluateResponse>('/requirements/evaluate', { method: 'POST', body })

export const fetchParseRequirements = (body: { description: string; business_type?: string }) =>
  apiFetch<ParseResponse>('/requirements/parse', { method: 'POST', body })

export const fetchExplanation = (body: {
  site_id: string
  weights?: Record<string, number>
  level_weights?: { category_weights: Record<string, number> | null; leaf_weights: Record<string, Record<string, number>> | null }
  method: string
  requirements?: Record<string, unknown>
  penalty_rate?: number
  compare_with?: string[]
  include_stability?: boolean
}) => apiFetch<ExplanationResponse>('/explanations/site', { method: 'POST', body })

export const fetchPropertySources = () =>
  apiFetch<PropertySourcesResponse>('/properties/sources')

export const fetchPropertySearch = (body: {
  site_ids: string[]
  radius_m?: number
  business_type?: string | null
  acquisition_mode?: string
  limit_per_site?: number
}) => apiFetch<PropertySearchResponse>('/properties/search', { method: 'POST', body })

export const fetchDataQuality = () => apiFetch<DataQualityResponse>('/data-quality')

export const fetchThresholds = (weights: Record<string, number>, method: string) => {
  const params = new URLSearchParams({ weights: JSON.stringify(weights), method })
  return apiFetch<ThresholdRow[]>(`/sensitivity/thresholds?${params.toString()}`)
}

export const fetchStability = (weights: Record<string, number>, method: string) => {
  const params = newURLSearchParamsSafe({ weights: JSON.stringify(weights), method })
  return apiFetch<StabilityRow[]>(`/sensitivity/stability?${params.toString()}`)
}

export const fetchNearTies = (weights: Record<string, number>, method: string) => {
  const params = new URLSearchParams({ weights: JSON.stringify(weights), method })
  return apiFetch<NearTieCluster[]>(`/sensitivity/near-ties?${params.toString()}`)
}

export const fetchCrossMethod = (weights: Record<string, number>, method: string) => {
  const params = new URLSearchParams({ weights: JSON.stringify(weights), method })
  return apiFetch<CrossMethodAgreement>(`/sensitivity/cross-method?${params.toString()}`)
}

export const fetchScenarios = () => apiFetch<Scenario[]>('/scenarios')

export const createScenario = (body: {
  name: string
  weight_set: Record<string, number>
  aggregation_method: string
}) => apiFetch<Scenario>('/scenarios', { method: 'POST', body })

export const fetchScenario = (id: number) =>
  apiFetch<ScenarioWithRanking>(`/scenarios/${id}`)

export const fetchScenarioComparison = (ids: number[]) =>
  apiFetch<{ scenarios: Scenario[]; ranking: Record<string, number>[] }>(
    `/scenarios/compare?ids=${ids.join(',')}`,
  )

export const exportRanking = (body: {
  scenario_id?: number
  weight_set?: Record<string, number>
  aggregation_method: string
}) => apiFetch<{ export_id?: string; payload?: unknown; [key: string]: unknown }>('/export', {
  method: 'POST',
  body,
})

export const generateReport = (body: Record<string, unknown>) =>
  apiFetch<Record<string, unknown>>('/reports/generate', { method: 'POST', body })

export const fetchReportExportFormats = () =>
  apiFetch<ReportExportFormatsResponse>('/reports/export/formats')

export const fetchBrokerageSources = () =>
  apiFetch<BrokerageSourcesResponse>('/brokerage/sources')

export const fetchBrokerageSearch = (body: {
  site_ids: string[]
  radius_m?: number
  limit_per_site?: number
}) => {
  const params = new URLSearchParams({
    site_ids: body.site_ids.join(','),
    radius_m: String(body.radius_m ?? 5000),
    limit_per_site: String(body.limit_per_site ?? 10),
  })
  return apiFetch<BrokerageSearchResponse>(`/brokerage/search-sites?${params.toString()}`)
}

/**
 * Small helper so that the sensitivity helpers above read consistently.
 */
function newURLSearchParamsSafe(init: Record<string, string>): URLSearchParams {
  return new URLSearchParams(init)
}
