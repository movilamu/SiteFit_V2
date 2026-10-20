import type {
  CategoryNode,
  CriteriaTree,
  Importance,
  LevelWeights,
} from './types'

/**
 * Helpers for working with the criteria hierarchy on the client.
 *
 * The hierarchy itself always comes from the API (`GET /criteria`).  These
 * helpers only read and reshape it; they never invent criteria.
 */

/** All categories in tree order. */
export function categories(tree: CriteriaTree | null): CategoryNode[] {
  return tree?.categories ?? []
}

/** All leaf criteria of a category, flattened. */
export function leavesOfCategory(category: CategoryNode) {
  return category.subcategories.flatMap((subcategory) => subcategory.criteria)
}

/** A map of leaf key to owning category key. */
export function categoryByLeaf(tree: CriteriaTree | null): Record<string, string> {
  const map: Record<string, string> = {}
  for (const category of categories(tree)) {
    for (const leaf of leavesOfCategory(category)) {
      map[leaf.key] = category.key
    }
  }
  return map
}

/** Equal-weight category weights across every category. */
export function equalCategoryWeights(tree: CriteriaTree | null): Record<string, number> {
  const list = categories(tree)
  if (list.length === 0) return {}
  const weight = 1 / list.length
  return Object.fromEntries(list.map((category) => [category.key, weight]))
}

/** Equal-weight leaf weights within every category. */
export function equalLeafWeights(tree: CriteriaTree | null): Record<string, Record<string, number>> {
  const result: Record<string, Record<string, number>> = {}
  for (const category of categories(tree)) {
    const leaves = leavesOfCategory(category)
    if (leaves.length === 0) continue
    const weight = 1 / leaves.length
    result[category.key] = Object.fromEntries(leaves.map((leaf) => [leaf.key, weight]))
  }
  return result
}

/** Sum of a weight record. */
export function weightSum(weights: Record<string, number>): number {
  return Object.values(weights).reduce((total, value) => total + (Number(value) || 0), 0)
}

/** Normalise a weight record so that it sums to 1. */
export function normalizeWeights(weights: Record<string, number>): Record<string, number> {
  const total = weightSum(weights)
  if (total <= 0) return weights
  return Object.fromEntries(
    Object.entries(weights).map(([key, value]) => [key, (Number(value) || 0) / total]),
  )
}

/**
 * Build the query parameters for the endpoints that take a weight vector
 * as a query string.
 *
 * The weight-passing convention is:
 *   * `POST /score` and the criteria roll-up take a JSON body;
 *   * the decomposition and sensitivity endpoints take the vector as a
 *     `weights` query parameter.
 */
export function weightsQueryParams(
  weights: Record<string, number>,
  method: string = 'weighted_sum',
): URLSearchParams {
  return new URLSearchParams({
    weights: JSON.stringify(normalizeWeights(weights)),
    method,
  })
}

/**
 * Distribute a category's weight across its leaves, honouring any
 * within-category leaf weights the user has set.
 *
 * A leaf the user has explicitly weighted keeps its relative share; a leaf
 * with no weight assigned receives an equal share of what is left.
 */
export function distributeCategoryWeight(
  category: CategoryNode,
  categoryWeight: number,
  leafWeights: Record<string, number> | undefined,
): Record<string, number> {
  const leaves = leavesOfCategory(category)
  if (leaves.length === 0) return {}

  const assigned = leaves.filter(
    (leaf) => leafWeights && (leafWeights[leaf.key] ?? 0) > 0,
  )
  const assignedTotal = assigned.reduce(
    (total, leaf) => total + (leafWeights?.[leaf.key] ?? 0),
    0,
  )

  if (assigned.length === 0) {
    const share = categoryWeight / leaves.length
    return Object.fromEntries(leaves.map((leaf) => [leaf.key, share]))
  }

  if (assigned.length === leaves.length) {
    return Object.fromEntries(
      leaves.map((leaf) => [leaf.key, categoryWeight * ((leafWeights?.[leaf.key] ?? 0) / assignedTotal)]),
    )
  }

  // Some leaves are weighted explicitly: they take their stated share of
  // the category weight and the remainder is split evenly between the
  // leaves the user has not touched.
  const remaining = Math.max(0, categoryWeight - categoryWeight * (assignedTotal / assignedTotal))
  const unassigned = leaves.filter((leaf) => !assigned.includes(leaf))
  const unassignedShare = unassigned.length > 0 ? remaining / unassigned.length : 0

  const result: Record<string, number> = {}
  for (const leaf of leaves) {
    if (assigned.includes(leaf)) {
      result[leaf.key] = categoryWeight * ((leafWeights?.[leaf.key] ?? 0) / assignedTotal)
    } else {
      result[leaf.key] = unassignedShare
    }
  }
  return result
}

/** Build the level-weight payload sent to the API. */
export function buildLevelWeights(
  tree: CriteriaTree | null,
  categoryWeights: Record<string, number>,
  leafWeights: Record<string, Record<string, number>> | undefined,
): LevelWeights {
  return {
    category_weights: normalizeWeights(categoryWeights),
    leaf_weights: leafWeights ?? null,
  }
}

/** Importance label used in the interface. */
export function importanceLabel(importance: Importance): string {
  switch (importance) {
    case 'required':
      return 'Required'
    case 'preferred':
      return 'Preferred'
    default:
      return 'Not important'
  }
}

/** Short description of what each importance level does. */
export function importanceDescription(importance: Importance): string {
  switch (importance) {
    case 'required':
      return 'Sites that fail this requirement are excluded from the shortlist.'
    case 'preferred':
      return 'Sites are kept; failing this requirement lowers their suitability score.'
    default:
      return 'This requirement is not assessed.'
  }
}
