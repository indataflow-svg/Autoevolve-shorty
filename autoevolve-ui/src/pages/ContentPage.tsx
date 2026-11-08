import { useEffect, useMemo, useState, type FormEvent } from 'react'
import { useQuery, useQueryClient } from '@tanstack/react-query'
import { createColumnHelper } from '@tanstack/react-table'
import { useSearchParams } from 'react-router-dom'
import { ChevronLeft, ChevronRight, FileImage, Plus, Send, Video } from 'lucide-react'
import { assetBlob, confirmManualPublish, contentView, createManualPost, previewManualPost, publisherAccounts, publishersView, publishInsights, publishJob, publishManualPostAsync, type ContentItem } from '../api/workflows'
import { useAuthSession, useCredentials } from '../app/Auth'
import { AppShell } from '../components/Shell'
import { DataState, LoadingRows, RightDrawer, StateBadge } from '../components/Primitives'
import { ShortDate, StatusText, WorkflowMetrics, WorkflowTable } from '../components/WorkflowTable'

const postStages = ['saved', 'uploading', 'ready', 'buffer_draft', 'scheduled', 'failed']
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

type SendConfirmationPost = { verdict?: string; status?: string; buffer_account?: string; external_link?: string; error?: string }
type SendConfirmation = { overall: string; checked_at: string; posts: Record<string, SendConfirmationPost> }

function readSendConfirmation(value: unknown): SendConfirmation | null {
  if (!value || typeof value !== 'object') return null
  const record = value as Record<string, unknown>
  if (typeof record.overall !== 'string' || typeof record.checked_at !== 'string' || !record.posts || typeof record.posts !== 'object') return null
  return record as unknown as SendConfirmation
}

function ContentDrawer({ item, close }: { item: ContentItem; close: () => void }) {
  const credentials = useCredentials()
  const session = useAuthSession()
  const queryClient = useQueryClient()
  const [token, setToken] = useState('')
  const [mode, setMode] = useState<'queue' | 'next' | 'timed'>('queue')
  const [dueAt, setDueAt] = useState('')
  const [account, setAccount] = useState('')
  const [postId, setPostId] = useState('')
  const [error, setError] = useState('')
  const [notice, setNotice] = useState('')
  const [pending, setPending] = useState(false)
  const [confirming, setConfirming] = useState(false)
  const [confirmError, setConfirmError] = useState('')
  const sendConfirmation = item.kind === 'manual_post' ? readSendConfirmation(item.send_confirmation) : null
  const publisher = item.publisher || 'buffer'
  const publishers = useQuery({ queryKey: ['publishers'], queryFn: () => publishersView(credentials), staleTime: 60_000 })
  const publisherInfo = publishers.data?.publishers.find(value => value.name === publisher)
  const capabilities = publisherInfo?.capabilities
  const publisherLabel = publisherInfo?.label || publisher
  const postIds = item.publisher_post_ids?.length ? item.publisher_post_ids : item.buffer_post_ids
  async function runConfirm() {
    setConfirmError('')
    if (item.kind !== 'manual_post') return
    if (!session && !token.trim()) { setConfirmError('Enter the founder action token.'); return }
    setConfirming(true)
    try {
      const response = await confirmManualPublish(credentials, item.id, token.trim())
      if (!response.ok) throw new Error('Backend did not confirm the send status.')
      await queryClient.invalidateQueries({ queryKey: ['content'] })
      setToken('')
    } catch (reason) { setConfirmError(reason instanceof Error ? reason.message : 'Send check failed.') }
    finally { setConfirming(false) }
  }
  const maySchedule = item.kind === 'manual_post' && ['ready', 'buffer_draft'].includes(item.stage) && Boolean(capabilities?.schedule) && !['queued', 'running', 'scheduled'].includes(item.publisher_status || item.buffer_status || '')
  const accounts = useQuery({ queryKey: ['publisher-accounts', publisher], queryFn: () => publisherAccounts(credentials, publisher), enabled: maySchedule, staleTime: 60_000 })
  const accountNames = (accounts.data?.accounts || []).map(item => item.name)
  const preferredAccount = item.kind === 'manual_post' && item.publisher_account && accountNames.includes(item.publisher_account) ? item.publisher_account : ''
  const selectedAccount = account || preferredAccount || accounts.data?.accounts[0]?.name || 'default'
  const selectedPostId = postId || postIds[0] || ''
  const insights = useQuery({ queryKey: ['publish-insights', publisher, item.id, selectedPostId], queryFn: () => publishInsights(credentials, item.id, selectedPostId), enabled: item.kind === 'manual_post' && Boolean(capabilities?.insights) && !!selectedPostId, retry: false, staleTime: 60_000 })
  async function schedule(event: FormEvent<HTMLFormElement>) {
    event.preventDefault(); setError(''); setNotice('')
    if (!maySchedule) { setError('This post is not ready to schedule.'); return }
    if (!session && !token.trim()) { setError('Enter the founder action token.'); return }
    if (mode === 'timed' && !dueAt) { setError('Choose a date and time.'); return }
    setPending(true)
    try {
      const queued = await publishManualPostAsync(credentials, item.id, { mode, dueAt: mode === 'timed' ? new Date(dueAt).toISOString() : null, account: selectedAccount, token })
      if (!queued.ok || !queued.job?.id) throw new Error('Backend did not queue the publish job.')
      let job = queued.job
      for (let attempt = 0; attempt < 240 && ['queued', 'running'].includes(job.status); attempt += 1) {
        await new Promise(resolve => window.setTimeout(resolve, 1000))
        job = await publishJob(credentials, job.id)
      }
      if (job.status !== 'completed') {
        throw new Error(job.error || `Publish job ended as ${job.status}. Refresh and inspect the post before retrying.`)
      }
      await Promise.all([queryClient.invalidateQueries({ queryKey: ['content'] }), queryClient.invalidateQueries({ queryKey: ['home'] }), queryClient.invalidateQueries({ queryKey: ['publish-insights'] })])
      setNotice(`${publisherLabel} scheduling confirmed by the backend. Publication is not confirmed.`)
      setToken('')
    } catch (reason) { setError(reason instanceof Error ? reason.message : 'Scheduling failed.') }
    finally { setPending(false) }
  }
  return <RightDrawer title="Content details" onClose={close} className="workflow-drawer">
    <div className="drawer-identity"><span className="provider-icon"><FileImage size={24} /></span><div className="drawer-name"><h2>{item.title}</h2><p>{item.org_name || 'Organization unavailable'} · Manual post</p></div></div>
    <div className="drawer-status"><StatusText value={item.stage} known={postStages} tone={item.stage === 'failed' ? 'red' : item.stage === 'scheduled' || item.stage === 'ready' ? 'green' : 'blue'} /></div>
    {notice && <p className="success-message" role="status">{notice}</p>}
    <div className="drawer-tabs"><button aria-selected="true">Overview</button></div>
    <div className="drawer-body"><section className="detail-card"><h3>Saved content</h3><dl className="company-fields"><div><dt>Type</dt><dd>{item.kind.replaceAll('_', ' ')}</dd></div><div><dt>Format</dt><dd>{item.format}</dd></div><div><dt>Platform</dt><dd>{item.platform || 'Not recorded'}</dd></div><div><dt>Assets</dt><dd>{item.asset_count}</dd></div><div><dt>Updated</dt><dd><ShortDate value={item.updated_at} /></dd></div>{item.kind === 'manual_post' && <div><dt>Publisher</dt><dd><StatusText value={item.buffer_status || 'not_started'} known={bufferStates} /></dd></div>}</dl></section>
      {item.caption && <section className="detail-card"><h3>Caption / creative</h3><p className="workflow-message">{item.caption}</p></section>}
      {item.asset_urls.length > 0 && <section className="detail-card"><h3>Assets</h3><div className="content-preview-grid">{item.asset_urls.slice(0, 6).map(path => <AssetPreview key={path} path={path} />)}</div>{item.asset_urls.length > 6 && <p className="operational-note">Showing 6 of {item.asset_urls.length} assets.</p>}</section>}
      {item.kind === 'manual_post' && postIds.length > 0 && <section className="detail-card"><h3>Provider post insights</h3><p className="operational-note">Live, experimental provider read. Metrics can be delayed or unavailable.</p>{postIds.length > 1 && <label className="operational-label">Buffer post<select value={selectedPostId} onChange={event => setPostId(event.target.value)}>{postIds.map(id => <option key={id} value={id}>{id}</option>)}</select></label>}{insights.isPending ? <p className="operational-note">Loading provider status…</p> : insights.isError ? <p className="form-error" role="alert">Insights unavailable: {insights.error.message}</p> : insights.data && <><dl className="company-fields"><div><dt>Provider state</dt><dd><StatusText value={insights.data.status} known={['draft', 'scheduled', 'sent', 'error', 'pending']} tone={insights.data.status === 'sent' ? 'green' : insights.data.status === 'error' ? 'red' : 'blue'} /></dd></div><div><dt>Account</dt><dd>{insights.data.buffer_account}</dd></div><div><dt>Due</dt><dd><ShortDate value={insights.data.due_at} /></dd></div><div><dt>Metrics refreshed</dt><dd><ShortDate value={insights.data.metrics_updated_at} /></dd></div></dl>{insights.data.external_link?.startsWith('https://') && <a className="contact-link" href={insights.data.external_link} target="_blank" rel="noreferrer">Open provider post</a>}{insights.data.metrics?.length ? <div className="buffer-metrics">{insights.data.metrics.map(metric => <div key={metric.type}><span>{metric.name}</span><strong>{metric.value.toLocaleString()}{metric.unit === 'percentage' ? '%' : ''}</strong></div>)}</div> : <p className="operational-note">No provider metrics are available for this post.</p>}</>}</section>}
      {item.kind === 'manual_post' && (postIds.length > 0 || sendConfirmation) && <section className="detail-card"><h3>Send confirmation</h3>{sendConfirmation ? <><dl className="company-fields"><div><dt>Provider verdict</dt><dd><StatusText value={sendConfirmation.overall} known={['sent', 'failed', 'pending', 'unknown']} tone={sendConfirmation.overall === 'sent' ? 'green' : sendConfirmation.overall === 'failed' ? 'red' : 'blue'} /></dd></div><div><dt>Checked</dt><dd><ShortDate value={sendConfirmation.checked_at} /></dd></div></dl><div className="key-list">{Object.entries(sendConfirmation.posts).map(([postId, entry]) => <div key={postId}><code>{postId}</code><StateBadge tone={entry.verdict === 'sent' ? 'green' : entry.verdict === 'failed' ? 'red' : 'blue'}>{entry.verdict || 'pending'} · {entry.status || 'unknown'}</StateBadge>{entry.error ? <small className="muted-copy break-value">{entry.error}</small> : <small className="muted-copy break-value">{entry.buffer_account || ''}{entry.external_link?.startsWith('https://') ? ` · ${entry.external_link}` : ''}</small>}</div>)}</div><p className="operational-note">Only an explicit sent counts as sent. This never changes the local scheduled record.</p></> : <p className="operational-note">Scheduled on our side — Buffer has not confirmed anything yet.</p>}<div className="operational-actions"><button className="button secondary" type="button" onClick={() => void runConfirm()} disabled={confirming}>{confirming ? 'Checking…' : 'Check send status'}</button></div>{confirmError && <p className="form-error" role="alert">{confirmError}</p>}</section>}
      {item.kind === 'manual_post' && <p className="operational-note">A provider draft or scheduled post does not confirm publication.</p>}
    </div>
    {maySchedule && <div className="drawer-footer"><form className="workflow-form" onSubmit={schedule}><h3>Schedule with {publisherLabel}</h3><label>Account<select aria-label="Publisher account" value={selectedAccount} onChange={event => setAccount(event.target.value)}>{accounts.data?.accounts.length ? accounts.data.accounts.map(value => <option key={value.name} value={value.name}>{value.label}{value.platforms.includes(item.platform || '') ? '' : ' · platform unconfigured'}</option>) : <option value="default">default</option>}</select></label>{accounts.data?.error && <p className="form-error" role="alert">Publisher configuration: {accounts.data.error}</p>}{accounts.isError && <p className="form-error" role="alert">Publisher accounts could not be loaded: {accounts.error.message}</p>}<label>Mode<select value={mode} onChange={event => setMode(event.target.value as 'queue' | 'next' | 'timed')}><option value="queue">Queue</option><option value="next">Next slot</option><option value="timed">Specific time</option></select></label>{mode === 'timed' && <label>Date and time<input type="datetime-local" value={dueAt} onChange={event => setDueAt(event.target.value)} required /></label>}{!session && <label>Founder action token<input type="password" aria-label="Founder action token" autoComplete="off" value={token} onChange={event => setToken(event.target.value)} /></label>}{error && <p className="form-error" role="alert">{error}</p>}<button className="button primary" disabled={pending || accounts.isPending || accounts.isError || !!accounts.data?.error}>Schedule post</button></form></div>}
  </RightDrawer>
}

function ManualPostCreate({ close, created }: { close: () => void; created: () => Promise<void> }) {
  const credentials = useCredentials()
  const session = useAuthSession()
  const [platform, setPlatform] = useState<'instagram' | 'x' | 'linkedin'>('instagram')
  const [postType, setPostType] = useState<'carousel' | 'video'>('carousel')
  const [destinationUrl, setDestinationUrl] = useState('')
  const [linkLabel, setLinkLabel] = useState('')
  const [assets, setAssets] = useState<File[]>([])
  const [error, setError] = useState('')
  const [pending, setPending] = useState(false)
  // Debounce the inputs that shape the preview so typing a URL is not one request per key.
  const [previewInput, setPreviewInput] = useState({ platform, postType, destinationUrl, linkLabel })
  useEffect(() => {
    const timer = window.setTimeout(() => setPreviewInput({ platform, postType, destinationUrl, linkLabel }), 350)
    return () => window.clearTimeout(timer)
  }, [platform, postType, destinationUrl, linkLabel])
  const filenames = assets.map(asset => asset.name)
  const publishers = useQuery({ queryKey: ['publishers'], queryFn: () => publishersView(credentials), staleTime: 60_000, retry: false })
  const [publisher, setPublisher] = useState('buffer')
  useEffect(() => {
    const available = publishers.data?.publishers
    if (available?.length && !available.some(item => item.name === publisher)) setPublisher(available[0]!.name)
  }, [publisher, publishers.data])
  const publisherChoices = publishers.data?.publishers ?? (session ? [] : [{ name: 'buffer', label: 'Buffer', capabilities: { draft: true, schedule: true, confirm: true, insights: true, platforms: ['instagram', 'x', 'linkedin'] } }])
  const noPublisher = publisherChoices.length === 0
  const publisherInfo = publisherChoices.find(item => item.name === publisher)
  const platforms = useMemo(() => publisherInfo?.capabilities.platforms ?? ['instagram', 'x', 'linkedin'], [publisherInfo])
  useEffect(() => {
    if (platforms.length && !platforms.includes(platform)) {
      setPlatform(platforms[0] as typeof platform)
    }
  }, [platforms, platform])
  const accounts = useQuery({ queryKey: ['publisher-accounts', publisher], queryFn: () => publisherAccounts(credentials, publisher), staleTime: 60_000, retry: false })
  const availableAccounts = accounts.data?.accounts || []
  const [bufferAccount, setBufferAccount] = useState('')
  const effectiveAccount = bufferAccount || availableAccounts[0]?.name || 'default'
  const selectedAccount = availableAccounts.find(item => item.name === effectiveAccount)
  const preview = useQuery({
    queryKey: ['manual-post-preview', previewInput.platform, previewInput.postType, previewInput.destinationUrl, previewInput.linkLabel, filenames.join('|')],
    queryFn: () => previewManualPost(credentials, { platform: previewInput.platform, postType: previewInput.postType, destinationUrl: previewInput.destinationUrl, linkLabel: previewInput.linkLabel, filenames }),
    retry: false,
    staleTime: 30_000,
  })
  // Buffer capability decides whether scheduling can work; saving a local record never depends on it.
  // The indicator reflects the selected account only: one org can hold several
  // One publisher can hold several accounts; a channel may be bound on one but not another.
  const publisherUnknown = accounts.isError || Boolean(accounts.data?.error)
  const connected = new Set<string>(selectedAccount?.platforms || [])
  const channelState = accounts.isPending || publisherUnknown ? 'unknown' : connected.has(platform) ? 'connected' : 'missing'
  const label = linkLabel.trim() || 'ops audit'
  async function submit(event: FormEvent<HTMLFormElement>) {
    event.preventDefault(); setError('')
    if (noPublisher) { setError('Configure a publisher in Settings before saving content.'); return }
    if (!assets.length) { setError('Select at least one media file.'); return }
    if (postType === 'video' && assets.length !== 1) { setError('Video posts require exactly one MP4 file.'); return }
    setPending(true)
    try {
      const result = await createManualPost(credentials, { platform, postType, destinationUrl, linkLabel, assets, publisher, bufferAccount: effectiveAccount })
      if (!result.ok || result.post.workflow_status !== 'ready') throw new Error('The backend did not confirm a ready manual post.')
      await created(); close()
    } catch (reason) { setError(reason instanceof Error ? reason.message : 'Manual post could not be saved.') }
    finally { setPending(false) }
  }
  return <div className="modal-backdrop" role="presentation"><div className="modal" role="dialog" aria-modal="true" aria-label="New manual post"><button className="modal-close icon-button" onClick={close} aria-label="Close new manual post">×</button><h2>New manual post</h2><p>Save media and the backend-generated caption. Nothing is published here; Buffer scheduling is a separate, founder-authorized step.</p><form onSubmit={submit}>
    <label>Publisher<select aria-label="Publisher" value={publisher} onChange={event => { setPublisher(event.target.value); setBufferAccount('') }}>{publisherChoices.length ? publisherChoices.map(item => <option key={item.name} value={item.name}>{item.label}</option>) : <option value="">No publisher configured</option>}</select></label>
    <p className="field-note">{noPublisher ? 'Configure the signed webhook in Settings before saving content.' : session ? 'Your organization publishes through its own signed webhook.' : 'Buffer is the default scheduler. A configured webhook scheduler appears here as another option.'}</p>
    <label>Platform<select value={platform} onChange={event => setPlatform(event.target.value as typeof platform)}>{platforms.map(value => <option key={value} value={value}>{value === 'x' ? 'X' : value === 'linkedin' ? 'LinkedIn' : value.charAt(0).toUpperCase() + value.slice(1)}</option>)}</select></label>
    <p className="field-note">{channelState === 'unknown' ? 'Publisher channel status is unavailable. You can save this post; scheduling may need a connection first.' : channelState === 'connected' ? `A ${publisherInfo?.label || publisher} channel is connected for this platform on ${effectiveAccount}.` : `No ${publisherInfo?.label || publisher} channel is connected for ${platform === 'instagram' ? 'Instagram' : platform === 'x' ? 'X' : 'LinkedIn'} on ${effectiveAccount}. You can save now and connect before scheduling.`}</p>
    <label>Publisher account<select aria-label="Publisher account" value={effectiveAccount} onChange={event => setBufferAccount(event.target.value)}>{availableAccounts.length ? availableAccounts.map(item => <option key={item.name} value={item.name}>{item.label}</option>) : <option value="default">default</option>}</select></label>
    <p className="field-note">One publisher can hold several accounts. The channel check above and the later scheduling step both use this account.</p>
    <label>Format<select value={postType} onChange={event => { setPostType(event.target.value as typeof postType); setAssets([]) }}><option value="carousel">Carousel · PNG</option><option value="video">Video · MP4</option></select></label>
    <p className="field-note">{postType === 'video' ? 'Exactly one MP4. Its file name seeds the caption.' : 'PNG images only, one or more. File names seed the caption.'}</p>
    <label>Media<input type="file" accept={postType === 'video' ? '.mp4,video/mp4' : '.png,image/png'} multiple={postType === 'carousel'} onChange={event => setAssets(Array.from(event.target.files || []))} required /></label>
    <label>Destination URL<input type="url" value={destinationUrl} onChange={event => setDestinationUrl(event.target.value)} placeholder={preview.data?.default_destination_url || 'https://your-site.example/form'} /></label>
    <p className="field-note">Leave blank to use {preview.data?.default_destination_url || 'your hosted form'}. UTM and post tracking parameters are appended to the saved link.</p>
    <label>CTA label<input value={linkLabel} onChange={event => setLinkLabel(event.target.value)} maxLength={80} placeholder="ops audit" /></label>
    <p className="field-note">{platform === 'instagram' ? `Rendered as "Link in bio · ${label}". Instagram captions cannot carry a clickable link.` : platform === 'x' ? `Rendered as "Get the ${label}: <tracked link>".` : 'Links stay in the post text — LinkedIn makes them clickable.'}</p>
    <section className="detail-card" aria-live="polite">
      <h3>Caption preview</h3>
      {preview.isPending ? <p className="operational-note">Building caption…</p> : preview.isError ? <p className="form-error" role="alert">Preview unavailable: {preview.error.message}. Saving still works; the backend builds the caption on save.</p> : preview.data && <>
        <p className="workflow-message">{preview.data.caption}</p>
        <dl className="company-fields"><div><dt>Title</dt><dd>{preview.data.title}</dd></div><div><dt>Tracked link</dt><dd><code className="tracked-link">{preview.data.tracked_url}</code></dd></div></dl>
        <p className="operational-note">Sample link: post and campaign ids are assigned when you save. Captions are drafted from file names, not media contents.</p>
      </>}
    </section>
    {error && <p className="form-error" role="alert">{error}</p>}<div className="modal-actions"><button type="button" className="button secondary" onClick={close}>Cancel</button><button className="button primary" disabled={pending || noPublisher}>Save manual post</button></div>
  </form></div></div>
}

export function ContentPage() {
  const credentials = useCredentials()
  const queryClient = useQueryClient()
  const [params, setParams] = useSearchParams()
  const [creatingPost, setCreatingPost] = useState(false)
  const [notice, setNotice] = useState('')
  const q = params.get('q') || ''
  const stage = params.get('stage') || ''
  const selected = params.get('item')
  const page = Math.max(1, Number(params.get('page')) || 1)
  const query = useQuery({ queryKey: ['content'], queryFn: () => contentView(credentials) })
  const data = query.data
  const filtered = useMemo(() => (data?.items || []).filter(item => (!stage || item.stage === stage) && (!q || `${item.title} ${item.caption || ''} ${item.org_name || ''}`.toLowerCase().includes(q.toLowerCase()))), [data, stage, q])
  const items = filtered.slice((page - 1) * 10, page * 10)
  const pages = Math.max(1, Math.ceil(filtered.length / 10))
  const chosen = data?.items.find(item => `${item.kind}:${item.id}` === selected)
  function update(changes: Record<string, string | null>) { const next = new URLSearchParams(params); for (const [key, value] of Object.entries(changes)) { if (value) next.set(key, value); else next.delete(key) } setParams(next) }
  const columns = [
    column.display({ id: 'title', header: 'Content', cell: info => <strong>{info.row.original.title}</strong> }),
    column.display({ id: 'kind', header: 'Type', cell: info => info.row.original.kind.replaceAll('_', ' ') }),
    column.display({ id: 'publisher', header: 'Publisher', cell: info => info.row.original.publisher || 'buffer' }),
    column.display({ id: 'format', header: 'Format', cell: info => info.row.original.format }),
    column.display({ id: 'org', header: 'Organization', cell: info => info.row.original.org_name || 'Not recorded' }),
    column.display({ id: 'stage', header: 'Stage', cell: info => <StatusText value={info.row.original.stage} known={postStages} tone={info.row.original.stage === 'failed' ? 'red' : info.row.original.stage === 'scheduled' ? 'green' : 'blue'} /> }),
    column.display({ id: 'assets', header: 'Assets', cell: info => info.row.original.asset_count }),
    column.display({ id: 'updated', header: 'Updated', cell: info => <ShortDate value={info.row.original.updated_at} /> }),
    column.display({ id: 'action', header: 'Action', cell: info => <button className="row-action" onClick={event => { event.stopPropagation(); update({ item: info.row.original.id }) }}>View content</button> }),
  ]
  return <AppShell active="Content" query={q} onQueryChange={value => update({ q: value, page: '1', item: null })}><div className="page-layout"><main className="page-main"><div className="page-content">
    <div className="page-heading"><div><h1>Content</h1><p>Review saved manual posts. Scheduling and publication are separate states.</p></div><div className="heading-actions"><button className="button primary" onClick={() => setCreatingPost(true)}><Plus size={16} />New manual post</button></div></div>
    <WorkflowMetrics items={[{ label: 'Manual posts loaded', value: data?.manual_posts_loaded, icon: <FileImage /> }, { label: 'Draft-stage loaded', value: data?.items.filter(item => item.stage === 'buffer_draft').length, icon: <Video /> }, { label: 'Scheduled loaded', value: data?.items.filter(item => item.stage === 'scheduled').length, icon: <Send /> }]} />
    {notice && <div className="company-page-notice" role="status">{notice}<button onClick={() => setNotice('')} aria-label="Dismiss message">×</button></div>}
    {data?.manual_posts_truncated && <div className="operational-footnote">This view contains the latest {data.manual_posts_loaded} manual posts. Filters and counts apply to loaded records.</div>}
    <div className="table-toolbar"><div className="view-tabs"><button className="active">Manual posts</button></div><label className="sort-control">Stage <select aria-label="Filter content stage" value={stage} onChange={event => update({ stage: event.target.value, page: '1', item: null })}><option value="">All stages</option>{[...new Set(data?.items.map(item => item.stage) || [])].map(value => <option value={value} key={value}>{value.replaceAll('_', ' ')}</option>)}</select></label></div>
    {query.isError && data && <div className="operational-error" role="alert">Refresh failed: {query.error.message} <button onClick={() => query.refetch()}>Retry</button></div>}
    <div className="table-panel">{query.isPending ? <LoadingRows label="Loading content" /> : query.isError && !data ? <DataState title="Content could not be loaded" detail={query.error.message} retry={() => query.refetch()} /> : items.length ? <WorkflowTable items={items.map(item => ({ ...item, id: `${item.kind}:${item.id}` }))} columns={columns} selected={selected} onSelect={id => update({ item: id })} /> : <DataState title="No content found" detail={q || stage ? 'Try another filter.' : 'Create a manual post.'} />}</div>
    <div className="table-footer"><span>{data ? `Showing ${filtered.length ? (page - 1) * 10 + 1 : 0}–${Math.min(page * 10, filtered.length)} of ${filtered.length} loaded records` : 'Loading content…'}</span><div className="pagination"><button aria-label="Previous page" disabled={page <= 1} onClick={() => update({ page: String(page - 1), item: null })}><ChevronLeft size={17} /></button><span>{page} of {pages}</span><button aria-label="Next page" disabled={page >= pages} onClick={() => update({ page: String(page + 1), item: null })}><ChevronRight size={17} /></button></div></div>
  </div></main>{chosen && <ContentDrawer key={selected} item={chosen} close={() => update({ item: null })} />}{creatingPost && <ManualPostCreate close={() => setCreatingPost(false)} created={async () => { await queryClient.invalidateQueries({ queryKey: ['content'] }); update({ q: null, kind: null, stage: null, page: '1', item: null }); setNotice('Manual post saved and ready. It has not been scheduled or published.') }} />}</div></AppShell>
}
