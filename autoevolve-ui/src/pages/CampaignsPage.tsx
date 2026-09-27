import { useState, type FormEvent } from 'react'
import { keepPreviousData, useQuery, useQueryClient } from '@tanstack/react-query'
import { createColumnHelper } from '@tanstack/react-table'
import { Link, useSearchParams } from 'react-router-dom'
import { AlertCircle, ChevronLeft, ChevronRight, FileCheck2, Megaphone, Plus, Send } from 'lucide-react'
import { approveCampaignScript, campaignDetail, campaignsPage, createCampaign, retryCampaign, type CampaignItem } from '../api/workflows'
import { useCredentials } from '../app/Auth'
import { AppShell } from '../components/Shell'
import { DataState, LoadingRows, RightDrawer } from '../components/Primitives'
import { ShortDate, StatusText, WorkflowMetrics, WorkflowTable } from '../components/WorkflowTable'

const campaignStatuses = ['queued', 'running', 'needs_campaign_review', 'needs_voice_recording', 'variants_ready', 'selected', 'drafting', 'drafted', 'failed']
const tabs = [{ label: 'All', value: '' }, { label: 'Script review', value: 'needs_campaign_review' }, { label: 'Variants ready', value: 'variants_ready' }, { label: 'Drafted', value: 'drafted' }, { label: 'Failed', value: 'failed' }]
const column = createColumnHelper<CampaignItem>()

function CampaignDrawer({ id, close }: { id: string; close: () => void }) {
  const credentials = useCredentials()
  const queryClient = useQueryClient()
  const detail = useQuery({ queryKey: ['campaign-detail', id], queryFn: () => campaignDetail(credentials, id) })
  const [token, setToken] = useState('')
  const [error, setError] = useState('')
  const [notice, setNotice] = useState('')
  const [pending, setPending] = useState(false)
  const campaign = detail.data
  async function act(kind: 'approve' | 'retry') {
    setError(''); setNotice('')
    if (!token.trim()) { setError('Enter the founder action token.'); return }
    if (!campaign || (kind === 'approve' && (campaign.status !== 'needs_campaign_review' || !campaign.script_available)) || (kind === 'retry' && campaign.status !== 'failed')) { setError('This action is not allowed in the current campaign state.'); return }
    setPending(true)
    try {
      const response = kind === 'approve' ? await approveCampaignScript(credentials, id, token) : await retryCampaign(credentials, id, token)
      if (!response.ok) throw new Error('Backend did not confirm this campaign action. Refresh and inspect its status.')
      await Promise.all([queryClient.invalidateQueries({ queryKey: ['campaigns'] }), queryClient.invalidateQueries({ queryKey: ['campaign-detail', id] }), queryClient.invalidateQueries({ queryKey: ['home'] })])
      setNotice(kind === 'approve' ? 'Script approval confirmed. The backend queued the media stage.' : 'Retry accepted by the backend. Check the refreshed status.')
      setToken('')
    } catch (reason) { setError(reason instanceof Error ? reason.message : 'Action failed.') }
    finally { setPending(false) }
  }
  return <RightDrawer title="Campaign details" onClose={close} className="workflow-drawer">
    {detail.isPending ? <LoadingRows label="Loading campaign" /> : detail.isError && !campaign ? <DataState title="Campaign unavailable" detail={detail.error.message} retry={() => detail.refetch()} /> : campaign ? <>
      <div className="drawer-identity"><span className="provider-icon"><Megaphone size={24} /></span><div className="drawer-name"><h2>{campaign.topic}</h2><p>{campaign.org_name || 'Organization unavailable'} · {campaign.objective}</p></div></div>
      <div className="drawer-status"><StatusText value={campaign.status} known={campaignStatuses} tone={campaign.status === 'failed' ? 'red' : campaign.status === 'needs_campaign_review' ? 'yellow' : 'blue'} /></div>
      <div className="drawer-tabs"><button aria-selected="true">Overview</button></div>
      <div className="drawer-body"><section className="detail-card"><h3>Campaign goal</h3><p>{campaign.topic}</p><dl className="company-fields"><div><dt>Objective</dt><dd>{campaign.objective}</dd></div><div><dt>Buyer</dt><dd>{campaign.buyer}</dd></div><div><dt>Channels</dt><dd>{[...campaign.social_platforms, campaign.video_platform].join(', ')}</dd></div><div><dt>Current stage</dt><dd>{campaign.current_stage}</dd></div><div><dt>G3 handoff</dt><dd>{campaign.g3_status === 'drafted' ? 'Buffer drafts created; publication unconfirmed' : campaign.g3_status}</dd></div><div><dt>Created</dt><dd><ShortDate value={campaign.created_at} /></dd></div></dl></section>
        {campaign.script_text && <section className="detail-card"><h3>Saved script</h3><p className="workflow-message">{campaign.script_text}</p></section>}
        {campaign.variants.length > 0 && <section className="detail-card"><h3>Video variants</h3><div className="key-list">{campaign.variants.map(variant => <div key={variant.id}><span>{variant.platform}</span><StatusText value={variant.status || ''} known={['queued', 'rendering', 'ready', 'failed']} /></div>)}</div></section>}
        {campaign.error && <div className="operational-error" role="alert">{campaign.error}</div>}
        {campaign.status === 'drafted' && <p className="operational-note">A Buffer draft is not a scheduled or published post.</p>}
      </div>
      <div className="drawer-footer">{(campaign.status === 'needs_campaign_review' || campaign.status === 'failed') && <label className="operational-label">Founder action token<input type="password" aria-label="Founder action token" autoComplete="off" value={token} onChange={event => setToken(event.target.value)} /></label>}
        {error && <p className="form-error" role="alert">{error}</p>}{notice && <p className="success-message" role="status">{notice}</p>}
        <div className="workflow-actions">{campaign.status === 'needs_campaign_review' && campaign.script_available && <button className="button primary" disabled={pending || !campaign.script_text} title={!campaign.script_text ? 'Saved script cannot be read; check campaign storage before approving' : undefined} onClick={() => act('approve')}>Approve saved script</button>}{campaign.status === 'failed' && <button className="button primary" disabled={pending} onClick={() => act('retry')}>Retry failed stage</button>}<Link className="button secondary" to="/content">View content</Link></div>
      </div>
    </> : null}
  </RightDrawer>
}

function CampaignCreate({ close, onCreated }: { close: () => void; onCreated: (id: string) => Promise<void> }) {
  const credentials = useCredentials()
  const [objective, setObjective] = useState('awareness')
  const [brief, setBrief] = useState('')
  const [platforms, setPlatforms] = useState<string[]>(['x'])
  const [voiceMode, setVoiceMode] = useState('tts')
  const [error, setError] = useState('')
  const [pending, setPending] = useState(false)
  async function submit(event: FormEvent<HTMLFormElement>) {
    event.preventDefault(); setError('')
    if (!platforms.length) { setError('Choose at least one social platform.'); return }
    setPending(true)
    try { const result = await createCampaign(credentials, { objective, brief, social_platforms: platforms, video_platform: 'shorts', voice_mode: voiceMode }); if (!result.ok || !result.campaign?.id) throw new Error('Backend did not confirm campaign creation.'); await onCreated(result.campaign.id); close() }
    catch (reason) { setError(reason instanceof Error ? reason.message : 'Campaign creation failed.') }
    finally { setPending(false) }
  }
  return <div className="modal-backdrop" role="presentation"><div className="modal" role="dialog" aria-modal="true" aria-label="New campaign"><button className="modal-close icon-button" onClick={close} aria-label="Close new campaign">×</button><h2>New campaign</h2><p>Creates a campaign in the active organization and starts its backend pipeline.</p><form onSubmit={submit}><label>Objective<input value={objective} onChange={event => setObjective(event.target.value)} minLength={3} maxLength={80} required /></label><label>Brief<textarea value={brief} onChange={event => setBrief(event.target.value)} minLength={10} maxLength={500} required placeholder="Describe the audience, problem, and message." /></label><div className="workflow-checks"><span>Social platforms</span>{['x', 'instagram'].map(value => <label key={value}><input type="checkbox" checked={platforms.includes(value)} onChange={event => setPlatforms(event.target.checked ? [...platforms, value] : platforms.filter(item => item !== value))} />{value}</label>)}</div><label>Voice mode<select value={voiceMode} onChange={event => setVoiceMode(event.target.value)}><option value="tts">Generated voice</option><option value="real_voice">Real voice recording required later</option></select></label>{error && <p className="form-error" role="alert">{error}</p>}<div className="modal-actions"><button type="button" className="button secondary" onClick={close}>Cancel</button><button className="button primary" disabled={pending}>Create campaign</button></div></form></div></div>
}

export function CampaignsPage() {
  const credentials = useCredentials()
  const queryClient = useQueryClient()
  const [params, setParams] = useSearchParams()
  const [creating, setCreating] = useState(false)
  const [notice, setNotice] = useState('')
  const page = Math.max(1, Number(params.get('page')) || 1)
  const q = params.get('q') || ''
  const status = params.get('status') || ''
  const sort = ['recent', 'oldest', 'name'].includes(params.get('sort') || '') ? params.get('sort')! : 'recent'
  const orgId = Number(params.get('org')) || null
  const selected = params.get('campaign')
  const query = useQuery({ queryKey: ['campaigns', page, q, status, sort, orgId], queryFn: () => campaignsPage(credentials, { page, q, status, sort, orgId }), placeholderData: keepPreviousData })
  const result = query.data
  const pages = Math.max(1, Math.ceil((result?.total || 0) / 10))
  function update(changes: Record<string, string | null>) { const next = new URLSearchParams(params); for (const [key, value] of Object.entries(changes)) { if (value) next.set(key, value); else next.delete(key) } setParams(next) }
  const columns = [
    column.display({ id: 'topic', header: 'Campaign', cell: info => <strong>{info.row.original.topic}</strong> }),
    column.display({ id: 'org', header: 'Organization', cell: info => info.row.original.org_name || 'Not recorded' }),
    column.display({ id: 'channels', header: 'Channels', cell: info => <span>{[...info.row.original.social_platforms, info.row.original.video_platform].join(', ')}</span> }),
    column.display({ id: 'status', header: 'Status', cell: info => <StatusText value={info.row.original.status} known={campaignStatuses} tone={info.row.original.status === 'failed' ? 'red' : info.row.original.status === 'needs_campaign_review' ? 'yellow' : 'blue'} /> }),
    column.display({ id: 'stage', header: 'Stage', cell: info => info.row.original.current_stage.replaceAll('_', ' ') }),
    column.display({ id: 'updated', header: 'Updated', cell: info => <ShortDate value={info.row.original.updated_at} /> }),
    column.display({ id: 'action', header: 'Next step', cell: info => <button className="row-action" onClick={event => { event.stopPropagation(); update({ campaign: info.row.original.id }) }}>{info.row.original.status === 'needs_campaign_review' ? 'Review script' : info.row.original.status === 'failed' ? 'Inspect failure' : 'View campaign'}</button> }),
  ]
  return <AppShell active="Campaigns" query={q} onQueryChange={value => update({ q: value, page: '1', campaign: null })}><div className="page-layout"><main className="page-main"><div className="page-content">
    <div className="page-heading"><div><h1>Campaigns</h1><p>Track marketing work from brief to Buffer draft handoff.</p></div><div className="heading-actions"><button className="button primary" onClick={() => setCreating(true)}><Plus size={16} />New campaign</button></div></div>
    <WorkflowMetrics items={[{ label: 'Campaign records', value: result ? Object.values(result.by_status).reduce((a, b) => a + b, 0) : undefined, icon: <Megaphone /> }, { label: 'Script review', value: result ? result.by_status.needs_campaign_review || 0 : undefined, icon: <FileCheck2 /> }, { label: 'Buffer drafts', value: result ? result.by_status.drafted || 0 : undefined, icon: <Send /> }, { label: 'Failed', value: result ? result.by_status.failed || 0 : undefined, icon: <AlertCircle /> }]} />
    {notice && <div className="company-page-notice" role="status">{notice}<button onClick={() => setNotice('')} aria-label="Dismiss message">×</button></div>}
    <div className="table-toolbar"><div className="view-tabs">{tabs.map(tab => <button key={tab.label} className={status === tab.value ? 'active' : ''} onClick={() => update({ status: tab.value, page: '1', campaign: null })}>{tab.label} ({tab.value ? result?.by_status[tab.value] || 0 : Object.values(result?.by_status || {}).reduce((a, b) => a + b, 0)})</button>)}</div><label className="sort-control">Sort <select aria-label="Sort campaigns" value={sort} onChange={event => update({ sort: event.target.value, page: '1' })}><option value="recent">Recently updated</option><option value="oldest">Oldest updated</option><option value="name">Name A–Z</option></select></label></div>
    {query.isError && result && <div className="operational-error" role="alert">Refresh failed: {query.error.message} <button onClick={() => query.refetch()}>Retry</button></div>}
    <div className="table-panel">{query.isPending ? <LoadingRows label="Loading campaigns" /> : query.isError && !result ? <DataState title="Campaigns could not be loaded" detail={query.error.message} retry={() => query.refetch()} /> : result?.items.length ? <WorkflowTable items={result.items} columns={columns} selected={selected} onSelect={id => update({ campaign: id })} /> : <DataState title="No campaigns found" detail={q || status ? 'Try another search or status.' : 'Create a campaign once an organization is active.'} />}</div>
    <div className="table-footer"><span>{result ? `Showing ${result.total ? (page - 1) * 10 + 1 : 0}–${Math.min(page * 10, result.total)} of ${result.total} campaigns` : 'Loading campaigns…'}{query.isFetching && !query.isPending && ' · Refreshing…'}</span><div className="pagination"><button aria-label="Previous page" disabled={page <= 1} onClick={() => update({ page: String(page - 1), campaign: null })}><ChevronLeft size={17} /></button><span>{page} of {pages}</span><button aria-label="Next page" disabled={page >= pages} onClick={() => update({ page: String(page + 1), campaign: null })}><ChevronRight size={17} /></button></div></div>
  </div></main>{selected && <CampaignDrawer key={selected} id={selected} close={() => update({ campaign: null })} />}{creating && <CampaignCreate close={() => setCreating(false)} onCreated={async id => { await queryClient.invalidateQueries({ queryKey: ['campaigns'] }); await queryClient.invalidateQueries({ queryKey: ['home'] }); update({ campaign: id, page: '1', q: null, status: null, org: null }); setNotice('Campaign accepted by the backend. The pipeline is running; no publication is implied.') }} />}</div></AppShell>
}
