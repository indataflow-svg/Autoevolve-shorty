import type { components } from './schema'
import { api, apiBlob, type Credentials } from './client'
import { draftOutreach } from './contacts'

export type OutreachItem = components['schemas']['OutreachItem']
export type OutreachPage = components['schemas']['OutreachPage']
export type CampaignItem = components['schemas']['CampaignItem']
export type CampaignDetail = components['schemas']['CampaignDetail']
export type CampaignsPage = components['schemas']['CampaignsPage']
export type ContentItem = components['schemas']['ContentItem']
export type ContentView = components['schemas']['ContentView']
export type BufferAccountsView = components['schemas']['BufferAccountsView']
export type BufferInsightsView = components['schemas']['BufferInsightsView']
export type HomeView = components['schemas']['HomeView']
export type ReplyItem = components['schemas']['ReplyItem']
export type RepliesPage = components['schemas']['RepliesPage']
export type MeetingMarker = components['schemas']['MeetingMarker']
export type MeetingsPage = components['schemas']['MeetingsPage']
export type CampaignLaunchRequest = components['schemas']['CampaignLaunchRequest']

export const DRAFT_STATUS = {
  draft: 'draft', approved: 'approved', sending: 'sending', sent: 'sent',
  sendUnknown: 'send_unknown', replied: 'replied', suppressed: 'suppressed',
} as const

export function outreachPage(credentials: Credentials, input: { page: number; q: string; status: string; sort: string }) {
  const params = new URLSearchParams({ page: String(input.page), page_size: '10', sort: input.sort })
  if (input.q) params.set('q', input.q)
  if (input.status) params.set('status', input.status)
  return api<OutreachPage>(`/company/ui/outreach?${params}`, credentials)
}
export const outreachDetail = (credentials: Credentials, id: string) => api<OutreachItem>(`/company/ui/outreach/${encodeURIComponent(id)}`, credentials)
export const updateOutreach = (credentials: Credentials, id: string, input: components['schemas']['DraftUpdatePayload'], token: string) => api<components['schemas']['SalesDraftRecord']>(`/company/sales/drafts/${encodeURIComponent(id)}/update`, credentials, { method: 'POST', body: JSON.stringify(input) }, token)
export const approveOutreach = (credentials: Credentials, id: string, token: string) => api<components['schemas']['SalesDraftRecord']>(`/company/sales/drafts/${encodeURIComponent(id)}/approve`, credentials, { method: 'POST' }, token)
export const sendOutreach = (credentials: Credentials, id: string, token: string) => api<components['schemas']['SendActionResult']>(`/company/sales/drafts/${encodeURIComponent(id)}/send`, credentials, { method: 'POST' }, token)

export function campaignsPage(credentials: Credentials, input: { page: number; q: string; status: string; sort: string; orgId: number | null }) {
  const params = new URLSearchParams({ page: String(input.page), page_size: '10', sort: input.sort })
  if (input.q) params.set('q', input.q)
  if (input.status) params.set('status', input.status)
  if (input.orgId) params.set('org_id', String(input.orgId))
  return api<CampaignsPage>(`/company/ui/campaigns?${params}`, credentials)
}
export const campaignDetail = (credentials: Credentials, id: string) => api<CampaignDetail>(`/company/ui/campaigns/${encodeURIComponent(id)}`, credentials)
export const createCampaign = (credentials: Credentials, input: CampaignLaunchRequest) => api<components['schemas']['CampaignCreateResult']>('/company/marketing/campaigns', credentials, { method: 'POST', body: JSON.stringify(input) })
export const approveCampaignScript = (credentials: Credentials, id: string, token: string) => api<components['schemas']['CampaignTransitionResult']>(`/company/marketing/campaigns/${encodeURIComponent(id)}/approve-script`, credentials, { method: 'POST' }, token)
export const retryCampaign = (credentials: Credentials, id: string, token: string) => api<components['schemas']['CampaignTransitionResult']>(`/company/marketing/campaigns/${encodeURIComponent(id)}/retry`, credentials, { method: 'POST' }, token)

export const contentView = (credentials: Credentials) => api<ContentView>('/company/ui/content', credentials)
export const assetBlob = (credentials: Credentials, path: string) => apiBlob(path, credentials)
export const createAssetPack = (credentials: Credentials, input: components['schemas']['AssetPackRequest']) => api<components['schemas']['AssetPackCreateResult']>('/company/marketing/asset-packs', credentials, { method: 'POST', body: JSON.stringify(input) })
export function createManualPost(credentials: Credentials, input: { platform: 'instagram' | 'x' | 'linkedin'; postType: 'carousel' | 'video'; destinationUrl: string; linkLabel: string; assets: File[] }) {
  const body = new FormData()
  body.set('platform', input.platform)
  body.set('post_type', input.postType)
  if (input.destinationUrl) body.set('destination_url', input.destinationUrl)
  if (input.linkLabel) body.set('link_label', input.linkLabel)
  input.assets.forEach(asset => body.append('assets', asset))
  return api<components['schemas']['ManualPostCreateResult']>('/company/marketing/manual-posts', credentials, { method: 'POST', body })
}
export const bufferAccounts = (credentials: Credentials) => api<BufferAccountsView>('/company/marketing/buffer-accounts', credentials)
export const bufferInsights = (credentials: Credentials, id: string, postId: string) => api<BufferInsightsView>(`/company/marketing/manual-posts/${encodeURIComponent(id)}/buffer-insights?post_id=${encodeURIComponent(postId)}`, credentials)
export const scheduleManualPost = (credentials: Credentials, id: string, mode: 'queue' | 'next' | 'timed', dueAt: string | null, token: string, account: string) => api<components['schemas']['BufferScheduleResult']>(`/company/marketing/manual-posts/${encodeURIComponent(id)}/buffer-schedule?buffer_account=${encodeURIComponent(account)}`, credentials, { method: 'POST', body: JSON.stringify({ mode, due_at: dueAt }) }, token)

export const homeView = (credentials: Credentials) => api<HomeView>('/company/ui/home', credentials)

export function repliesPage(credentials: Credentials, input: { page: number; q: string; view: string; sort: string }) {
  const params = new URLSearchParams({ page: String(input.page), page_size: '10', view: input.view, sort: input.sort })
  if (input.q) params.set('q', input.q)
  return api<RepliesPage>(`/company/ui/replies?${params}`, credentials)
}
export const replyDetail = (credentials: Credentials, id: number) => api<ReplyItem>(`/company/ui/replies/${id}`, credentials)
export const createReplyDraft = draftOutreach

export function meetingsPage(credentials: Credentials, input: { page: number; q: string; view: string; sort: string }) {
  const params = new URLSearchParams({ page: String(input.page), page_size: '10', view: input.view, sort: input.sort })
  if (input.q) params.set('q', input.q)
  return api<MeetingsPage>(`/company/ui/meetings?${params}`, credentials)
}
export const meetingDetail = (credentials: Credentials, id: string) => api<MeetingMarker>(`/company/ui/meetings/${encodeURIComponent(id)}`, credentials)
export const recordMeetingMarker = (credentials: Credentials, leadId: string, scheduledFor: string | null, note: string | null, token: string) => api<components['schemas']['MeetingActionResult']>(`/company/sales/leads/${encodeURIComponent(leadId)}/schedule-meeting`, credentials, { method: 'POST', body: JSON.stringify({ scheduled_for: scheduledFor, note }) }, token)
