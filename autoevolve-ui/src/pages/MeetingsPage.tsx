import { useState, type FormEvent } from 'react'
import { keepPreviousData, useQuery, useQueryClient } from '@tanstack/react-query'
import { createColumnHelper } from '@tanstack/react-table'
import { ArrowRight, CalendarDays, ChevronLeft, ChevronRight, ClipboardList, Clock3, FileText, Plus, X } from 'lucide-react'
import { Link, useSearchParams } from 'react-router-dom'
import { contactsPage } from '../api/contacts'
import { meetingDetail, meetingsPage, recordMeetingMarker, type MeetingMarker } from '../api/workflows'
import { useCredentials } from '../app/Auth'
import { AppShell } from '../components/Shell'
import { DataState, LoadingRows, RightDrawer, StateBadge } from '../components/Primitives'
import { ShortDate, WorkflowMetrics, WorkflowTable } from '../components/WorkflowTable'

const column = createColumnHelper<MeetingMarker>()
const views = [
  { label: 'All records', value: 'all', count: 'total' },
  { label: 'With date', value: 'dated', count: 'dated' },
  { label: 'No date', value: 'undated', count: 'undated' },
] as const

function RecordedWhen({ value }: { value: string | null }) {
  if (!value) return <span className="muted-copy">Not recorded</span>
  const date = new Date(value)
  if (Number.isNaN(date.getTime())) return <span>{value}</span>
  return <time dateTime={value}>{new Intl.DateTimeFormat(undefined, { dateStyle: 'medium', timeStyle: 'short' }).format(date)}</time>
}

function MeetingDrawer({ id, close }: { id: string; close: () => void }) {
  const credentials = useCredentials()
  const detail = useQuery({ queryKey: ['meeting', id], queryFn: () => meetingDetail(credentials, id) })
  const meeting = detail.data
  return <RightDrawer title="Meeting details" onClose={close} className="workflow-drawer">
    {detail.isPending ? <LoadingRows label="Loading meeting record" /> : detail.isError && !meeting ? <DataState title="Meeting record unavailable" detail={detail.error.message} retry={() => detail.refetch()} /> : meeting ? <>
      <div className="drawer-identity"><span className="provider-icon"><CalendarDays size={24} /></span><div className="drawer-name"><h2>{meeting.company || 'Company not recorded'}</h2><p>{meeting.contact_name || meeting.email || 'Contact not recorded'}</p></div></div>
      <div className="drawer-status"><StateBadge tone="blue">Manual meeting marker · {meeting.status}</StateBadge></div>
      <div className="drawer-tabs"><button aria-selected="true">Record</button></div>
      <div className="drawer-body">
        {detail.isError && <p className="operational-error" role="alert">Refresh failed: {detail.error.message}</p>}
        <section className="detail-card"><h3>Recorded meeting details</h3><dl className="company-fields"><div><dt>Scheduled for</dt><dd><RecordedWhen value={meeting.scheduled_for} /></dd></div><div><dt>Recorded at</dt><dd><ShortDate value={meeting.recorded_at} /></dd></div><div><dt>Source</dt><dd>{meeting.source || 'Not recorded'}</dd></div><div><dt>Contact</dt><dd>{meeting.contact_name || 'Not recorded'}</dd></div><div><dt>Role</dt><dd>{meeting.contact_role || 'Not recorded'}</dd></div><div><dt>Email</dt><dd>{meeting.email || 'Not recorded'}</dd></div></dl></section>
        <section className="detail-card"><h3>Saved note</h3><p className="workflow-message">{meeting.note || 'No note was recorded.'}</p></section>
        <p className="operational-note">This marker was saved manually. It does not confirm a calendar booking, attendee invitation, or call link.</p>
      </div>
      <div className="drawer-footer"><div className="workflow-actions"><Link className="button secondary" to={`/contacts?contact=${encodeURIComponent(meeting.lead_id)}`}>Open contact</Link><a className="button secondary" href="/calendar" target="_blank" rel="noreferrer">Open booking page <ArrowRight size={14} /></a></div></div>
    </> : null}
  </RightDrawer>
}

function RecordMeetingDialog({ close, created }: { close: () => void; created: (id: string) => Promise<void> }) {
  const credentials = useCredentials()
  const [q, setQ] = useState('')
  const [leadId, setLeadId] = useState('')
  const [scheduledFor, setScheduledFor] = useState('')
  const [note, setNote] = useState('')
  const [token, setToken] = useState('')
  const [error, setError] = useState('')
  const [pending, setPending] = useState(false)
  const contacts = useQuery({ queryKey: ['meeting-contact-search', q], queryFn: () => contactsPage(credentials, { page: 1, q, stage: '', sort: 'recent' }), enabled: q.trim().length >= 2, retry: false })

  async function submit(event: FormEvent<HTMLFormElement>) {
    event.preventDefault(); setError('')
    if (!leadId || !contacts.data?.items.some(item => item.id === leadId)) { setError('Choose a contact from the current search results.'); return }
    if (!scheduledFor) { setError('Choose the date and time recorded for this meeting.'); return }
    setPending(true)
    try {
      const response = await recordMeetingMarker(credentials, leadId, new Date(scheduledFor).toISOString(), note.trim() || null, token)
      if (!response.ok || response.stage !== 'scheduled' || response.lead.metadata?.meeting?.status !== 'scheduled') throw new Error('The backend did not confirm a meeting marker. Refresh before trying again.')
      await created(leadId)
      close()
    } catch (reason) { setError(reason instanceof Error ? reason.message : 'Meeting marker could not be saved.') }
    finally { setPending(false) }
  }

  return <div className="modal-backdrop" role="presentation"><div className="modal" role="dialog" aria-modal="true" aria-label="Record meeting"><button className="modal-close icon-button" onClick={close} aria-label="Close record meeting"><X size={19} /></button><h2>Record meeting</h2><p>Save a manual meeting marker on an existing contact. This does not book a calendar event.</p><form onSubmit={submit}>
    <label>Find contact<input value={q} onChange={event => { setQ(event.target.value); setLeadId('') }} minLength={2} placeholder="Search name, company, or email" /></label>
    {contacts.isPending && q.trim().length >= 2 && <p className="operational-note">Searching contacts…</p>}
    {contacts.isError && <p className="form-error" role="alert">Contacts could not be loaded: {contacts.error.message}</p>}
    {contacts.data && <label>Contact<select value={leadId} onChange={event => setLeadId(event.target.value)} required><option value="">Select a contact</option>{contacts.data.items.map(item => <option key={item.id} value={item.id}>{item.full_name || item.email || 'Name not recorded'} · {item.company || 'Company not recorded'}</option>)}</select>{contacts.data.total > contacts.data.items.length && <small>Showing the first {contacts.data.items.length} matches. Refine your search to find another contact.</small>}</label>}
    <label>Recorded date and time<input type="datetime-local" value={scheduledFor} onChange={event => setScheduledFor(event.target.value)} required /></label>
    <label>Note (optional)<textarea value={note} onChange={event => setNote(event.target.value)} maxLength={400} /></label>
    <label>Founder action token<input type="password" autoComplete="off" value={token} onChange={event => setToken(event.target.value)} required /></label>
    {error && <p className="form-error" role="alert">{error}</p>}
    <div className="modal-actions"><button type="button" className="button secondary" onClick={close}>Cancel</button><button className="button primary" disabled={pending || !leadId}>{pending ? 'Saving…' : 'Save meeting marker'}</button></div>
  </form></div></div>
}

function RecordedSchedule({ items }: { items: MeetingMarker[] }) {
  const today = new Date()
  today.setHours(0, 0, 0, 0)
  const days = Array.from({ length: 7 }, (_, index) => { const day = new Date(today); day.setDate(today.getDate() + index); return day })
  return <section className="recorded-schedule"><div className="recorded-schedule-heading"><strong>Recorded dates</strong><span>Next seven days · records on this page only</span></div><div className="recorded-schedule-grid">{days.map(day => { const matching = items.filter(item => { if (!item.scheduled_for) return false; const date = new Date(item.scheduled_for); return !Number.isNaN(date.getTime()) && date.toDateString() === day.toDateString() }); return <div key={day.toISOString()}><span>{new Intl.DateTimeFormat(undefined, { weekday: 'short', day: 'numeric' }).format(day)}</span>{matching.length ? matching.map(item => <small key={item.id}>{item.company || item.contact_name || 'Contact not recorded'}</small>) : <small className="muted-copy">—</small>}</div> })}</div></section>
}

export function MeetingsPage() {
  const credentials = useCredentials()
  const queryClient = useQueryClient()
  const [params, setParams] = useSearchParams()
  const [creating, setCreating] = useState(false)
  const [notice, setNotice] = useState('')
  const page = Math.max(1, Number(params.get('page')) || 1)
  const q = params.get('q') || ''
  const view = views.some(item => item.value === params.get('view')) ? params.get('view')! : 'all'
  const sort = ['recent', 'oldest', 'company'].includes(params.get('sort') || '') ? params.get('sort')! : 'recent'
  const selected = params.get('meeting')
  const query = useQuery({ queryKey: ['meetings', page, q, view, sort], queryFn: () => meetingsPage(credentials, { page, q, view, sort }), placeholderData: keepPreviousData })
  const result = query.data
  const pages = Math.max(1, Math.ceil((result?.total || 0) / 10))
  function update(changes: Record<string, string | null>) { const next = new URLSearchParams(params); for (const [key, value] of Object.entries(changes)) { if (value) next.set(key, value); else next.delete(key) } setParams(next) }
  const columns = [
    column.display({ id: 'company', header: 'Company', cell: info => <strong>{info.row.original.company || 'Not recorded'}</strong> }),
    column.display({ id: 'contact', header: 'Contact', cell: info => info.row.original.contact_name || info.row.original.email || 'Not recorded' }),
    column.display({ id: 'when', header: 'Recorded date', cell: info => <RecordedWhen value={info.row.original.scheduled_for} /> }),
    column.display({ id: 'status', header: 'Status', cell: () => <StateBadge tone="blue">manual marker</StateBadge> }),
    column.display({ id: 'note', header: 'Note', cell: info => <span className="cell-truncate">{info.row.original.note || 'Not recorded'}</span> }),
    column.display({ id: 'action', header: 'Action', cell: info => <button className="row-action" onClick={event => { event.stopPropagation(); update({ meeting: info.row.original.id }) }}>View record</button> }),
  ]
  return <AppShell active="Meetings" query={q} onQueryChange={value => update({ q: value, page: '1', meeting: null })}><div className="page-layout"><main className="page-main"><div className="page-content">
    <div className="page-heading"><div><h1>Meetings</h1><p>Review manually recorded meeting markers. Calendar bookings are separate.</p></div><div className="heading-actions"><a className="button secondary" href="/calendar" target="_blank" rel="noreferrer">Open booking page</a><button className="button primary" onClick={() => setCreating(true)}><Plus size={16} />Record meeting</button></div></div>
    <WorkflowMetrics items={[{ label: 'Meeting markers', value: result?.counts.total, icon: <CalendarDays /> }, { label: 'With date', value: result?.counts.dated, icon: <Clock3 /> }, { label: 'No date', value: result?.counts.undated, icon: <ClipboardList /> }, { label: 'With note', value: result?.counts.with_note, icon: <FileText /> }]} />
    {notice && <div className="company-page-notice" role="status">{notice}<button onClick={() => setNotice('')} aria-label="Dismiss message">×</button></div>}
    <div className="table-toolbar"><div className="view-tabs">{views.map(item => <button key={item.value} className={view === item.value ? 'active' : ''} onClick={() => update({ view: item.value, page: '1', meeting: null })}>{item.label} ({result?.counts[item.count] ?? 0})</button>)}</div><label className="sort-control">Sort <select aria-label="Sort meeting records" value={sort} onChange={event => update({ sort: event.target.value, page: '1' })}><option value="recent">Recently recorded</option><option value="oldest">Oldest recorded</option><option value="company">Company A–Z</option></select></label></div>
    {query.isError && result && <div className="operational-error" role="alert">Refresh failed: {query.error.message} <button onClick={() => query.refetch()}>Retry</button></div>}
    <div className="table-panel">{query.isPending ? <LoadingRows label="Loading meeting records" /> : query.isError && !result ? <DataState title="Meeting records could not be loaded" detail={query.error.message} retry={() => query.refetch()} /> : result?.items.length ? <WorkflowTable items={result.items} columns={columns} selected={selected} onSelect={id => update({ meeting: id })} /> : <DataState title="No meeting markers found" detail={q || view !== 'all' ? 'Try another search or view.' : 'Use Record meeting to save a manual marker on a contact.'} />}</div>
    <div className="table-footer"><span>{result ? `Showing ${result.total ? (page - 1) * 10 + 1 : 0}–${Math.min(page * 10, result.total)} of ${result.total} recorded markers` : 'Loading meeting records…'}{query.isFetching && !query.isPending && ' · Refreshing…'}</span><div className="pagination"><button aria-label="Previous page" disabled={page <= 1} onClick={() => update({ page: String(page - 1), meeting: null })}><ChevronLeft size={17} /></button><span>{page} of {pages}</span><button aria-label="Next page" disabled={page >= pages} onClick={() => update({ page: String(page + 1), meeting: null })}><ChevronRight size={17} /></button></div></div>
    <RecordedSchedule items={result?.items || []} />
  </div></main>{selected && <MeetingDrawer key={selected} id={selected} close={() => update({ meeting: null })} />}{creating && <RecordMeetingDialog close={() => setCreating(false)} created={async id => { await Promise.all([queryClient.invalidateQueries({ queryKey: ['meetings'] }), queryClient.invalidateQueries({ queryKey: ['contacts'] }), queryClient.invalidateQueries({ queryKey: ['home'] })]); update({ q: null, view: null, page: '1', meeting: id }); setNotice('Manual meeting marker saved by the backend. Calendar booking remains unconfirmed.') }} />}</div></AppShell>
}
