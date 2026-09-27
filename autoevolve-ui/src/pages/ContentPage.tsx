import { useEffect, useMemo, useState, type FormEvent } from 'react'
import { useQuery, useQueryClient } from '@tanstack/react-query'
import { createColumnHelper } from '@tanstack/react-table'
import { useSearchParams } from 'react-router-dom'
import { ChevronLeft, ChevronRight, FileImage, Layers3, Plus, Send, Video } from 'lucide-react'
import { assetBlob, bufferAccounts, bufferInsights, contentView, createAssetPack, createManualPost, scheduleManualPost, type ContentItem } from '../api/workflows'
import { useCredentials } from '../app/Auth'
import { AppShell } from '../components/Shell'
import { DataState, LoadingRows, RightDrawer } from '../components/Primitives'
import { ShortDate, StatusText, WorkflowMetrics, WorkflowTable } from '../components/WorkflowTable'

const postStages = ['saved', 'uploading', 'ready', 'buffer_draft', 'scheduled', 'failed']
const packStages = ['queued', 'running', 'ready', 'failed']
const bufferStates = ['not_started', 'drafted', 'queued', 'running', 'scheduled', 'failed']
const column = createColumnHelper<ContentItem>()

function AssetPreview({ path }: { path: string }) {
  const credentials = useCredentials()
  const result = useQuery({ queryKey: ['content-asset', path], queryFn: () => assetBlob(credentials, path), staleTime: 60_000 })
  const [url, setUrl] = useState<string | null>(null)
  useEffect(() => {
    if (!result.data) return
    const objectUrl = URL.createObjectURL(result.data)
    setUrl(objectUrl)
    return () => URL.revokeObjectURL(objectUrl)
  }, [result.data])
  return result.isError ? <span className="asset-fallback">Preview unavailable</span> : url ? result.data?.type.startsWith('video/') ? <video src={url} controls aria-label="Saved content video" /> : <img src={url} alt="Saved content asset" /> : <span className="asset-fallback">Loading preview…</span>
}

function ContentDrawer({ item, close }: { item: ContentItem; close: () => void }) {
  const credentials = useCredentials()
  const queryClient = useQueryClient()
  const [token, setToken] = useState('')
  const [mode, setMode] = useState<'queue' | 'next' | 'timed'>('queue')
  const [dueAt, setDueAt] = useState('')
  const [account, setAccount] = useState('')
  const [postId, setPostId] = useState('')
  const [error, setError] = useState('')
  const [notice, setNotice] = useState('')
  const [pending, setPending] = useState(false)
  const maySchedule = item.kind === 'manual_post' && ['ready', 'buffer_draft'].includes(item.stage) && !['queued', 'running', 'scheduled'].includes(item.buffer_status || '')
  const accounts = useQuery({ queryKey: ['buffer-accounts'], queryFn: () => bufferAccounts(credentials), enabled: maySchedule, staleTime: 60_000 })
  const selectedAccount = account || accounts.data?.accounts[0]?.name || 'default'
  const selectedPostId = postId || item.buffer_post_ids[0] || ''
  const insights = useQuery({ queryKey: ['buffer-insights', item.id, selectedPostId], queryFn: () => bufferInsights(credentials, item.id, selectedPostId), enabled: item.kind === 'manual_post' && !!selectedPostId, retry: false, staleTime: 60_000 })
  async function schedule(event: FormEvent<HTMLFormElement>) {
    event.preventDefault(); setError(''); setNotice('')
    if (!maySchedule) { setError('This post is not ready to schedule.'); return }
    if (!token.trim()) { setError('Enter the founder action token.'); return }
    if (mode === 'timed' && !dueAt) { setError('Choose a date and time.'); return }
    setPending(true)
    try {
      const response = await scheduleManualPost(credentials, item.id, mode, mode === 'timed' ? new Date(dueAt).toISOString() : null, token, selectedAccount)
      if (!response.ok || response.post.buffer_status !== 'scheduled') throw new Error('Backend did not confirm Buffer scheduling. Refresh and inspect the post before trying again.')
      await Promise.all([queryClient.invalidateQueries({ queryKey: ['content'] }), queryClient.invalidateQueries({ queryKey: ['home'] }), queryClient.invalidateQueries({ queryKey: ['buffer-insights', item.id] })])
      setNotice('Buffer scheduling confirmed by the backend. Publication is not confirmed.')
      setToken('')
    } catch (reason) { setError(reason instanceof Error ? reason.message : 'Scheduling failed.') }
    finally { setPending(false) }
  }
  return <RightDrawer title="Content details" onClose={close} className="workflow-drawer">
    <div className="drawer-identity"><span className="provider-icon"><FileImage size={24} /></span><div className="drawer-name"><h2>{item.title}</h2><p>{item.org_name || 'Organization unavailable'} · {item.kind === 'manual_post' ? 'Manual post' : 'Asset pack'}</p></div></div>
    <div className="drawer-status"><StatusText value={item.stage} known={item.kind === 'manual_post' ? postStages : packStages} tone={item.stage === 'failed' ? 'red' : item.stage === 'scheduled' || item.stage === 'ready' ? 'green' : 'blue'} /></div>
    {notice && <p className="success-message" role="status">{notice}</p>}
    <div className="drawer-tabs"><button aria-selected="true">Overview</button></div>
    <div className="drawer-body"><section className="detail-card"><h3>Saved content</h3><dl className="company-fields"><div><dt>Type</dt><dd>{item.kind.replaceAll('_', ' ')}</dd></div><div><dt>Format</dt><dd>{item.format}</dd></div><div><dt>Platform</dt><dd>{item.platform || 'Not recorded'}</dd></div><div><dt>Assets</dt><dd>{item.asset_count}</dd></div><div><dt>Updated</dt><dd><ShortDate value={item.updated_at} /></dd></div>{item.kind === 'manual_post' && <div><dt>Buffer</dt><dd><StatusText value={item.buffer_status || 'not_started'} known={bufferStates} /></dd></div>}</dl></section>
      {item.caption && <section className="detail-card"><h3>{item.kind === 'manual_post' ? 'Caption / creative' : 'Source excerpt'}</h3><p className="workflow-message">{item.caption}</p></section>}
      {item.asset_urls.length > 0 && <section className="detail-card"><h3>Assets</h3><div className="content-preview-grid">{item.asset_urls.slice(0, 6).map(path => <AssetPreview key={path} path={path} />)}</div>{item.asset_urls.length > 6 && <p className="operational-note">Showing 6 of {item.asset_urls.length} assets.</p>}</section>}
      {item.kind === 'manual_post' && item.buffer_post_ids.length > 0 && <section className="detail-card"><h3>Buffer post insights</h3><p className="operational-note">Live, experimental provider read using a personal Buffer API key. Metrics can be delayed or unavailable.</p>{item.buffer_post_ids.length > 1 && <label className="operational-label">Buffer post<select value={selectedPostId} onChange={event => setPostId(event.target.value)}>{item.buffer_post_ids.map(id => <option key={id} value={id}>{id}</option>)}</select></label>}{insights.isPending ? <p className="operational-note">Loading provider status…</p> : insights.isError ? <p className="form-error" role="alert">Insights unavailable: {insights.error.message}</p> : insights.data && <><dl className="company-fields"><div><dt>Provider state</dt><dd><StatusText value={insights.data.status} known={['draft', 'scheduled', 'sent', 'error', 'pending']} tone={insights.data.status === 'sent' ? 'green' : insights.data.status === 'error' ? 'red' : 'blue'} /></dd></div><div><dt>Account</dt><dd>{insights.data.buffer_account}</dd></div><div><dt>Due</dt><dd><ShortDate value={insights.data.due_at} /></dd></div><div><dt>Metrics refreshed</dt><dd><ShortDate value={insights.data.metrics_updated_at} /></dd></div></dl>{insights.data.external_link?.startsWith('https://') && <a className="contact-link" href={insights.data.external_link} target="_blank" rel="noreferrer">Open provider post</a>}{insights.data.metrics?.length ? <div className="buffer-metrics">{insights.data.metrics.map(metric => <div key={metric.type}><span>{metric.name}</span><strong>{metric.value.toLocaleString()}{metric.unit === 'percentage' ? '%' : ''}</strong></div>)}</div> : <p className="operational-note">No provider metrics are available for this post.</p>}</>}</section>}
      {item.kind === 'manual_post' && <p className="operational-note">A Buffer draft or scheduled post does not confirm publication.</p>}
    </div>
    {maySchedule && <div className="drawer-footer"><form className="workflow-form" onSubmit={schedule}><h3>Schedule in Buffer</h3><label>Account<select aria-label="Buffer account" value={selectedAccount} onChange={event => setAccount(event.target.value)}>{accounts.data?.accounts.length ? accounts.data.accounts.map(value => <option key={value.name} value={value.name}>{value.name}{item.platform === 'x' && !value.x_channel_id || item.platform === 'instagram' && !value.instagram_channel_id ? ' · channel unconfigured' : ''}</option>) : <option value="default">default</option>}</select></label>{accounts.data?.error && <p className="form-error" role="alert">Buffer configuration: {accounts.data.error}</p>}{accounts.isError && <p className="form-error" role="alert">Buffer accounts could not be loaded: {accounts.error.message}</p>}<label>Mode<select value={mode} onChange={event => setMode(event.target.value as 'queue' | 'next' | 'timed')}><option value="queue">Queue</option><option value="next">Next slot</option><option value="timed">Specific time</option></select></label>{mode === 'timed' && <label>Date and time<input type="datetime-local" value={dueAt} onChange={event => setDueAt(event.target.value)} required /></label>}<label>Founder action token<input type="password" aria-label="Founder action token" autoComplete="off" value={token} onChange={event => setToken(event.target.value)} /></label>{error && <p className="form-error" role="alert">{error}</p>}<button className="button primary" disabled={pending || accounts.isPending || accounts.isError || !!accounts.data?.error}>Schedule post</button></form></div>}
  </RightDrawer>
}

function AssetPackCreate({ close, created }: { close: () => void; created: () => Promise<void> }) {
  const credentials = useCredentials()
  const [script, setScript] = useState('')
  const [objective, setObjective] = useState('awareness')
  const [error, setError] = useState('')
  const [pending, setPending] = useState(false)
  async function submit(event: FormEvent<HTMLFormElement>) {
    event.preventDefault(); setError(''); setPending(true)
    try {
      const response = await createAssetPack(credentials, { script, objective })
      if (!response.ok || response.pack.status !== 'queued') throw new Error('Backend did not confirm that the asset pack was queued.')
      await created(); close()
    } catch (reason) { setError(reason instanceof Error ? reason.message : 'Asset pack creation failed.') }
    finally { setPending(false) }
  }
  return <div className="modal-backdrop" role="presentation"><div className="modal" role="dialog" aria-modal="true" aria-label="New asset pack"><button className="modal-close icon-button" onClick={close} aria-label="Close new asset pack">×</button><h2>New asset pack</h2><p>Queue assets for the active organization from a real script.</p><form onSubmit={submit}><label>Objective<input value={objective} onChange={event => setObjective(event.target.value)} minLength={3} maxLength={80} required /></label><label>Script<textarea value={script} onChange={event => setScript(event.target.value)} minLength={20} maxLength={12000} required placeholder="Enter the source script for image research and asset generation." /></label>{error && <p className="form-error" role="alert">{error}</p>}<div className="modal-actions"><button type="button" className="button secondary" onClick={close}>Cancel</button><button className="button primary" disabled={pending}>Queue asset pack</button></div></form></div></div>
}

function ManualPostCreate({ close, created }: { close: () => void; created: () => Promise<void> }) {
  const credentials = useCredentials()
  const [platform, setPlatform] = useState<'instagram' | 'x' | 'linkedin'>('instagram')
  const [postType, setPostType] = useState<'carousel' | 'video'>('carousel')
  const [destinationUrl, setDestinationUrl] = useState('')
  const [linkLabel, setLinkLabel] = useState('')
  const [assets, setAssets] = useState<File[]>([])
  const [error, setError] = useState('')
  const [pending, setPending] = useState(false)
  async function submit(event: FormEvent<HTMLFormElement>) {
    event.preventDefault(); setError('')
    if (!assets.length) { setError('Select at least one media file.'); return }
    if (postType === 'video' && assets.length !== 1) { setError('Video posts require exactly one MP4 file.'); return }
    setPending(true)
    try {
      const result = await createManualPost(credentials, { platform, postType, destinationUrl, linkLabel, assets })
      if (!result.ok || result.post.workflow_status !== 'ready') throw new Error('The backend did not confirm a ready manual post.')
      await created(); close()
    } catch (reason) { setError(reason instanceof Error ? reason.message : 'Manual post could not be saved.') }
    finally { setPending(false) }
  }
  return <div className="modal-backdrop" role="presentation"><div className="modal" role="dialog" aria-modal="true" aria-label="New manual post"><button className="modal-close icon-button" onClick={close} aria-label="Close new manual post">×</button><h2>New manual post</h2><p>Save uploaded media and a backend-generated caption. Buffer scheduling is a separate action.</p><form onSubmit={submit}>
    <label>Platform<select value={platform} onChange={event => setPlatform(event.target.value as typeof platform)}><option value="instagram">Instagram</option><option value="x">X</option><option value="linkedin">LinkedIn</option></select></label>
    <label>Format<select value={postType} onChange={event => { setPostType(event.target.value as typeof postType); setAssets([]) }}><option value="carousel">Carousel · PNG</option><option value="video">Video · MP4</option></select></label>
    <label>Media<input type="file" accept={postType === 'video' ? '.mp4,video/mp4' : '.png,image/png'} multiple={postType === 'carousel'} onChange={event => setAssets(Array.from(event.target.files || []))} required /></label>
    <label>Destination URL<input type="url" value={destinationUrl} onChange={event => setDestinationUrl(event.target.value)} /></label>
    <label>CTA label<input value={linkLabel} onChange={event => setLinkLabel(event.target.value)} maxLength={80} /></label>
    {error && <p className="form-error" role="alert">{error}</p>}<div className="modal-actions"><button type="button" className="button secondary" onClick={close}>Cancel</button><button className="button primary" disabled={pending}>Save manual post</button></div>
  </form></div></div>
}

export function ContentPage() {
  const credentials = useCredentials()
  const queryClient = useQueryClient()
  const [params, setParams] = useSearchParams()
  const [creating, setCreating] = useState(false)
  const [creatingPost, setCreatingPost] = useState(false)
  const [notice, setNotice] = useState('')
  const q = params.get('q') || ''
  const kind = params.get('kind') || ''
  const stage = params.get('stage') || ''
  const selected = params.get('item')
  const page = Math.max(1, Number(params.get('page')) || 1)
  const query = useQuery({ queryKey: ['content'], queryFn: () => contentView(credentials) })
  const data = query.data
  const filtered = useMemo(() => (data?.items || []).filter(item => (!kind || item.kind === kind) && (!stage || item.stage === stage) && (!q || `${item.title} ${item.caption || ''} ${item.org_name || ''}`.toLowerCase().includes(q.toLowerCase()))), [data, kind, stage, q])
  const items = filtered.slice((page - 1) * 10, page * 10)
  const pages = Math.max(1, Math.ceil(filtered.length / 10))
  const chosen = data?.items.find(item => `${item.kind}:${item.id}` === selected)
  function update(changes: Record<string, string | null>) { const next = new URLSearchParams(params); for (const [key, value] of Object.entries(changes)) { if (value) next.set(key, value); else next.delete(key) } setParams(next) }
  const columns = [
    column.display({ id: 'title', header: 'Content', cell: info => <strong>{info.row.original.title}</strong> }),
    column.display({ id: 'kind', header: 'Type', cell: info => info.row.original.kind.replaceAll('_', ' ') }),
    column.display({ id: 'format', header: 'Format', cell: info => info.row.original.format }),
    column.display({ id: 'org', header: 'Organization', cell: info => info.row.original.org_name || 'Not recorded' }),
    column.display({ id: 'stage', header: 'Stage', cell: info => <StatusText value={info.row.original.stage} known={info.row.original.kind === 'manual_post' ? postStages : packStages} tone={info.row.original.stage === 'failed' ? 'red' : info.row.original.stage === 'scheduled' ? 'green' : 'blue'} /> }),
    column.display({ id: 'assets', header: 'Assets', cell: info => info.row.original.asset_count }),
    column.display({ id: 'updated', header: 'Updated', cell: info => <ShortDate value={info.row.original.updated_at} /> }),
    column.display({ id: 'action', header: 'Action', cell: info => <button className="row-action" onClick={event => { event.stopPropagation(); update({ item: info.row.original.id }) }}>View content</button> }),
  ]
  return <AppShell active="Content" query={q} onQueryChange={value => update({ q: value, page: '1', item: null })}><div className="page-layout"><main className="page-main"><div className="page-content">
    <div className="page-heading"><div><h1>Content</h1><p>Review saved posts and assets. Scheduling and publication are separate states.</p></div><div className="heading-actions"><button className="button secondary" onClick={() => setCreatingPost(true)}><Plus size={16} />New manual post</button><button className="button primary" onClick={() => setCreating(true)}><Plus size={16} />New asset pack</button></div></div>
    <WorkflowMetrics items={[{ label: 'Manual posts loaded', value: data?.manual_posts_loaded, icon: <FileImage /> }, { label: 'Asset packs loaded', value: data?.asset_packs_loaded, icon: <Layers3 /> }, { label: 'Buffer drafts loaded', value: data?.items.filter(item => item.kind === 'manual_post' && item.stage === 'buffer_draft').length, icon: <Video /> }, { label: 'Scheduled loaded', value: data?.items.filter(item => item.kind === 'manual_post' && item.stage === 'scheduled').length, icon: <Send /> }]} />
    {notice && <div className="company-page-notice" role="status">{notice}<button onClick={() => setNotice('')} aria-label="Dismiss message">×</button></div>}
    {(data?.manual_posts_truncated || data?.asset_packs_truncated) && <div className="operational-footnote">This view contains the latest {data.manual_posts_loaded} manual posts and {data.asset_packs_loaded} asset packs. Filters and counts apply to loaded records.</div>}
    <div className="table-toolbar"><div className="view-tabs"><button className={!kind ? 'active' : ''} onClick={() => update({ kind: null, page: '1', item: null })}>All</button><button className={kind === 'manual_post' ? 'active' : ''} onClick={() => update({ kind: 'manual_post', page: '1', item: null })}>Manual posts</button><button className={kind === 'asset_pack' ? 'active' : ''} onClick={() => update({ kind: 'asset_pack', page: '1', item: null })}>Asset packs</button></div><label className="sort-control">Stage <select aria-label="Filter content stage" value={stage} onChange={event => update({ stage: event.target.value, page: '1', item: null })}><option value="">All stages</option>{[...new Set(data?.items.map(item => item.stage) || [])].map(value => <option value={value} key={value}>{value.replaceAll('_', ' ')}</option>)}</select></label></div>
    {query.isError && data && <div className="operational-error" role="alert">Refresh failed: {query.error.message} <button onClick={() => query.refetch()}>Retry</button></div>}
    <div className="table-panel">{query.isPending ? <LoadingRows label="Loading content" /> : query.isError && !data ? <DataState title="Content could not be loaded" detail={query.error.message} retry={() => query.refetch()} /> : items.length ? <WorkflowTable items={items.map(item => ({ ...item, id: `${item.kind}:${item.id}` }))} columns={columns} selected={selected} onSelect={id => update({ item: id })} /> : <DataState title="No content found" detail={q || kind || stage ? 'Try another filter.' : 'Create a manual post or asset pack.'} />}</div>
    <div className="table-footer"><span>{data ? `Showing ${filtered.length ? (page - 1) * 10 + 1 : 0}–${Math.min(page * 10, filtered.length)} of ${filtered.length} loaded records` : 'Loading content…'}</span><div className="pagination"><button aria-label="Previous page" disabled={page <= 1} onClick={() => update({ page: String(page - 1), item: null })}><ChevronLeft size={17} /></button><span>{page} of {pages}</span><button aria-label="Next page" disabled={page >= pages} onClick={() => update({ page: String(page + 1), item: null })}><ChevronRight size={17} /></button></div></div>
  </div></main>{chosen && <ContentDrawer key={selected} item={chosen} close={() => update({ item: null })} />}{creating && <AssetPackCreate close={() => setCreating(false)} created={async () => { await queryClient.invalidateQueries({ queryKey: ['content'] }); update({ q: null, kind: null, stage: null, page: '1', item: null }); setNotice('Asset pack queued by the backend. Assets are not ready yet.') }} />}{creatingPost && <ManualPostCreate close={() => setCreatingPost(false)} created={async () => { await queryClient.invalidateQueries({ queryKey: ['content'] }); update({ q: null, kind: null, stage: null, page: '1', item: null }); setNotice('Manual post saved and ready. It has not been scheduled or published.') }} />}</div></AppShell>
}
