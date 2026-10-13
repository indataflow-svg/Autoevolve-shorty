import type { components } from './schema'
import { api, type Credentials } from './client'

export type CompanyContext = components['schemas']['CompanyContext']
export type CompanyContextSections = components['schemas']['CompanyContextSections']
export type CompanyContextView = components['schemas']['CompanyContextView']
export type NextStage = NonNullable<CompanyContextView['next_stage']>
export type ContextState = NonNullable<CompanyContext['state']>
export type MarketingStage = NonNullable<ContextState['marketing_stage']>

/** The stage options the onboarding form offers today. */
export const MARKETING_STAGES: Array<{ value: MarketingStage; label: string }> = [
  { value: 'starting_from_zero', label: 'Starting from zero' },
]

export const companyContext = (credentials: Credentials) =>
  api<CompanyContextView>('/company/context', credentials)

export const replaceCompanyContext = (
  credentials: Credentials, value: CompanyContextSections, token: string,
) => api<CompanyContextView>(
  '/company/context', credentials,
  { method: 'PUT', body: JSON.stringify(value) }, token,
)

/**
 * Computed keys the read model adds on top of the ten sections. They are
 * never write authority: spreading a fetched view into a PUT body must not
 * echo them back as claims.
 */
const COMPUTED_CONTEXT_KEYS = [
  'status', 'missing', 'completeness_percent', 'workflow_ready', 'updated_at', 'schema_version',
]

/**
 * Merge founder-touched sections over a freshly fetched context.
 *
 * The PUT endpoint is a full replacement, so sending a stale view silently
 * discards other pages' saves (last-writer-wins). Callers must pass a
 * just-fetched context as `base` — never a cached render prop — and only
 * the fields the founder just edited as `touched`.
 */
export function mergeContextSections(
  base: Record<string, unknown>,
  touched: Record<string, Record<string, string>>,
): CompanyContextSections {
  const clean: Record<string, unknown> = {}
  for (const [section, value] of Object.entries(base || {})) {
    if (!COMPUTED_CONTEXT_KEYS.includes(section)) clean[section] = value
  }
  for (const [section, fields] of Object.entries(touched || {})) {
    const prev = clean[section]
    clean[section] = { ...((prev && typeof prev === 'object' ? prev : {}) as Record<string, string>), ...fields }
  }
  return clean as unknown as CompanyContextSections
}

/**
 * Below this completeness floor the consuming flows are blocked, not merely
 * nudged: with under 40% (fewer than 3 of 6 groups) there is too little to
 * plan, validate, or run against. The 80% workflow gate still governs plan
 * generation; this floor governs whether the actions are even offered.
 */
export const SETUP_FLOOR_PERCENT = 40

export type SetupTrigger = 'fresh' | 'blocked' | 'incomplete' | 'ready' | 'unknown'

/**
 * One trigger definition for every flow that needs usable company data.
 * Fresh means literally untouched; blocked means under the floor; incomplete
 * means progressing but below the workflow gate; ready means the gate passes.
 */
export function setupTrigger(view: {
  context?: { missing?: string[]; completeness_percent?: number; workflow_ready?: boolean } | null,
  next_stage?: string | null,
} | null | undefined): SetupTrigger {
  if (!view || !view.context) return 'unknown'
  // A resolved route needs the stage answer; readiness alone is not enough.
  if (view.context.workflow_ready && view.next_stage) return 'ready'
  const missing = view.context.missing || []
  const percent = view.context.completeness_percent ?? 0
  if (missing.length > 0 && percent === 0) return 'fresh'
  if (percent < SETUP_FLOOR_PERCENT) return 'blocked'
  return 'incomplete'
}