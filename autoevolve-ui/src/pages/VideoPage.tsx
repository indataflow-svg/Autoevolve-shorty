import { useMemo, useState, type FormEvent } from 'react'
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'
import { useCredentials } from '../app/Auth'
import { AppShell } from '../components/Shell'
import { DataState, LoadingRows } from '../components/Primitives'
import { StatusText } from '../components/WorkflowTable'
import { ApiError } from '../api/client'
import {
  RENDER_MODES,
  getPlan,
  listJobs,
  listPlans,
  listSpecs,
  queuePlan,
  queueStats,
  type RenderMode,
} from '../api/video'

const jobStatuses = ['pending', 'leased', 'running', 'completed', 'failed', 'cancelled'] as const

function toneFor(status: string): 'green' | 'yellow' | 'red' | 'blue' | 'neutral' {
  if (status === 'completed') return 'green'
  if (status === 'failed' || status === 'cancelled') return 'red'
  if (status === 'pending') return 'neutral'
  return 'blue'
}

export function VideoPage() {
  const credentials = useCredentials()
  const queryClient = useQueryClient()
  const [specId, setSpecId] = useState('')
  const [planId, setPlanId] = useState('')
  const [renderMode, setRenderMode] = useState<RenderMode>('full')
  const [token, setToken] = useState('')
  const [formError, setFormError] = useState('')
  const [lastQueue, setLastQueue] = useState<{ total: number; already: boolean } | null>(null)

  const specs = useQuery({ queryKey: ['video-specs'], queryFn: () => listSpecs(credentials), staleTime: 30_000 })
  const plans = useQuery({
    queryKey: ['video-plans', specId],
    queryFn: () => listPlans(credentials, specId || undefined),
    staleTime: 30_000,
  })
  const stats = useQuery({ queryKey: ['video-queue-stats'], queryFn: () => queueStats(credentials), staleTime: 15_000 })
  const plan = useQuery({
    queryKey: ['video-plan', planId],
    queryFn: () => getPlan(credentials, planId),
    enabled: !!planId,
    staleTime: 30_000,
  })
  const jobs = useQuery({
    queryKey: ['video-jobs', planId],
    queryFn: () => listJobs(credentials, planId),
    enabled: !!planId,
    staleTime: 10_000,
  })

  const modeHint = useMemo(
    () => RENDER_MODES.find(mode => mode.value === renderMode)?.hint || '',
    [renderMode],
  )
  const selectedPlan = plan.data
  const activePlanId = planId || selectedPlan?.id || ''

  const queue = useMutation({
    mutationFn: () => {
      if (!activePlanId) throw new Error('Choose a shot plan first.')
      return queuePlan(credentials, activePlanId, renderMode, token)
    },
    onSuccess: result => {
      setFormError('')
      setLastQueue({ total: result.counts.total, already: result.already_queued })
      void queryClient.invalidateQueries({ queryKey: ['video-jobs', activePlanId] })
      void queryClient.invalidateQueries({ queryKey: ['video-queue-stats'] })
    },
    onError: error => {
      setFormError(error instanceof ApiError ? error.message : String(error))
    },
  })

  function submit(event: FormEvent) {
    event.preventDefault()
    setLastQueue(null)
    queue.mutate()
  }

  return <AppShell active="Video" query="" onQueryChange={() => undefined}>
    <div className="page-header"><div><h2>Video renders</h2><p className="page-subtitle">Queue a shot plan as per-shot clips or one full video, then track the render jobs.</p></div></div>
    {stats.data && <p className="operational-note">Queue: {Object.entries(stats.data.by_status).map(([status, count]) => `${count} ${status}`).join(' · ') || 'empty'}</p>}
    <div className="table-panel"><form className="workflow-form" onSubmit={submit}>
      <h3>Queue a render</h3>
      <label>Spec{specs.isPending ? ' (loading…)' : ''}<select aria-label="Video spec" value={specId} onChange={event => { setSpecId(event.target.value); setPlanId(''); }}>
        <option value="">All specs</option>
        {(specs.data?.specs || []).map(spec => <option key={spec.id} value={spec.id}>{spec.title} · {spec.format.durationSeconds}s</option>)}
      </select></label>
      {specs.isError && <p className="form-error" role="alert">Specs unavailable: {specs.error.message}</p>}
      <label>Shot plan{plans.isPending ? ' (loading…)' : ''}<select aria-label="Shot plan" value={planId} onChange={event => setPlanId(event.target.value)} required>
        <option value="">Choose a plan…</option>
        {(plans.data?.plans || []).map(item => <option key={item.id} value={item.id}>{item.id} · {item.shots.length} shots · {item.status}</option>)}
      </select></label>
      {plans.isError && <p className="form-error" role="alert">Plans unavailable: {plans.error.message}</p>}
      <label>Render type<select aria-label="Render type" value={renderMode} onChange={event => setRenderMode(event.target.value as RenderMode)}>
        {RENDER_MODES.map(mode => <option key={mode.value} value={mode.value}>{mode.label}</option>)}
      </select></label>
      <p className="operational-note">{modeHint}</p>
      {selectedPlan && <p className="operational-note">{selectedPlan.shots.length} shots · {selectedPlan.total_duration_seconds}s · {selectedPlan.status}</p>}
      <label>Founder action token<input type="password" aria-label="Founder action token" autoComplete="off" value={token} onChange={event => setToken(event.target.value)} required /></label>
      {formError && <p className="form-error" role="alert">{formError}</p>}
      {lastQueue && <p className="operational-note" role="status">{lastQueue.already ? 'Plan already queued: ' : 'Queued: '}{lastQueue.total} job{lastQueue.total === 1 ? '' : 's'} ({renderMode === 'full' ? 'full video' : 'per-shot clips'}).</p>}
      <button className="button primary" type="submit" disabled={queue.isPending || !activePlanId}>{queue.isPending ? 'Queueing…' : 'Queue render'}</button>
    </form></div>
    <div className="table-panel">
      <h3>Render jobs{activePlanId ? ` · ${activePlanId}` : ''}</h3>
      {!activePlanId ? <DataState title="No plan selected" detail="Choose a shot plan above to list its render jobs." /> :
        jobs.isPending ? <LoadingRows label="Loading render jobs" /> :
        jobs.isError ? <DataState title="Jobs unavailable" detail={jobs.error.message} retry={() => jobs.refetch()} /> :
        !jobs.data.jobs.length ? <DataState title="No jobs yet" detail="Queue this plan to create render jobs." /> :
        <table className="data-table"><thead><tr><th>Shot</th><th>Renderer</th><th>Status</th><th>Frames</th><th>Attempts</th><th>Output</th><th>Error</th></tr></thead>
        <tbody>{jobs.data.jobs.map(job => <tr key={job.id}>
          <td>{job.shot_id}</td>
          <td>{job.renderer}</td>
          <td><StatusText value={job.status} known={jobStatuses} tone={toneFor(job.status)} /></td>
          <td>{job.frames ?? '—'}</td>
          <td>{job.attempts}/{job.max_attempts}</td>
          <td>{job.output_path}</td>
          <td>{job.error ? `${job.error.code || 'error'}: ${job.error.message}` : '—'}</td>
        </tr>)}</tbody></table>}
    </div>
  </AppShell>
}
