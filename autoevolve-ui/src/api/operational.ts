import type { components } from './schema'
import { api, type Credentials } from './client'

export type IntegrationsView = components['schemas']['IntegrationsView']
export type ProviderGroup = components['schemas']['ProviderGroup']
export type SettingsView = components['schemas']['SettingsView']
export type WorkspaceOrg = components['schemas']['WorkspaceOrg']
export type PublicLink = components['schemas']['PublicLink']
export type SetupKeysPayload = components['schemas']['SetupKeysPayload']
export type MarketingOrgCreateRequest = components['schemas']['MarketingOrgCreateRequest']

export const integrationsView = (credentials: Credentials) => api<IntegrationsView>('/company/ui/integrations', credentials)
export const incidentsView = (credentials: Credentials) => api<components['schemas']['IncidentsView']>('/company/incidents?limit=100', credentials)
export const settingsView = (credentials: Credentials) => api<SettingsView>('/company/ui/settings', credentials)

export function testProviderKeys(credentials: Credentials, payload: SetupKeysPayload, token: string) {
  return api<components['schemas']['SetupKeyTestResult']>('/company/setup/keys/test', credentials, { method: 'POST', body: JSON.stringify(payload) }, token)
}

export function saveProviderKeys(credentials: Credentials, payload: SetupKeysPayload, token: string) {
  return api<components['schemas']['SetupKeySaveResult']>('/company/setup/keys', credentials, { method: 'POST', body: JSON.stringify(payload) }, token)
}

export function createOrganization(credentials: Credentials, payload: MarketingOrgCreateRequest) {
  return api<components['schemas']['MarketingOrgCreateResult']>('/company/marketing/orgs', credentials, { method: 'POST', body: JSON.stringify(payload) })
}

export function selectOrganization(credentials: Credentials, orgId: number) {
  return api<components['schemas']['MarketingOrgActiveResult']>('/company/marketing/orgs/active', credentials, { method: 'POST', body: JSON.stringify({ org_id: orgId }) })
}

export function setOrganizationCapabilities(credentials: Credentials, orgId: number, capabilities: Record<string, boolean>) {
  return api<components['schemas']['OrgCapabilitiesResult']>(`/company/marketing/orgs/${orgId}/capabilities`, credentials, { method: 'POST', body: JSON.stringify({ capabilities }) })
}
