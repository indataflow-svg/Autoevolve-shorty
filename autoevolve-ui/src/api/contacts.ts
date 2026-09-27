import type { components } from './schema'
import { api, type Credentials } from './client'

export type Contact = components['schemas']['Contact']
export type ContactDetail = components['schemas']['ContactDetail']
export type ContactsPage = components['schemas']['ContactsPage']
export type LeadIntake = components['schemas']['LeadIntake']
export type SalesDraftRecord = components['schemas']['SalesDraftRecord']
export type Stage = Contact['stage']
export type Sort = 'recent' | 'oldest' | 'name' | 'score' | 'company'

export type ContactFilters = { page: number; q: string; stage: Stage | ''; sort: Sort }

export function contactsPage(credentials: Credentials, filters: ContactFilters) {
  const params = new URLSearchParams({ page: String(filters.page), page_size: '10', sort: filters.sort })
  if (filters.q) params.set('q', filters.q)
  if (filters.stage) params.set('stage', filters.stage)
  return api<ContactsPage>(`/company/sales/contacts?${params}`, credentials)
}

export function contactDetail(credentials: Credentials, id: string) {
  return api<ContactDetail>(`/company/sales/contacts/${encodeURIComponent(id)}`, credentials)
}

export function draftOutreach(credentials: Credentials, id: string, token: string) {
  return api<SalesDraftRecord>(`/company/sales/leads/${encodeURIComponent(id)}/draft`, credentials, { method: 'POST' }, token)
}

export function addContact(credentials: Credentials, value: LeadIntake, token: string) {
  return api<components['schemas']['LeadCreateResult']>(
    '/company/sales/leads', credentials, { method: 'POST', body: JSON.stringify(value) }, token,
  )
}
