import { api, type Credentials } from './client'

export type CommercialId = string
export type Offer = { id: string; name: string; status: string; category?: string; description?: string }
export type ICP = { id: string; name: string; status: string; version: number; segment?: string }
export type CAccount = { id: string; company_name: string; domain?: string | null; fit_score?: number | null; fit_grade?: string; lifecycle_status?: string }
export type Pipeline = { id: string; name: string; stages_json: string }
export type Opportunity = { id: string; account_id: string; stage: string; outcome: string }
export type QualRule = { id: string; name: string; rule_type: string }
export type Integration = { provider: string; label: string; state?: string; configured?: boolean; connection?: { status: string; sync_status: string } | null; blocker?: string }
export type ImportPreview = { import_id: string; headers: string[]; suggested_mapping: Record<string, string>; totals: Record<string, number>; sample: Array<Record<string, string>>; ambiguous: Array<{ row: number; reason: string }> }
export type OBSession = { id: string; path: string; current_step: string; completed: number }

const base = '/company/commercial'
const write = (credentials: Credentials, token: string, path: string, method: string, body?: unknown) =>
  api<never>(`${base}${path}`, credentials, { method, body: body === undefined ? undefined : JSON.stringify(body) }, token)

export const commercialApi = (credentials: Credentials) => ({
  offers: () => api<Offer[]>(`${base}/offers`, credentials),
  icps: () => api<ICP[]>(`${base}/icps`, credentials),
  accounts: () => api<CAccount[]>(`${base}/accounts`, credentials),
  account: (id: string) => api<CAccount & { intent?: { score: number; level: string; note: string }; activities?: unknown[] }>(`${base}/accounts/${id}`, credentials),
  pipelines: () => api<Pipeline[]>(`${base}/pipelines`, credentials),
  opportunities: () => api<Opportunity[]>(`${base}/opportunities`, credentials),
  rules: () => api<QualRule[]>(`${base}/rules`, credentials),
  integrations: () => api<Integration[]>(`${base}/integrations`, credentials),
  sessions: () => api<OBSession[]>(`${base}/onboarding-sessions`, credentials),
})

export const commercialWrite = (credentials: Credentials, token: string) => ({
  createOffer: (v: Record<string, unknown>) => write(credentials, token, '/offers', 'POST', v),
  createICP: (v: Record<string, unknown>) => write(credentials, token, '/icps', 'POST', v),
  updateICP: (id: string, v: Record<string, unknown>) => write(credentials, token, `/icps/${id}`, 'PATCH', v),
  evaluateICP: (id: string, v: Record<string, unknown>) => write(credentials, token, `/icps/${id}/evaluate`, 'POST', v),
  createAccount: (v: Record<string, unknown>) => write(credentials, token, '/accounts', 'POST', v),
  createPipeline: (v: Record<string, unknown>) => write(credentials, token, '/pipelines', 'POST', v),
  createOpportunity: (v: Record<string, unknown>) => write(credentials, token, '/opportunities', 'POST', v),
  moveOpportunity: (id: string, v: Record<string, unknown>) => write(credentials, token, `/opportunities/${id}/move`, 'POST', v),
  createRule: (v: Record<string, unknown>) => write(credentials, token, '/rules', 'POST', v),
  qualify: (id: string) => api<unknown>(`${base}/accounts/${id}/qualify`, credentials, { method: 'POST', body: '{}' }, token),
  logActivity: (v: Record<string, unknown>) => write(credentials, token, '/activities', 'POST', v),
  commitImport: (id: string, v: Record<string, unknown>) => write(credentials, token, `/imports/${id}/commit`, 'POST', v),
  connect: (p: string, v: Record<string, unknown>) => write(credentials, token, `/integrations/${p}/connect`, 'POST', v),
  disconnect: (p: string) => write(credentials, token, `/integrations/${p}/disconnect`, 'POST', {}),
  sync: (p: string) => write(credentials, token, `/integrations/${p}/sync`, 'POST', {}),
  createSession: (v: Record<string, unknown>) => write(credentials, token, '/onboarding-sessions', 'POST', v),
  updateSession: (id: string, v: Record<string, unknown>) => write(credentials, token, `/onboarding-sessions/${id}`, 'PATCH', v),
})

export async function previewImport(credentials: Credentials, token: string, entityType: string, file: File): Promise<ImportPreview> {
  const form = new FormData()
  form.append('file', file)
  const res = await fetch(`${base}/imports/preview?entity_type=${encodeURIComponent(entityType)}`, {
    method: 'POST',
    headers: { Authorization: `Basic ${btoa(`${credentials.username}:${credentials.password}`)}`, 'X-Founder-Action-Token': token },
    body: form,
  })
  if (!res.ok) throw new Error(`import preview failed: ${res.status}`)
  return res.json() as Promise<ImportPreview>
}
