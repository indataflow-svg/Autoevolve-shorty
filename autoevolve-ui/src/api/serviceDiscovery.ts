import type { components } from './schema'
import { api, type Credentials } from './client'

export type ServiceDiscoveryView = components['schemas']['ServiceDiscoveryView']
export type ServiceTargetEdit = components['schemas']['ServiceTargetEdit']

export const serviceDiscovery = (credentials: Credentials) => api<ServiceDiscoveryView>('/company/ui/service-discovery', credentials)
export const searchService = (credentials: Credentials, service: string, desired_contacts: number, token: string) => api<ServiceDiscoveryView>(
  '/company/setup/service-discovery/search', credentials,
  { method: 'POST', body: JSON.stringify({ service, desired_contacts }) }, token,
)
export const retargetService = (credentials: Credentials, id: string, target: ServiceTargetEdit, token: string) => api<ServiceDiscoveryView>(
  `/company/setup/service-discovery/${encodeURIComponent(id)}/search`, credentials,
  { method: 'POST', body: JSON.stringify(target) }, token,
)
