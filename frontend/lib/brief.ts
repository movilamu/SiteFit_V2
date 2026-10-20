import { apiFetch } from './api'
import { getSupabase } from './supabase/client'
import type {
  AcquisitionMode,
  ConstraintBehaviour,
  Importance,
  LevelWeights,
} from './types'

/**
 * The site-selection brief.
 *
 * This is the single source of truth for the workflow: the wizard writes
 * it, the workspace reads it, and the report is generated from it.  It is
 * persisted locally so that an analysis survives a page reload while the
 * server-side project tables are the intended system of record.
 */
export type BriefRequirement = {
  key: string
  label: string
  importance: Importance
  value: number | boolean | string | null
  valueType: 'number' | 'boolean' | 'select'
  unit: string
  minimum: number | null
  maximum: number | null
  options: string[]
  helpText: string
}

export type BriefFacility = {
  key: string
  label: string
  importance: Importance
}

export type BriefParking = {
  minCarSpaces: number | null
  minTwoWheelerSpaces: number | null
  minParkingAreaSqft: number | null
  behaviour: ConstraintBehaviour
  scope: 'site' | 'site_and_catchment'
}

export type BriefBudget = {
  key: string
  label: string
  scope: string
  limit: number | null
  behaviour: 'penalise' | 'hard'
  appliesTo: AcquisitionMode[]
}

export type BriefFinancial = {
  budgets: BriefBudget[]
  /** Budget behaviour applied when a limit is exceeded. */
  budgetBehaviour: 'penalise' | 'hard'
}

export type BriefLocation = {
  mode: 'city' | 'radius' | 'polygon'
  city: string
  radiusKm: number
  center: { latitude: number; longitude: number } | null
  polygon: [number, number][] | null
}

export type Brief = {
  id: string
  name: string
  businessType: string
  acquisitionMode: AcquisitionMode
  location: BriefLocation
  requirements: BriefRequirement[]
  parking: BriefParking
  facilities: BriefFacility[]
  financial: BriefFinancial
  weights: LevelWeights
  aggregationMethod: string
  /** Set once the user has explicitly confirmed the requirements. */
  confirmedAt: string | null
  notes: string
  createdAt: string
  updatedAt: string
}

export const DEFAULT_PARKING: BriefParking = {
  minCarSpaces: null,
  minTwoWheelerSpaces: null,
  minParkingAreaSqft: null,
  behaviour: 'preference',
  scope: 'site',
}

export const DEFAULT_FINANCIAL: BriefFinancial = {
  budgets: [],
  budgetBehaviour: 'penalise',
}

export const DEFAULT_LOCATION: BriefLocation = {
  mode: 'city',
  city: '',
  radiusKm: 5,
  center: null,
  polygon: null,
}

export function createBrief(name = 'Untitled analysis'): Brief {
  const now = new Date().toISOString()
  return {
    id: `brief_${Date.now().toString(36)}_${Math.random().toString(36).slice(2, 8)}`,
    name,
    businessType: '',
    acquisitionMode: 'either',
    location: { ...DEFAULT_LOCATION },
    requirements: [],
    parking: { ...DEFAULT_PARKING },
    facilities: [],
    financial: { budgets: [], budgetBehaviour: 'penalise' },
    weights: { category_weights: null, leaf_weights: null },
    aggregationMethod: 'weighted_sum',
    confirmedAt: null,
    notes: '',
    createdAt: now,
    updatedAt: now,
  }
}

// ---------------------------------------------------------------------------
// Requirement payload for the API
// ---------------------------------------------------------------------------

/**
 * Convert the brief into the requirement block the deterministic
 * evaluation endpoints expect.
 */
export function toRequirementPayload(brief: Brief): Record<string, unknown> {
  return {
    acquisition_mode: brief.acquisitionMode,
    parking: {
      min_car_spaces: brief.parking.minCarSpaces,
      min_two_wheeler_spaces: brief.parking.minTwoWheelerSpaces,
      min_parking_area_sqft: brief.parking.minParkingAreaSqft,
      behaviour: brief.parking.behaviour,
      scope: brief.parking.scope,
    },
    facilities: brief.facilities.map((facility) => ({
      key: facility.key,
      label: facility.label,
      importance: facility.importance,
    })),
    business_requirements: brief.requirements.map((requirement) => ({
      key: requirement.key,
      label: requirement.label,
      importance: requirement.importance,
      value: requirement.value,
      value_type: requirement.valueType,
    })),
    financial: {
      acquisition_mode: brief.acquisitionMode,
      budget_behaviour: brief.financial.budgetBehaviour,
      budgets: brief.financial.budgets
        .filter((budget) => budget.limit !== null)
        .map((budget) => ({
          key: budget.key,
          label: budget.label,
          limit: budget.limit,
          behaviour: budget.behaviour,
          scope: budget.scope,
        })),
    },
  }
}

// ---------------------------------------------------------------------------
// Local persistence
// ---------------------------------------------------------------------------

const STORAGE_KEY = 'retail-site-intelligence.briefs.v2'

type StoredBriefs = Record<string, Brief>

function readStorage(): StoredBriefs {
  if (typeof window === 'undefined') return {}
  try {
    const raw = window.localStorage.getItem(STORAGE_KEY)
    if (!raw) return {}
    const parsed = JSON.parse(raw) as StoredBriefs
    return typeof parsed === 'object' && parsed !== null ? parsed : {}
  } catch {
    return {}
  }
}

function writeStorage(briefs: StoredBriefs): void {
  if (typeof window === 'undefined') return
  try {
    window.localStorage.setItem(STORAGE_KEY, JSON.stringify(briefs))
  } catch {
    // Storage may be unavailable (private browsing, quota). The session
    // still works; it simply will not survive a reload.
  }
}

export function loadBriefs(): Brief[] {
  return Object.values(readStorage()).sort((a, b) => b.updatedAt.localeCompare(a.updatedAt))
}

export function loadBrief(id: string): Brief | null {
  return readStorage()[id] ?? null
}

export function saveBrief(brief: Brief): Brief {
  const next = { ...brief, updatedAt: new Date().toISOString() }
  const briefs = readStorage()
  briefs[next.id] = next
  writeStorage(briefs)
  return next
}

export function deleteBrief(id: string): void {
  const briefs = readStorage()
  delete briefs[id]
  writeStorage(briefs)
}

// ---------------------------------------------------------------------------
// Project persistence
// ---------------------------------------------------------------------------

/**
 * The brief as the API exchanges it.
 *
 * The API stores an analysis in relational tables and reassembles it on the
 * way out, so the payload is a flat object with snake_case keys.  The brief
 * itself uses camelCase: `toApiPayload` and `fromApiPayload` are the only
 * places where the two shapes meet.
 */
export type ApiProjectPayload = {
  id: string
  name: string
  business_type: string
  acquisition_mode: string
  location: Record<string, unknown>
  requirements: Array<Record<string, unknown>>
  parking: Record<string, unknown>
  facilities: Array<Record<string, unknown>>
  financial: Record<string, unknown>
  weights: Record<string, unknown>
  aggregation_method: string
  criteria_coverage: Record<string, unknown>
  notes: string
  confirmed: boolean
  created_at?: string
  updated_at?: string
}

/** The financial horizon the API stores when the brief does not carry one. */
const DEFAULT_FINANCIAL_HORIZON_MONTHS = 60

/** True when the identifier is a UUID, i.e. an identifier assigned by the API. */
function isServerId(id: string): boolean {
  return /^[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}$/i.test(id)
}

function asString(value: unknown, fallback = ''): string {
  return typeof value === 'string' ? value : fallback
}

function asNullableNumber(value: unknown): number | null {
  return typeof value === 'number' && Number.isFinite(value) ? value : null
}

function asImportance(value: unknown): Importance {
  return value === 'required' || value === 'preferred' ? value : 'not_important'
}

function asValueType(value: unknown): BriefRequirement['valueType'] {
  return value === 'boolean' || value === 'select' ? value : 'number'
}

function asConstraintBehaviour(value: unknown): ConstraintBehaviour {
  return value === 'hard' || value === 'flexible' ? value : 'preference'
}

function asAcquisitionMode(value: unknown): AcquisitionMode {
  return value === 'buy' || value === 'lease' ? value : 'either'
}

function toBriefRequirement(raw: Record<string, unknown>): BriefRequirement {
  const value = raw.value
  return {
    key: asString(raw.key),
    label: asString(raw.label),
    importance: asImportance(raw.importance),
    value:
      typeof value === 'number' || typeof value === 'boolean' || typeof value === 'string'
        ? value
        : null,
    valueType: asValueType(raw.valueType),
    unit: asString(raw.unit),
    minimum: asNullableNumber(raw.minimum),
    maximum: asNullableNumber(raw.maximum),
    options: Array.isArray(raw.options)
      ? raw.options.filter((option): option is string => typeof option === 'string')
      : [],
    helpText: asString(raw.helpText),
  }
}

function toBriefFacility(raw: Record<string, unknown>): BriefFacility {
  return {
    key: asString(raw.key),
    label: asString(raw.label),
    importance: asImportance(raw.importance),
  }
}

function toBriefBudget(raw: Record<string, unknown>): BriefBudget {
  return {
    key: asString(raw.key),
    label: asString(raw.label),
    scope: asString(raw.scope),
    limit: asNullableNumber(raw.limit),
    behaviour: raw.behaviour === 'hard' ? 'hard' : 'penalise',
    appliesTo: Array.isArray(raw.appliesTo)
      ? (raw.appliesTo.filter(
          (mode): mode is AcquisitionMode =>
            mode === 'buy' || mode === 'lease' || mode === 'either',
        ) as AcquisitionMode[])
      : [],
  }
}

function toBriefLocation(raw: Record<string, unknown> | undefined): BriefLocation {
  const source = raw ?? {}
  const center = source.center as
    | { latitude?: unknown; longitude?: unknown }
    | null
    | undefined
  const polygon = Array.isArray(source.polygon) ? source.polygon : null

  return {
    mode:
      source.mode === 'radius' || source.mode === 'polygon' ? source.mode : 'city',
    city: asString(source.city),
    radiusKm:
      typeof source.radiusKm === 'number' && Number.isFinite(source.radiusKm)
        ? source.radiusKm
        : DEFAULT_LOCATION.radiusKm,
    center:
      center &&
      typeof center.latitude === 'number' &&
      typeof center.longitude === 'number'
        ? { latitude: center.latitude, longitude: center.longitude }
        : null,
    polygon: polygon as [number, number][] | null,
  }
}

function toBriefParking(raw: Record<string, unknown> | undefined): BriefParking {
  const source = raw ?? {}
  return {
    minCarSpaces: asNullableNumber(source.minCarSpaces),
    minTwoWheelerSpaces: asNullableNumber(source.minTwoWheelerSpaces),
    minParkingAreaSqft: asNullableNumber(source.minParkingAreaSqft),
    behaviour: asConstraintBehaviour(source.behaviour),
    scope: source.scope === 'site_and_catchment' ? 'site_and_catchment' : 'site',
  }
}

function toBriefFinancial(raw: Record<string, unknown> | undefined): BriefFinancial {
  const source = raw ?? {}
  return {
    budgets: Array.isArray(source.budgets)
      ? source.budgets.map((budget) =>
          toBriefBudget(
            (budget ?? {}) as Record<string, unknown>,
          ),
        )
      : [],
    budgetBehaviour: source.budgetBehaviour === 'hard' ? 'hard' : 'penalise',
  }
}

function toBriefWeights(raw: Record<string, unknown> | undefined): LevelWeights {
  const source = raw ?? {}
  const categoryWeights = source.category_weights
  const leafWeights = source.leaf_weights
  return {
    category_weights:
      categoryWeights && typeof categoryWeights === 'object'
        ? (categoryWeights as Record<string, number>)
        : null,
    leaf_weights:
      leafWeights && typeof leafWeights === 'object'
        ? (leafWeights as Record<string, Record<string, number>>)
        : null,
  }
}

/**
 * Convert the brief into the payload the projects API expects.
 */
export function toApiPayload(brief: Brief): ApiProjectPayload {
  return {
    id: brief.id,
    name: brief.name,
    business_type: brief.businessType,
    acquisition_mode: brief.acquisitionMode,
    location: { ...brief.location },
    requirements: brief.requirements.map((requirement) => ({
      key: requirement.key,
      label: requirement.label,
      importance: requirement.importance,
      value: requirement.value,
      valueType: requirement.valueType,
      unit: requirement.unit,
      minimum: requirement.minimum,
      maximum: requirement.maximum,
      options: [...requirement.options],
      helpText: requirement.helpText,
    })),
    parking: {
      minCarSpaces: brief.parking.minCarSpaces,
      minTwoWheelerSpaces: brief.parking.minTwoWheelerSpaces,
      minParkingAreaSqft: brief.parking.minParkingAreaSqft,
      behaviour: brief.parking.behaviour,
      scope: brief.parking.scope,
    },
    facilities: brief.facilities.map((facility) => ({
      key: facility.key,
      label: facility.label,
      importance: facility.importance,
    })),
    financial: {
      budgets: brief.financial.budgets.map((budget) => ({ ...budget })),
      budgetBehaviour: brief.financial.budgetBehaviour,
      horizonMonths: DEFAULT_FINANCIAL_HORIZON_MONTHS,
    },
    weights: {
      category_weights: brief.weights.category_weights,
      leaf_weights: brief.weights.leaf_weights,
    },
    aggregation_method: brief.aggregationMethod,
    criteria_coverage: {},
    notes: brief.notes,
    confirmed: brief.confirmedAt !== null,
  }
}

/**
 * Convert a payload returned by the API back into a brief.
 */
export function fromApiPayload(payload: ApiProjectPayload): Brief {
  const now = new Date().toISOString()
  return {
    id: payload.id,
    name: payload.name || 'Untitled analysis',
    businessType: payload.business_type ?? '',
    acquisitionMode: asAcquisitionMode(payload.acquisition_mode),
    location: toBriefLocation(payload.location),
    requirements: (payload.requirements ?? []).map((requirement) =>
      toBriefRequirement((requirement ?? {}) as Record<string, unknown>),
    ),
    parking: toBriefParking(payload.parking),
    facilities: (payload.facilities ?? []).map((facility) =>
      toBriefFacility((facility ?? {}) as Record<string, unknown>),
    ),
    financial: toBriefFinancial(payload.financial),
    weights: toBriefWeights(payload.weights),
    aggregationMethod: payload.aggregation_method || 'weighted_sum',
    confirmedAt: payload.confirmed ? now : null,
    notes: payload.notes ?? '',
    createdAt: payload.created_at ?? now,
    updatedAt: payload.updated_at ?? now,
  }
}

// ---------------------------------------------------------------------------
// Store abstraction
// ---------------------------------------------------------------------------

/**
 * Where the analyses live.
 *
 * The API is the system of record once Supabase is configured; the browser
 * is the fallback for a local, unconfigured deployment.
 */
type ProjectStore = {
  list(): Promise<Brief[]>
  get(id: string): Promise<Brief | null>
  save(brief: Brief): Promise<Brief>
  remove(id: string): Promise<void>
}

const remoteStore: ProjectStore = {
  async list() {
    const response = await apiFetch<{ projects?: ApiProjectPayload[] }>('/projects')
    return (response.projects ?? []).map(fromApiPayload)
  },
  async get(id) {
    const response = await apiFetch<{ project?: ApiProjectPayload }>(
      `/projects/${encodeURIComponent(id)}`,
    )
    return response.project ? fromApiPayload(response.project) : null
  },
  async save(brief) {
    const payload = toApiPayload(brief)
    // A brief that already carries a server identifier is an update; a
    // freshly created one is a new analysis and the API assigns the id.
    const response = isServerId(brief.id)
      ? await apiFetch<{ project?: ApiProjectPayload }>(
          `/projects/${encodeURIComponent(brief.id)}`,
          { method: 'PATCH', body: payload },
        )
      : await apiFetch<{ project?: ApiProjectPayload }>('/projects', {
          method: 'POST',
          body: payload,
        })
    return response.project ? fromApiPayload(response.project) : brief
  },
  async remove(id) {
    await apiFetch<void>(`/projects/${encodeURIComponent(id)}`, {
      method: 'DELETE',
    })
  },
}

const localStore: ProjectStore = {
  async list() {
    return loadBriefs()
  },
  async get(id) {
    return loadBrief(id)
  },
  async save(brief) {
    return saveBrief(brief)
  },
  async remove(id) {
    deleteBrief(id)
  },
}

let warnedAboutLocalStorage = false

/** Warn once that the analyses are only kept in this browser. */
function warnAboutLocalStorage(): void {
  if (warnedAboutLocalStorage) return
  warnedAboutLocalStorage = true
  console.warn(
    '[brief] Supabase is not configured or no session is available, so this ' +
      'analysis is stored in this browser only. It is not shared between ' +
      'users or devices and it is lost when the browser data is cleared.',
  )
}

/**
 * Pick the store to use.
 *
 * The API is used when Supabase is configured *and* a session exists; the
 * browser is used otherwise.
 */
async function resolveStore(): Promise<ProjectStore> {
  const supabase = getSupabase()
  if (supabase) {
    try {
      const { data } = await supabase.auth.getSession()
      if (data.session) return remoteStore
    } catch {
      // The session could not be read: fall back to the browser.
    }
  }
  warnAboutLocalStorage()
  return localStore
}

/**
 * Every analysis owned by the signed-in user.
 *
 * Falls back to the analyses held in this browser when Supabase is not
 * configured or nobody is signed in.
 */
export async function fetchProjects(): Promise<Brief[]> {
  const store = await resolveStore()
  return store.list()
}

/**
 * One analysis.
 *
 * Falls back to the analysis held in this browser when Supabase is not
 * configured or nobody is signed in.
 */
export async function fetchProject(id: string): Promise<Brief | null> {
  const store = await resolveStore()
  return store.get(id)
}

/**
 * Save an analysis.
 *
 * When the API is the system of record the saved analysis is returned, and
 * it carries the identifier the API assigned.  The caller must use the
 * returned brief, because a new analysis receives a new identifier.
 */
export async function persistProject(brief: Brief): Promise<Brief> {
  const store = await resolveStore()
  return store.save(brief)
}

/**
 * Delete an analysis.
 *
 * Falls back to the analysis held in this browser when Supabase is not
 * configured or nobody is signed in.
 */
export async function removeProject(id: string): Promise<void> {
  const store = await resolveStore()
  await store.remove(id)
}
