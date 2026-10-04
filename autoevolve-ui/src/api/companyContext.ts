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