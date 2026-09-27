import type { components } from './schema'
import { api, type Credentials } from './client'

export type CompanySummary = components['schemas']['CompanySummary']
export type CompanyDetail = components['schemas']['CompanyDetail']
export type CompaniesPage = components['schemas']['CompaniesPage']
export type LeadResearchRequest = components['schemas']['LeadResearchRequest']
export type CompanyView = 'all' | 'candidates' | 'profiled' | 'with_contacts'
export type CompanySort = 'recent' | 'name' | 'contacts'
export type CompanyFilters = {
  page: number
  q: string
  view: CompanyView
  sort: CompanySort
  industry: string
  country: string
}

export function companiesPage(credentials: Credentials, filters: CompanyFilters) {
  const params = new URLSearchParams({ page: String(filters.page), page_size: '8', view: filters.view, sort: filters.sort })
  if (filters.q) params.set('q', filters.q)
  if (filters.industry) params.set('industry', filters.industry)
  if (filters.country) params.set('country', filters.country)
  return api<CompaniesPage>(`/company/sales/companies?${params}`, credentials)
}

export function companyDetail(credentials: Credentials, id: string) {
  return api<CompanyDetail>(`/company/sales/companies/${encodeURIComponent(id)}`, credentials)
}

export function runCompanyResearch(credentials: Credentials, input: LeadResearchRequest, token: string) {
  return api<components['schemas']['ResearchActionResult']>(
    '/company/sales/research/leads', credentials,
    { method: 'POST', body: JSON.stringify(input) }, token,
  )
}

export function prospectCompany(credentials: Credentials, domain: string, provider: 'hunter' | 'apollo', token: string) {
  return api<components['schemas']['ProspectActionResult']>(
    '/company/sales/prospect/domain', credentials,
    { method: 'POST', body: JSON.stringify({ domain, provider, limit: 5 }) }, token,
  )
}

export function resolveCompanyProfile(credentials: Credentials, leadId: string, token: string) {
  return api<components['schemas']['CompanyResolutionResult']>(
    `/company/sales/leads/${encodeURIComponent(leadId)}/resolve-company`, credentials,
    { method: 'POST' }, token,
  )
}
