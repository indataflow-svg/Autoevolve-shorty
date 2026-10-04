import { api, type Credentials } from './client'

export type RenderMode = 'shots' | 'full'

export type VideoSpecSummary = {
  id: string
  project_id: string
  title: string
  status: string
  format: { durationSeconds: number; aspectRatio: string; fps: number }
  transcript: { id: string }[]
}

export type ShotPlanSummary = {
  id: string
  video_spec_id: string
  status: string
  total_duration_seconds: number
  shots: { id: string; visualType: string; startSeconds: number; endSeconds: number }[]
}

export type RenderJobSummary = {
  id: string
  shot_id: string
  renderer: string
  status: string
  frames: number | null
  seed: number | null
  output_path: string
  attempts: number
  max_attempts: number
  worker_id: string | null
  error: { code?: string; message: string; retryable: boolean } | null
}

export type QueueCounts = {
  total: number
  by_renderer: Record<string, number>
  brand_end_frames: number
}

export const RENDER_MODES: { value: RenderMode; label: string; hint: string }[] = [
  {
    value: 'shots',
    label: 'Per-shot clips',
    hint: 'One job per clip. Short jobs fit the worker envelope; failed shots retry individually.',
  },
  {
    value: 'full',
    label: 'Full video',
    hint: 'A single whole-video render. Exceeds the validated worker envelope; the worker may reject it.',
  },
]

export function listSpecs(credentials: Credentials) {
  return api<{ specs: VideoSpecSummary[] }>('/company/video/specs', credentials)
}

export function listPlans(credentials: Credentials, specId?: string) {
  const query = specId ? `?spec_id=${encodeURIComponent(specId)}` : ''
  return api<{ plans: ShotPlanSummary[] }>(`/company/video/plans${query}`, credentials)
}

export function getPlan(credentials: Credentials, planId: string) {
  return api<ShotPlanSummary>(`/company/video/plans/${encodeURIComponent(planId)}`, credentials)
}

export function queuePlan(credentials: Credentials, planId: string, renderMode: RenderMode, token: string) {
  return api<{ ok: boolean; queued: RenderJobSummary[]; already_queued: boolean; counts: QueueCounts }>(
    `/company/video/plans/${encodeURIComponent(planId)}/queue?render_mode=${renderMode}`,
    credentials,
    { method: 'POST' },
    token,
  )
}

export function listJobs(credentials: Credentials, planId: string) {
  return api<{ jobs: RenderJobSummary[] }>(
    `/company/video/jobs?shot_plan_id=${encodeURIComponent(planId)}`,
    credentials,
  )
}

export function queueStats(credentials: Credentials) {
  return api<{ by_status: Record<string, number>; queued_by_renderer: Record<string, number> }>(
    '/company/video/queue/stats',
    credentials,
  )
}
