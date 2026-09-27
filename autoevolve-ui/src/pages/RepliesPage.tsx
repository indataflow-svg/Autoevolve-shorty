import { useState } from 'react'
import { keepPreviousData, useQuery, useQueryClient } from '@tanstack/react-query'
import { createColumnHelper } from '@tanstack/react-table'
import { ArrowRight, ChevronLeft, ChevronRight, Inbox, Mail, MessageCircle, ShieldAlert } from 'lucide-react'
import { Link, useSearchParams } from 'react-router-dom'
import { createReplyDraft, repliesPage, replyDetail, type ReplyItem } from '../api/workflows'
import { useCredentials } from '../app/Auth'
import { AppShell } from '../components/Shell'
import { DataState, LoadingRows, RightDrawer, StateBadge } from '../components/Primitives'
import { ShortDate, WorkflowMetrics, WorkflowTable } from '../components/WorkflowTable'

type ReplyRow = Omit<ReplyItem, 'id'> & { id: string }
const column = createColumnHelper<ReplyRow>()
const views = [
  { label: 'All replies', value: 'all', count: 'total' },
  { label: 'Latest inbound', value: 'latest', count: 'latest' },
  { label: 'Suppressed contacts', value: 'suppressed', count: 'suppressed' },
] as const

function ReplyDrawer({ id, close }: { id: number; close: () => void }) {
  const credentials = useCredentials()
  const queryClient = useQueryClient()
  const detail = useQuery({ queryKey: ['reply', id], queryFn: () => replyDetail(credentials, id) })
  const reply = detail.data
  const [token, setToken] = useState('')
  const [pending, setPending] = useState(false)
  const [error, setError] = useState('')
  const [draftId, setDraftId] = useState('')

  async function draft() {
    if (!reply || !token.trim()) { setError('Enter the founder action token.'); return }
    setError(''); setPending(true)
    try {
      const current = await replyDetail(credentials, id)
      if (!current.can_draft_reply) throw new Error('This reply is no longer the latest eligible interaction. Refresh before drafting.')
      const saved = await createReplyDraft(credentials, current.lead_id, token)
      if (saved.kind !== 'reply' || !saved.id || (current.provider_message_id && saved.in_reply_to !== current.provider_message_id)) throw new Error('The backend did not confirm a draft for this reply. Inspect the contact before taking another action.')
      setDraftId(saved.id)
      setToken('')
      await Promise.all([
        queryClient.invalidateQueries({ queryKey: ['replies'] }),
        queryClient.invalidateQueries({ queryKey: ['reply', id] }),
        queryClient.invalidateQueries({ queryKey: ['outreach'] }),
        queryClient.invalidateQueries({ queryKey: ['home'] }),
      ])
    } catch (reason) { setError(reason instanceof Error ? reason.message : 'Reply draft failed.') }
    finally { setPending(false) }
  }

  return <RightDrawer title="Reply details" onClose={close} className="workflow-drawer">
    {detail.isPending ? <LoadingRows label="Loading reply" /> : detail.isError && !reply ? <DataState title="Reply unavailable" detail={detail.error.message} retry={() => detail.refetch()} /> : reply ? <>
      <div className="drawer-identity"><span className="provider-icon"><MessageCircle size={24} /></span><div className="drawer-name"><h2>{reply.company || 'Company not recorded'}</h2><p>{reply.contact_name || reply.email || 'Contact not recorded'}</p></div></div>
      <div className="drawer-status"><StateBadge tone={reply.lead_stage === 'suppressed' ? 'red' : reply.is_latest_interaction ? 'blue' : 'neutral'}>{reply.lead_stage === 'suppressed' ? 'Contact suppressed' : reply.is_latest_interaction ? 'Latest interaction: inbound' : 'Earlier inbound reply'}</StateBadge></div>
      <div className="drawer-tabs"><button aria-selected="true">Message</button></div>
      <div className="drawer-body">
        {detail.isError && <p className="operational-error" role="alert">Refresh failed: {detail.error.message}</p>}
        <section className="detail-card"><h3>Original inbound message</h3><p className="operational-note">From {reply.contact_name || reply.email || 'Contact not recorded'} · <ShortDate value={reply.received_at} /></p><strong className="message-subject">{reply.subject || 'No subject'}</strong><p className="workflow-message">{reply.body || 'Message body was not recorded.'}</p></section>
        <section className="detail-card"><h3>Saved facts</h3><dl className="company-fields"><div><dt>Contact</dt><dd>{reply.contact_name || 'Not recorded'}</dd></div><div><dt>Role</dt><dd>{reply.contact_role || 'Not recorded'}</dd></div><div><dt>Company</dt><dd>{reply.company || 'Not recorded'}</dd></div><div><dt>Email</dt><dd>{reply.email || 'Not recorded'}</dd></div><div><dt>Thread ID</dt><dd className="break-value">{reply.provider_message_id || 'Not recorded'}</dd></div></dl></section>
        <p className="operational-note">Intent and confidence are not classified by the current backend. The message above is the original saved inbound text.</p>
      </div>
      <div className="drawer-footer">
        {draftId && <p className="success-message" role="status">Reply draft saved by the backend. <Link to={`/outreach?draft=${encodeURIComponent(draftId)}`}>Review it in Outreach <ArrowRight size={13} /></Link></p>}
        {error && <p className="form-error" role="alert">{error}</p>}
        {reply.can_draft_reply ? <><label className="operational-label">Founder action token<input type="password" aria-label="Founder action token" autoComplete="off" value={token} onChange={event => setToken(event.target.value)} /></label><button className="button primary" onClick={draft} disabled={pending || !!draftId}>{pending ? 'Creating draft…' : 'Draft reply'}</button></> : <p className="operational-note">A reply draft is available only while this remains the contact’s latest inbound interaction and the contact is eligible.</p>}
        <Link className="button secondary" to={`/contacts?contact=${encodeURIComponent(reply.lead_id)}`}>Open contact</Link>
      </div>
    </> : null}
  </RightDrawer>
}

export function RepliesPage() {
  const credentials = useCredentials()
  const [params, setParams] = useSearchParams()
  const page = Math.max(1, Number(params.get('page')) || 1)
  const q = params.get('q') || ''
  const view = views.some(item => item.value === params.get('view')) ? params.get('view')! : 'all'
  const sort = ['recent', 'oldest', 'company'].includes(params.get('sort') || '') ? params.get('sort')! : 'recent'
  const selected = params.get('reply')
  const query = useQuery({ queryKey: ['replies', page, q, view, sort], queryFn: () => repliesPage(credentials, { page, q, view, sort }), placeholderData: keepPreviousData })
  const result = query.data
  const pages = Math.max(1, Math.ceil((result?.total || 0) / 10))
  function update(changes: Record<string, string | null>) { const next = new URLSearchParams(params); for (const [key, value] of Object.entries(changes)) { if (value) next.set(key, value); else next.delete(key) } setParams(next) }
  const columns = [
    column.display({ id: 'company', header: 'Company', cell: info => <strong>{info.row.original.company || 'Not recorded'}</strong> }),
    column.display({ id: 'contact', header: 'Contact', cell: info => <span>{info.row.original.contact_name || info.row.original.email || 'Not recorded'}</span> }),
    column.display({ id: 'message', header: 'Message', cell: info => <span className="cell-truncate">{info.row.original.body || info.row.original.subject || 'Body not recorded'}</span> }),
    column.display({ id: 'thread', header: 'Thread state', cell: info => <StateBadge tone={info.row.original.lead_stage === 'suppressed' ? 'red' : info.row.original.is_latest_interaction ? 'blue' : 'neutral'}>{info.row.original.lead_stage === 'suppressed' ? 'suppressed' : info.row.original.is_latest_interaction ? 'latest inbound' : 'earlier reply'}</StateBadge> }),
    column.display({ id: 'received', header: 'Received', cell: info => <ShortDate value={info.row.original.received_at} /> }),
    column.display({ id: 'action', header: 'Action', cell: info => <button className="row-action" onClick={event => { event.stopPropagation(); update({ reply: String(info.row.original.id) }) }}>{info.row.original.can_draft_reply ? 'Draft reply' : 'View message'}</button> }),
  ]
  return <AppShell active="Replies" query={q} onQueryChange={value => update({ q: value, page: '1', reply: null })}><div className="page-layout"><main className="page-main"><div className="page-content">
    <div className="page-heading"><div><h1>Replies</h1><p>Review original inbound email and create gated reply drafts.</p></div><div className="heading-actions"><Link to="/outreach" className="button secondary">Open Outreach <ArrowRight size={16} /></Link></div></div>
    <WorkflowMetrics items={[{ label: 'Inbound replies', value: result?.counts.total, icon: <Inbox /> }, { label: 'Latest inbound', value: result?.counts.latest, icon: <MessageCircle /> }, { label: 'With thread ID', value: result?.counts.threaded, icon: <Mail /> }, { label: 'Suppressed contacts', value: result?.counts.suppressed, icon: <ShieldAlert /> }]} />
    <div className="reply-summary"><button onClick={() => update({ view: 'latest', page: '1', reply: null })}><MessageCircle size={22} /><span><strong>Latest inbound on a contact</strong><small>{result?.counts.latest ?? '—'} saved replies are the most recent interaction on their contact.</small></span><ChevronRight size={17} /></button><Link to="/outreach"><Mail size={22} /><span><strong>Reply drafts live in Outreach</strong><small>Draft, approval, and send remain separate backend stages.</small></span><ArrowRight size={17} /></Link></div>
    <div className="table-toolbar"><div className="view-tabs">{views.map(item => <button key={item.value} className={view === item.value ? 'active' : ''} onClick={() => update({ view: item.value, page: '1', reply: null })}>{item.label} ({result?.counts[item.count] ?? 0})</button>)}</div><label className="sort-control">Sort <select aria-label="Sort replies" value={sort} onChange={event => update({ sort: event.target.value, page: '1' })}><option value="recent">Last received</option><option value="oldest">Oldest received</option><option value="company">Company A–Z</option></select></label></div>
    {query.isError && result && <div className="operational-error" role="alert">Refresh failed: {query.error.message} <button onClick={() => query.refetch()}>Retry</button></div>}
    <div className="table-panel">{query.isPending ? <LoadingRows label="Loading replies" /> : query.isError && !result ? <DataState title="Replies could not be loaded" detail={query.error.message} retry={() => query.refetch()} /> : result?.items.length ? <WorkflowTable items={result.items.map(item => ({ ...item, id: String(item.id) }))} columns={columns} selected={selected} onSelect={id => update({ reply: id })} /> : <DataState title="No replies found" detail={q || view !== 'all' ? 'Try another search or view.' : 'Inbound email replies will appear here after the backend records them.'} />}</div>
    <div className="table-footer"><span>{result ? `Showing ${result.total ? (page - 1) * 10 + 1 : 0}–${Math.min(page * 10, result.total)} of ${result.total} replies` : 'Loading replies…'}{query.isFetching && !query.isPending && ' · Refreshing…'}</span><div className="pagination"><button aria-label="Previous page" disabled={page <= 1} onClick={() => update({ page: String(page - 1), reply: null })}><ChevronLeft size={17} /></button><span>{page} of {pages}</span><button aria-label="Next page" disabled={page >= pages} onClick={() => update({ page: String(page + 1), reply: null })}><ChevronRight size={17} /></button></div></div>
  </div></main>{selected && /^\d+$/.test(selected) && <ReplyDrawer key={selected} id={Number(selected)} close={() => update({ reply: null })} />}</div></AppShell>
}
