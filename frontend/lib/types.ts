/**
 * Shared API types.
 *
 * These mirror the FastAPI response models.  Keeping them in one place
 * means a contract change surfaces as a type error rather than as an
 * undefined field at runtime.
 */

// --- Criteria ---------------------------------------------------------------

export type CriterionDirection = 'benefit' | 'cost' | null

export type CriterionNode = {
  key: string
  label: string
  direction: CriterionDirection
  scoring_mode: 'monotonic' | 'target_band'
  target_band: number[] | null
  data_field: string
  data_available: boolean
  notes: string
}

export type SubcategoryNode = {
  key: string
  label: string
  criteria: CriterionNode[]
}

export type CategoryNode = {
  key: string
  label: string
  subcategories: SubcategoryNode[]
}

export type CriteriaTree = {
  categories: CategoryNode[]
  category_keys: string[]
  leaf_keys: string[]
  leaf_count: number
  scorable_leaf_count: number
  notes: string
}

export type LevelWeights = {
  category_weights: Record<string, number> | null
  leaf_weights: Record<string, Record<string, number>> | null
}

export type RollupResponse = {
  leaf_weights: Record<string, number>
  category_weights: Record<string, number>
  breakdown: {
    criterion: string
    label: string
    category: string | null
    weight: number
  }[]
  leaf_keys: string[]
}

// --- Sites ------------------------------------------------------------------

export type SiteCoordinates = {
  latitude: number
  longitude: number
}

export type CandidateSite = {
  site_id: string | number
  name: string | null
  coordinates: SiteCoordinates
  unit_size: number | null
  rent: number | null
  tenure: string | null
  status: string | null
  attractiveness: number | null
  attributes: Record<string, unknown>
}

export type SitesListResponse = {
  count: number
  filters_applied: Record<string, unknown>
  sites: CandidateSite[]
  excluded: { site_identifier: string | number; reasons: string[] }[]
}

export type RankedSite = {
  rank: number
  site_id: string
  score: number
}

export type ScoreResponse = {
  method: string
  sites: RankedSite[]
  effective_weights: Record<string, number>
  dropped_criteria: string[]
  coverage: number
}

export type CriterionDecomposition = {
  criterion: string
  label: string
  category: string
  normalized_value: number
  weight: number
  contribution: number
  direction: CriterionDirection
}

export type SiteDecompositionResponse = {
  site_id: string
  method: string
  total_score: number
  criteria: CriterionDecomposition[]
  rank: number | null
  dropped_criteria: string[]
  coverage: number
}

// --- Requirements -----------------------------------------------------------

export type ConstraintBehaviour = 'hard' | 'preference' | 'flexible'

export type Importance = 'required' | 'preferred' | 'not_important'

export type AcquisitionMode = 'buy' | 'lease' | 'either'

export type BusinessTypeCatalogEntry = {
  key: string
  label: string
  description: string
  acquisition_modes: AcquisitionMode[]
  requirements: Record<string, Importance>
  required_facilities: string[]
  preferred_facilities: string[]
  typical_unit_size_sqft: number[]
  is_custom: boolean
}

export type RequirementDefinition = {
  key: string
  label: string
  value_type: 'number' | 'boolean' | 'select'
  unit: string
  minimum: number | null
  maximum: number | null
  options: string[]
  default: unknown
  help_text: string
  site_attributes: string[]
}

export type FacilityDefinition = {
  key: string
  label: string
  category: string
  site_attributes: string[]
}

export type RequirementCatalog = {
  business_types: BusinessTypeCatalogEntry[]
  requirements: RequirementDefinition[]
  facilities: FacilityDefinition[]
  constraint_behaviours: { key: ConstraintBehaviour; label: string; description: string }[]
  acquisition_modes: { key: AcquisitionMode; label: string; description: string }[]
  budget_definitions: {
    key: string
    label: string
    scope: string
    applies_to: AcquisitionMode[]
  }[]
  parking_fields: { key: string; label: string; unit: string }[]
  default_penalty_rate: number
}

export type BusinessProfileEntry = {
  key: string
  label: string
  importance: Importance
  value_type: 'number' | 'boolean' | 'select'
  unit: string
  minimum: number | null
  maximum: number | null
  options: string[]
  default: unknown
  help_text: string
}

export type BusinessProfile = {
  business_type: string
  requirements: BusinessProfileEntry[]
}

export type CheckStatus = 'pass' | 'fail' | 'warning' | 'unknown' | 'not_applicable'

export type CheckResult = {
  key: string
  label: string
  status: CheckStatus
  importance: Importance
  detail: string
  observed: unknown
  expected: unknown
  source: string | null
}

export type SectionEvaluation = {
  section: string
  behaviour: ConstraintBehaviour
  checks: CheckResult[]
  required_total: number
  required_met: number
  required_failed: number
  required_unknown: number
  preferred_total: number
  preferred_met: number
  preferred_unknown: number
  fit_ratio: number
  status: CheckStatus
}

export type CostProvenance =
  | 'verified_listed'
  | 'user_provided'
  | 'estimated'
  | 'calculated'
  | 'unavailable'

export type CostLine = {
  key: string
  label: string
  amount: number | null
  provenance: CostProvenance
  provenance_label: string
  category: 'acquisition' | 'setup' | 'recurring'
  source: string | null
  note: string
}

export type CostBudgetResult = {
  key: string
  label: string
  limit: number | null
  behaviour: 'penalise' | 'hard'
  scope: string
  status: 'within_budget' | 'over_budget' | 'partially_assessed' | 'not_set'
  observed: number | null
  known_minimum?: number
  headroom: number | null
  detail: string
}

/**
 * The cost of ownership over the configured horizon.
 *
 * The total is only reported when every component is known.  Otherwise the
 * known part is reported as a minimum and the missing components are
 * named, so an incomplete cost picture is never presented as a total.
 */
export type CostOfOwnership = {
  horizon_months: number
  total_cost_of_ownership: number | null
  known_minimum: number
  initial_investment: number | null
  recurring_total: number | null
  is_complete: boolean
  missing: string[]
}

export type CostAssessment = {
  site_id: string
  acquisition_mode: AcquisitionMode
  lines: CostLine[]
  budget_results: CostBudgetResult[]
  totals: {
    acquisition_total: number | null
    setup_total: number | null
    recurring_monthly_total: number | null
    recurring_annual_total: number | null
    initial_investment_total: number | null
    known_minimum_initial_investment: number
    is_complete: boolean
  }
  missing_components: string[]
  notes: string[]
  cost_of_ownership: CostOfOwnership | null
}

export type SiteRequirementEvaluation = {
  site_id: string
  eligible: boolean
  hard_failures: CheckResult[]
  parking: SectionEvaluation | null
  facilities: SectionEvaluation | null
  business_requirements: SectionEvaluation | null
  cost: CostAssessment | null
  fit_ratio: number
  fit_factor: number
  notes: string[]
}

export type EvaluateResponse = {
  sites: {
    site_id: string
    name: string | null
    eligible: boolean
    fit_ratio: number
    fit_factor: number
    evaluation: SiteRequirementEvaluation
  }[]
  evaluated_count: number
  eligible_count: number
  excluded_count: number
  penalty_rate: number
  notes: string[]
}

export type ParsedRequirement = {
  key: string
  label: string
  importance: Importance
  value: unknown
  unit: string
  value_type: string
  confidence: string
  source_quote: string
}

export type ParseResponse = {
  interpretation_summary: string
  business_type: string | null
  acquisition_mode: AcquisitionMode
  requirements: ParsedRequirement[]
  parking: Record<string, unknown>
  facilities: { key: string; label: string; importance: string }[]
  financial: Record<string, unknown>
  warnings: string[]
  requires_confirmation: boolean
  provider: string | null
}

// --- Explanations -----------------------------------------------------------

export type StrengthFactor = {
  criterion: string
  label: string
  category: string
  focal_value: number
  reference_value: number | null
  focal_weight: number
  contribution_delta: number
  advantage: number
  direction: CriterionDirection
}

export type ExplanationResponse = {
  site_id: string
  site_name: string | null
  headline: string
  rank: number | null
  total_sites: number
  base_score: number
  adjusted_score: number | null
  fit_factor: number
  summary: string
  comparison_sentence: string
  strengths: StrengthFactor[]
  weaknesses: StrengthFactor[]
  requirements: { business: string; parking: string; facilities: string }
  cost: string
  caveats: string[]
  coverage: number
  dropped_criteria: string[]
  eligible: boolean
  hard_failures: CheckResult[]
}

// --- Property intelligence --------------------------------------------------

export type PropertyOpportunity = {
  source_key: string
  source_label: string
  publisher: string
  title: string
  source_url: string | null
  location: string
  latitude: number | null
  longitude: number | null
  distance_m: number | null
  property_type: string
  area_sqft: number | null
  purchase_price: number | null
  monthly_rent: number | null
  security_deposit: number | null
  parking_spaces: number | null
  facilities: string
  broker_name: string
  broker_contact: string
  listed_at: string | null
  retrieved_at: string
  price_provenance: string
  verification_status: string
}

export type PropertySourceStatus = {
  key: string
  label: string
  publisher: string
  status: string
  message: string
  retrieved_at: string
  opportunity_count: number
  /** Present for a manual source: the direct link to search the portal. */
  search_url?: string | null
}

export type PropertySearchResult = {
  site_id: string
  site_name: string | null
  latitude?: number
  longitude?: number
  status: string
  message: string
  sources: PropertySourceStatus[]
  opportunities: PropertyOpportunity[]
}

export type PropertySearchResponse = {
  sites: PropertySearchResult[]
  opportunity_count: number
  source_status_summary: {
    key: string
    label: string
    publisher: string
    status: string
    message: string
    checked_sites: number
  }[]
  any_source_available: boolean
  disclaimer: string
}

export type PropertySourcesResponse = {
  sources: {
    key: string
    label: string
    publisher: string
    homepage_url: string | null
    kind: string
    description: string
    enabled: boolean
    status: string
    reason: string
  }[]
  enabled_count: number
  notes: string[]
}

// --- Data quality -----------------------------------------------------------

export type DataQualityResponse = {
  generated_at: string | null
  sources: {
    table: string
    label: string
    origin: string
    available: boolean
    has_rows: boolean
    note: string
  }[]
  coverage: Record<string, any>
  criteria: {
    criterion: string
    label: string
    category: string
    direction: CriterionDirection
    scoring_mode: string
    data_available: boolean
    marked_pending: boolean
    status: string
  }[]
  backtesting: {
    available: boolean
    method: string
    note: string
  }
  limitations: {
    id: string
    severity: string
    title: string
    detail: string
  }[]
  summary: {
    criteria_coverage: number
    criteria_coverage_grade: string
    usable_source_count: number
    total_source_count: number
    matrix_available: boolean
    backtest_available: boolean
    overall_grade: string
    grading_rule: string
  }
}

// --- Sensitivity ------------------------------------------------------------

export type ThresholdRow = {
  criterion: string
  current_weight: number
  current_top_site: string
  direction: 'increase' | 'decrease' | null
  threshold_weight: number | null
  delta: number | null
  new_top_site: string | null
  method: string
}

export type StabilityRow = {
  site_id: string
  current_rank: number
  stability_percentage: number
  stability_criterion: string
  top_n?: number
}

export type NearTieCluster = {
  cluster_rank: number
  site_ids: string[]
  scores: number[]
  score_range: number
}

export type CrossMethodAgreement = {
  ranks: Record<string, number[]>
  pairwise_spearman: Record<string, number>
  overall_agreement: number
  flagged_sites: {
    site_id: string
    ranks: Record<string, number>
    rank_spread: number
  }[]
}

// --- Scenarios --------------------------------------------------------------

export type Scenario = {
  scenario_id: number
  name: string
  weight_set: Record<string, number>
  aggregation_method: string
  created_at: string
  updated_at: string
}

export type ScenarioWithRanking = Scenario & {
  ranking: { rank: number; site_id: string; score: number }[]
}

// --- Reporting ---------------------------------------------------------------

export type ReportExportFormatKey = 'pdf' | 'csv' | 'xlsx' | 'json'

export type ReportExportFormat = {
  key: ReportExportFormatKey
  label: string
  media_type: string
  description: string
}

export type ReportExportFormatsResponse = {
  formats: ReportExportFormat[]
}

// --- Brokerage intelligence --------------------------------------------------

export type BrokerageSourceKind = 'automated' | 'manual'

export type BrokerageSource = {
  key: string
  label: string
  publisher: string
  kind: BrokerageSourceKind
  enabled: boolean
  status: string
  description: string
}

export type BrokerageSourcesResponse = {
  sources: BrokerageSource[]
  automated_count: number
  manual_count: number
  notes: string[]
}

export type BrokerageOpportunity = {
  source_key: string
  source_label: string
  publisher: string
  name: string
  service_area: string
  website: string
  phone: string
  email: string
  source_url: string
  listing_count: number
  distance_m: number | null
  retrieved_at: string
  source_date: string | null
  source_status: string
  source_status_label: string
  kind: string
  notes: string
}

export type BrokerageSourceStatus = {
  source_key: string
  source_label: string
  publisher: string
  status: string
  status_label: string
  message: string
  retrieved_at: string
  kind: string
  /** Present for a manual source: the direct link to search the portal. */
  search_url: string | null
  opportunity_count: number
  opportunities: BrokerageOpportunity[]
}

export type BrokerageSiteResult = {
  site_id: string
  site_name: string | null
  status: string
  message: string
  sources: BrokerageSourceStatus[]
  opportunities: BrokerageOpportunity[]
}

export type BrokerageSearchResponse = {
  sites: BrokerageSiteResult[]
  opportunity_count: number
  disclaimer: string
}
