import type { components } from './schema'
import { api, type Credentials } from './client'

export type IntegrationsView = components['schemas']['IntegrationsView']
export type ProviderGroup = components['schemas']['ProviderGroup']
export type SettingsView = components['schemas']['SettingsView']
export type WorkspaceOrg = components['schemas']['WorkspaceOrg']
export type PublicLink = components['schemas']['PublicLink']
export type SetupKeysPayload = components['schemas']['SetupKeysPayload']
export type MarketingOrgCreateRequest = components['schemas']['MarketingOrgCreateRequest']
export type BufferSetupAccounts = components['schemas']['BufferSetupAccountsView']
export type BufferSetupAccount = components['schemas']['BufferAccountView']
export type BufferDiscovery = components['schemas']['BufferDiscoveryView']
export type BufferConnectResult = components['schemas']['BufferConnectResult']

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

export const bufferSetupAccounts = (credentials: Credentials) =>
  api<BufferSetupAccounts>('/company/setup/buffer/accounts', credentials)

export function discoverBuffer(
  credentials: Credentials,
  payload: { account: string; api_key: string | null },
  token: string,
) {
  return api<BufferDiscovery>('/company/setup/buffer/discover', credentials, {
    method: 'POST',
    body: JSON.stringify(payload),
  }, token)
}

export function connectBuffer(
  credentials: Credentials,
  payload: {
    account: string
    api_key: string | null
    organization_id: string
    instagram_channel_id: string | null
    x_channel_id: string | null
    linkedin_channel_id: string | null
  },
  token: string,
) {
  return api<BufferConnectResult>('/company/setup/buffer/connect', credentials, {
    method: 'POST',
    body: JSON.stringify(payload),
  }, token)
}

export type QuotaItem = {
  kind: string; plan: string; used: number; limit: number; remaining: number; reset_at: string
}
export type QuotasView = { plan: string; quotas: Record<string, QuotaItem> }
export type GovernanceLimitsView = {
  plan: string
  max_spend_usd: number
  max_actions: number
  max_outreach_contacts: number
  max_duration_days: number
  overrides: Record<string, number>
}

export const quotasView = (credentials: Credentials) =>
  api<QuotasView>('/company/ui/quotas', credentials)

export const limitsView = (credentials: Credentials) =>
  api<GovernanceLimitsView>('/company/ui/limits', credentials)

export function saveLimits(
  credentials: Credentials,
  payload: { max_spend_usd?: number; max_actions?: number; max_outreach_contacts?: number; max_duration_days?: number },
  token: string,
) {
  return api<GovernanceLimitsView>('/company/ui/limits', credentials, {
    method: 'PUT',
    body: JSON.stringify(payload),
  }, token)
}

export type PublisherCatalogItem = {
  name: string
  label: string
  capabilities: { draft: boolean; schedule: boolean; confirm: boolean; insights: boolean; platforms: string[] }
}
export type WebhookConnectionView = {
  org_id: number
  provider: string
  url: string
  account: string
  label: string
  platforms: string[]
  updated_at: string
  configured: boolean
  secret_set: boolean
}
export type PublisherConnectionsView = {
  publishers: PublisherCatalogItem[]
  webhook: WebhookConnectionView | null
}

export const publisherConnectionsView = (credentials: Credentials) =>
  api<PublisherConnectionsView>('/company/ui/publishers', credentials)

export function saveWebhookConnection(
  credentials: Credentials,
  payload: { url: string; secret: string; account: string; label: string; platforms: string },
  token?: string,
) {
  return api<{ webhook: WebhookConnectionView }>('/company/ui/publishers/webhook', credentials, {
    method: 'PUT',
    body: JSON.stringify(payload),
  }, token)
}

export function deleteWebhookConnection(credentials: Credentials, token?: string) {
  return api<{ webhook: null }>('/company/ui/publishers/webhook', credentials, { method: 'DELETE' }, token)
}
