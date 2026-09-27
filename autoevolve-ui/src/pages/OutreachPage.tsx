import { useState, type FormEvent } from 'react'
import { keepPreviousData, useQuery, useQueryClient } from '@tanstack/react-query'
import { createColumnHelper } from '@tanstack/react-table'
import { Link, useSearchParams } from 'react-router-dom'
import { ArrowRight, ChevronLeft, ChevronRight, Clock3, FileText, Mail, Send, ShieldAlert } from 'lucide-react'
import { approveOutreach, DRAFT_STATUS, outreachDetail, outreachPage, sendOutreach, updateOutreach, type OutreachItem } from '../api/workflows'
import { useCredentials } from '../app/Auth'
import { AppShell } from '../components/Shell'
import { DataState, LoadingRows, RightDrawer } from '../components/Primitives'
import { ShortDate, StatusText, WorkflowMetrics, WorkflowTable } from '../components/WorkflowTable'

const draftStatuses = Object.values(DRAFT_STATUS)
const tabs = [{ label: 'All', value: '' }, { label: 'Drafts', value: 'draft' }, { label: 'Approved', value: 'approved' }, { label: 'Sending', value: 'sending' }, { label: 'Sent', value: 'sent' }, { label: 'Unknown', value: 'send_unknown' }]
const column = createColumnHelper<OutreachItem>()

function OutreachDrawer({ id, close }: { id: string; close: () => void }) {
  const credentials = useCredentials()
  const queryClient = useQueryClient()
  const detail = useQuery({ queryKey: ['outreach-detail', id], queryFn: () => outreachDetail(credentials, id) })
  const [token, setToken] = useState('')
  const [editing, setEditing] = useState(false)
  const [subject, setSubject] = useState('')
  const [body, setBody] = useState('')
  const [error, setError] = useState('')
  const [notice, setNotice] = useState('')
  const [pending, setPending] = useState(false)
  const draft = detail.data
  async function refresh() {
    await Promise.all([queryClient.invalidateQueries({ queryKey: ['outreach'] }), queryClient.invalidateQueries({ queryKey: ['outreach-detail', id] }), queryClient.invalidateQueries({ queryKey: ['contacts'] }), queryClient.invalidateQueries({ queryKey: ['home'] })])
  }
  async function act(kind: 'edit' | 'approve' | 'send', event?: FormEvent) {
    event?.preventDefault()
    setError(''); setNotice('')
    if (!draft || !token.trim()) { setError('Enter the founder action token.'); return }
    if (kind === 'edit' && !['draft', 'approved'].includes(draft.status)) { setError('This draft can no longer be edited.'); return }
    if (kind === 'approve' && draft.status !== DRAFT_STATUS.draft) { setError('Only draft messages can be approved.'); return }
    if (kind === 'send' && (draft.status !== DRAFT_STATUS.approved || draft.channel !== 'email' || !draft.email)) { setError('Only an approved email with a recipient can be sent.'); return }
    setPending(true)
    try {
      if (kind === 'edit') await updateOutreach(credentials, id, { subject, body }, token)
      else if (kind === 'approve') await approveOutreach(credentials, id, token)
      else { const response = await sendOutreach(credentials, id, token); if (!response.ok || !response.sent) throw new Error('Backend did not confirm the send. Refresh and check its status before trying again.') }
      await refresh()
      setNotice(kind === 'edit' ? 'Draft saved and refreshed.' : kind === 'approve' ? 'Draft approved and refreshed.' : 'Backend confirmed the send. Refreshed from the draft record.')
      setEditing(false); setToken('')
    } catch (reason) { setError(reason instanceof Error ? reason.message : 'Action failed.') }
    finally { setPending(false) }
  }
  return <RightDrawer title="Outreach details" onClose={close} className="workflow-drawer">
    {detail.isPending ? <LoadingRows label="Loading draft" /> : detail.isError && !draft ? <DataState title="Draft unavailable" detail={detail.error.message} retry={() => detail.refetch()} /> : draft ? <>
      <div className="drawer-identity"><span className="provider-icon"><Mail size={24} /></span><div className="drawer-name"><h2>{draft.company || 'Company not recorded'}</h2><p>{draft.contact_name || draft.email || 'Contact not recorded'}</p></div></div>
      <div className="drawer-status"><StatusText value={draft.status} known={draftStatuses} tone={draft.status === 'sent' ? 'green' : draft.status === 'send_unknown' ? 'red' : draft.status === 'approved' ? 'blue' : 'yellow'} /></div>
      <div className="drawer-tabs"><button aria-selected="true">Message</button></div>
      <div className="drawer-body"><section className="detail-card"><h3>Recipient</h3><p>{draft.contact_name || 'Name not recorded'} {draft.email ? `<${draft.email}>` : '· Email not recorded'}</p><p className="operational-note">{draft.contact_role || 'Role not recorded'} · {draft.channel}</p></section>
        <section className="detail-card"><h3>{draft.subject}</h3><p className="workflow-message">{draft.body}</p></section>
        <section className="detail-card"><h3>Workflow facts</h3><dl className="company-fields"><div><dt>Kind</dt><dd>{draft.kind}</dd></div><div><dt>Created</dt><dd><ShortDate value={draft.created_at} /></dd></div><div><dt>Approved</dt><dd><ShortDate value={draft.approved_at} /></dd></div><div><dt>Sent</dt><dd><ShortDate value={draft.sent_at} /></dd></div></dl></section>
        {draft.status === 'send_unknown' && <div className="operational-error">Send status unknown — reconciliation required. Duplicate sends are blocked.</div>}
      </div>
      <div className="drawer-footer"><label className="operational-label">Founder action token<input type="password" aria-label="Founder action token" autoComplete="off" value={token} onChange={event => setToken(event.target.value)} /></label>
        {editing && <form className="workflow-form" onSubmit={event => act('edit', event)}><label>Subject<input value={subject} onChange={event => setSubject(event.target.value)} minLength={3} maxLength={200} required /></label><label>Message<textarea value={body} onChange={event => setBody(event.target.value)} minLength={20} maxLength={6000} required /></label><button className="button primary" disabled={pending}>Save draft</button></form>}
        {error && <p className="form-error" role="alert">{error}</p>}{notice && <p className="success-message" role="status">{notice}</p>}
        <div className="workflow-actions">{['draft', 'approved'].includes(draft.status) && <button className="button secondary" onClick={() => { setEditing(!editing); setSubject(draft.subject); setBody(draft.body) }}>{editing ? 'Cancel edit' : 'Edit draft'}</button>}{draft.status === DRAFT_STATUS.draft && <button className="button primary" disabled={pending} onClick={() => act('approve')}>Approve draft</button>}{draft.status === DRAFT_STATUS.approved && draft.channel === 'email' && draft.email && <button className="button primary" disabled={pending} onClick={() => act('send')}>Send approved email</button>}</div>
      </div>
    </> : null}
  </RightDrawer>
}

export function OutreachPage() {
  const credentials = useCredentials()
  const [params, setParams] = useSearchParams()
  const page = Math.max(1, Number(params.get('page')) || 1)
  const q = params.get('q') || ''
  const status = params.get('status') || ''
  const sort = ['recent', 'oldest', 'company'].includes(params.get('sort') || '') ? params.get('sort')! : 'recent'
  const selected = params.get('draft')
  const query = useQuery({ queryKey: ['outreach', page, q, status, sort], queryFn: () => outreachPage(credentials, { page, q, status, sort }), placeholderData: keepPreviousData })
  const result = query.data
  const pages = Math.max(1, Math.ceil((result?.total || 0) / 10))
  function update(changes: Record<string, string | null>) { const next = new URLSearchParams(params); for (const [key, value] of Object.entries(changes)) { if (value) next.set(key, value); else next.delete(key) } setParams(next) }
  const columns = [
    column.display({ id: 'company', header: 'Company', cell: info => <strong>{info.row.original.company || 'Not recorded'}</strong> }),
    column.display({ id: 'contact', header: 'Contact', cell: info => <span>{info.row.original.contact_name || info.row.original.email || 'Not recorded'}</span> }),
    column.display({ id: 'channel', header: 'Channel', cell: info => <span>{info.row.original.channel}</span> }),
    column.display({ id: 'subject', header: 'Subject', cell: info => <span className="cell-truncate">{info.row.original.subject}</span> }),
    column.display({ id: 'status', header: 'Stage', cell: info => <StatusText value={info.row.original.status} known={draftStatuses} tone={info.row.original.status === 'sent' ? 'green' : info.row.original.status === 'send_unknown' ? 'red' : 'blue'} /> }),
    column.display({ id: 'updated', header: 'Updated', cell: info => <ShortDate value={info.row.original.updated_at} /> }),
    column.display({ id: 'action', header: 'Action', cell: info => <button className="row-action" onClick={event => { event.stopPropagation(); update({ draft: info.row.original.id }) }}>{info.row.original.status === 'draft' ? 'Review' : info.row.original.status === 'approved' ? 'Send' : 'View'}</button> }),
  ]
  return <AppShell active="Outreach" query={q} onQueryChange={value => update({ q: value, page: '1', draft: null })}><div className="page-layout"><main className="page-main"><div className="page-content">
    <div className="page-heading"><div><h1>Outreach</h1><p>Review drafts, approve messages, and send through the existing workflow.</p></div><div className="heading-actions"><Link to="/contacts" className="button primary">New outreach <ArrowRight size={16} /></Link></div></div>
    <WorkflowMetrics items={[{ label: 'Drafts', value: result ? result.by_status.draft || 0 : undefined, icon: <FileText /> }, { label: 'Approved', value: result ? result.by_status.approved || 0 : undefined, icon: <Clock3 /> }, { label: 'Sent', value: result ? result.by_status.sent || 0 : undefined, icon: <Send /> }, { label: 'Send unknown', value: result ? result.by_status.send_unknown || 0 : undefined, icon: <ShieldAlert /> }]} />
    <div className="table-toolbar"><div className="view-tabs">{tabs.map(tab => <button key={tab.label} className={status === tab.value ? 'active' : ''} onClick={() => update({ status: tab.value, page: '1', draft: null })}>{tab.label} ({tab.value ? result?.by_status[tab.value] || 0 : Object.values(result?.by_status || {}).reduce((a, b) => a + b, 0)})</button>)}</div><label className="sort-control">Sort <select aria-label="Sort outreach" value={sort} onChange={event => update({ sort: event.target.value, page: '1' })}><option value="recent">Recently updated</option><option value="oldest">Oldest updated</option><option value="company">Company A–Z</option></select></label></div>
    {query.isError && result && <div className="operational-error" role="alert">Refresh failed: {query.error.message} <button onClick={() => query.refetch()}>Retry</button></div>}
    <div className="table-panel">{query.isPending ? <LoadingRows label="Loading outreach" /> : query.isError && !result ? <DataState title="Outreach could not be loaded" detail={query.error.message} retry={() => query.refetch()} /> : result?.items.length ? <WorkflowTable items={result.items} columns={columns} selected={selected} onSelect={id => update({ draft: id })} /> : <DataState title="No outreach found" detail={q || status ? 'Try another search or stage.' : 'Create a draft from a contact to start outreach.'} />}</div>
    <div className="table-footer"><span>{result ? `Showing ${result.total ? (page - 1) * 10 + 1 : 0}–${Math.min(page * 10, result.total)} of ${result.total} drafts` : 'Loading outreach…'}{query.isFetching && !query.isPending && ' · Refreshing…'}</span><div className="pagination"><button aria-label="Previous page" disabled={page <= 1} onClick={() => update({ page: String(page - 1), draft: null })}><ChevronLeft size={17} /></button><span>{page} of {pages}</span><button aria-label="Next page" disabled={page >= pages} onClick={() => update({ page: String(page + 1), draft: null })}><ChevronRight size={17} /></button></div></div>
  </div></main>{selected && <OutreachDrawer key={selected} id={selected} close={() => update({ draft: null })} />}</div></AppShell>
}
