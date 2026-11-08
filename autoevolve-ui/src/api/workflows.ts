import type { components } from './schema'
import { api, apiBlob, type Credentials } from './client'
import { draftOutreach } from './contacts'

export type OutreachItem = components['schemas']['OutreachItem']
export type OutreachPage = components['schemas']['OutreachPage']
export type ContentItem = components['schemas']['ContentItem']
export type ContentView = components['schemas']['ContentView']
export type BufferAccountsView = components['schemas']['BufferAccountsView']
export type BufferInsightsView = components['schemas']['BufferInsightsView']
export type HomeView = components['schemas']['HomeView']
export type ReplyItem = components['schemas']['ReplyItem']
export type RepliesPage = components['schemas']['RepliesPage']
export type MeetingMarker = components['schemas']['MeetingMarker']
export type MeetingsPage = components['schemas']['MeetingsPage']

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


export const contentView = (credentials: Credentials) => api<ContentView>('/company/ui/content', credentials)
export type PublisherCapabilities = {
  draft: boolean; schedule: boolean; confirm: boolean; insights: boolean; platforms: string[]
}
export type PublisherInfo = { name: string; label: string; capabilities: PublisherCapabilities }
export type PublisherAccount = {
  name: string; label: string; platforms: string[]; details: Record<string, unknown>
}
export type PublisherAccountsView = {
  publisher: string; label: string; capabilities: PublisherCapabilities; accounts: PublisherAccount[]; error?: string | null
}

export const publishersView = (credentials: Credentials) =>
  api<{ publishers: PublisherInfo[] }>('/company/marketing/publishers', credentials)
export const publisherAccounts = (credentials: Credentials, publisher: string) =>
  api<PublisherAccountsView>(`/company/marketing/publisher-accounts?publisher=${encodeURIComponent(publisher)}`, credentials)

export function publishManualPost(
  credentials: Credentials,
  id: string,
  input: { action: 'draft' | 'schedule'; mode?: 'queue' | 'next' | 'timed'; dueAt?: string | null; account?: string | null; token?: string },
) {
  const path = input.action === 'draft'
    ? `/company/marketing/manual-posts/${encodeURIComponent(id)}/publish/draft`
    : `/company/marketing/manual-posts/${encodeURIComponent(id)}/publish`
  return api<{ ok: boolean; post: ContentItem; result: unknown; message: string }>(path, credentials, {
    method: 'POST',
    body: JSON.stringify({
      action: input.action,
      mode: input.mode || 'queue',
      due_at: input.mode === 'timed' ? input.dueAt : null,
      account: input.account || null,
    }),
  }, input.action === 'schedule' ? input.token : undefined)
}

export type PublishJob = {
  id: string
  org_id: number
  post_id: string
  status: 'queued' | 'running' | 'completed' | 'failed' | 'unknown'
  result: { message?: string; result?: unknown; post?: ContentItem } | null
  error: string | null
  created_at: string
  updated_at: string
}

export function publishManualPostAsync(
  credentials: Credentials,
  id: string,
  input: { mode?: 'queue' | 'next' | 'timed'; dueAt?: string | null; account?: string | null; token?: string },
) {
  return api<{ ok: boolean; job: PublishJob }>(
    `/company/marketing/manual-posts/${encodeURIComponent(id)}/publish/async`,
    credentials,
    {
      method: 'POST',
      body: JSON.stringify({
        action: 'schedule',
        mode: input.mode || 'queue',
        due_at: input.mode === 'timed' ? input.dueAt : null,
        account: input.account || null,
      }),
    },
    input.token,
  )
}

export const publishJob = (credentials: Credentials, jobId: string) =>
  api<PublishJob>(`/company/marketing/publish-jobs/${encodeURIComponent(jobId)}`, credentials)

export const confirmManualPublish = (credentials: Credentials, id: string, token: string) =>
  api<{ ok: boolean; post: ContentItem; confirmation: Record<string, unknown>; message: string }>(
    `/company/marketing/manual-posts/${encodeURIComponent(id)}/publish/confirm`, credentials,
    { method: 'POST', body: '{}' }, token,
  )

export const publishInsights = (credentials: Credentials, id: string, postId: string) =>
  api<BufferInsightsView>(`/company/marketing/manual-posts/${encodeURIComponent(id)}/publish/insights?post_id=${encodeURIComponent(postId)}`, credentials)

export const assetBlob = (credentials: Credentials, path: string) => apiBlob(path, credentials)
export function createManualPost(credentials: Credentials, input: { platform: string; postType: 'carousel' | 'video'; destinationUrl: string; linkLabel: string; assets: File[]; publisher: string; bufferAccount: string }) {
  const body = new FormData()
  body.set('platform', input.platform)
  body.set('post_type', input.postType)
  if (input.destinationUrl) body.set('destination_url', input.destinationUrl)
  if (input.linkLabel) body.set('link_label', input.linkLabel)
  if (input.bufferAccount) body.set('buffer_account', input.bufferAccount)
  if (input.publisher) body.set('publisher', input.publisher)
  input.assets.forEach(asset => body.append('assets', asset))
  return api<components['schemas']['ManualPostCreateResult']>('/company/marketing/manual-posts', credentials, { method: 'POST', body })
}
export const previewManualPost = (credentials: Credentials, input: { platform: string; postType: string; destinationUrl: string; linkLabel: string; filenames: string[] }) =>
  api<components['schemas']['ManualPostPreviewView']>('/company/marketing/manual-posts/preview', credentials, {
    method: 'POST',
    body: JSON.stringify({
      platform: input.platform,
      post_type: input.postType,
      destination_url: input.destinationUrl || null,
      link_label: input.linkLabel || null,
      filenames: input.filenames,
    }),
  })
export const bufferAccounts = (credentials: Credentials) => api<BufferAccountsView>('/company/marketing/buffer-accounts', credentials)
export const bufferInsights = (credentials: Credentials, id: string, postId: string) => api<BufferInsightsView>(`/company/marketing/manual-posts/${encodeURIComponent(id)}/buffer-insights?post_id=${encodeURIComponent(postId)}`, credentials)
export const scheduleManualPost = (credentials: Credentials, id: string, mode: 'queue' | 'next' | 'timed', dueAt: string | null, token: string, account: string) => api<components['schemas']['BufferScheduleResult']>(`/company/marketing/manual-posts/${encodeURIComponent(id)}/buffer-schedule?buffer_account=${encodeURIComponent(account)}`, credentials, { method: 'POST', body: JSON.stringify({ mode, due_at: dueAt }) }, token)
export const confirmBufferSend = (credentials: Credentials, id: string, token: string) => api<components['schemas']['BufferConfirmResult']>(`/company/marketing/manual-posts/${encodeURIComponent(id)}/buffer-confirm`, credentials, { method: 'POST' }, token)

export const homeView = (credentials: Credentials) => api<HomeView>('/company/ui/home', credentials)

// True workflow CRUD against /company/workflows. These are the workflows
// names; the outreach/campaign/content helpers below are read projections
// that predate this file's name and stay here to avoid breaking imports.
export type Workflow = components['schemas']['Workflow']
export type WorkflowState = components['schemas']['WorkflowState']

export const listWorkflows = (credentials: Credentials, status?: string) => {
  const params = new URLSearchParams()
  if (status) params.set('status', status)
  const query = params.toString()
  return api<Workflow[]>(`/company/workflows${query ? `?${query}` : ''}`, credentials)
}
export const getWorkflow = (credentials: Credentials, id: string) =>
  api<Workflow>(`/company/workflows/${encodeURIComponent(id)}`, credentials)
export const createWorkflow = (
  credentials: Credentials,
  input: { name: string; objective?: string; trigger?: Record<string, unknown>; steps?: Array<Record<string, unknown>>; success_metric?: Record<string, unknown> },
  token: string,
) => api<Workflow>('/company/workflows', credentials, { method: 'POST', body: JSON.stringify(input) }, token)
export const runWorkflow = (credentials: Credentials, id: string, token: string, resume = false) =>
  api<Workflow>(`/company/workflows/${encodeURIComponent(id)}/run`, credentials, { method: 'POST', body: JSON.stringify({ resume }) }, token)
export const pauseWorkflow = (credentials: Credentials, id: string, token: string) =>
  api<Workflow>(`/company/workflows/${encodeURIComponent(id)}/pause`, credentials, { method: 'POST' }, token)
export const workflowState = (credentials: Credentials, id: string) =>
  api<WorkflowState>(`/company/workflows/${encodeURIComponent(id)}/state`, credentials)

export function repliesPage(credentials: Credentials, input: { page: number; q: string; view: string; sort: string }) {
  const params = new URLSearchParams({ page: String(input.page), page_size: '10', view: input.view, sort: input.sort })
  if (input.q) params.set('q', input.q)
  return api<RepliesPage>(`/company/ui/replies?${params}`, credentials)
}
export const replyDetail = (credentials: Credentials, id: number) => api<ReplyItem>(`/company/ui/replies/${id}`, credentials)
export interface InboxSyncResult {
  ok: boolean
  checked: number
  ingested: { email_id: string | null; lead_id: string | null; duplicate: boolean }[]
  skipped: (string | null)[]
  unmatched: { email_id: string | null; from: string; subject: string; received_at: string; reason: string }[]
  errors: { email_id: string | null; error: string }[]
}
export const syncResendInbox = (credentials: Credentials, input: { limit: number; to: string | null }, token: string) =>
  api<InboxSyncResult>('/company/sales/inbox/sync', credentials, { method: 'POST', body: JSON.stringify({ limit: input.limit, to: input.to }) }, token)
export const createReplyDraft = draftOutreach
export const requestMeeting = (credentials: Credentials, leadId: string, input: { slots: string[]; note?: string }, token: string) =>
  api<components['schemas']['MeetingRequestResult']>(`/company/sales/leads/${encodeURIComponent(leadId)}/meeting-request`, credentials, { method: 'POST', body: JSON.stringify(input) }, token)

export function meetingsPage(credentials: Credentials, input: { page: number; q: string; view: string; sort: string }) {
  const params = new URLSearchParams({ page: String(input.page), page_size: '10', view: input.view, sort: input.sort })
  if (input.q) params.set('q', input.q)
  return api<MeetingsPage>(`/company/ui/meetings?${params}`, credentials)
}
export const meetingDetail = (credentials: Credentials, id: string) => api<MeetingMarker>(`/company/ui/meetings/${encodeURIComponent(id)}`, credentials)
export const recordMeetingMarker = (credentials: Credentials, leadId: string, scheduledFor: string | null, note: string | null, token: string) => api<components['schemas']['MeetingActionResult']>(`/company/sales/leads/${encodeURIComponent(leadId)}/schedule-meeting`, credentials, { method: 'POST', body: JSON.stringify({ scheduled_for: scheduledFor, note }) }, token)
