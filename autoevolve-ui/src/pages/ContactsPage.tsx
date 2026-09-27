import { useCallback, useEffect, useMemo, useState, type FormEvent } from 'react'
import { keepPreviousData, useMutation, useQuery, useQueryClient } from '@tanstack/react-query'
import { createColumnHelper, flexRender, getCoreRowModel, useReactTable } from '@tanstack/react-table'
import { useSearchParams } from 'react-router-dom'
import { ArrowDown, Building2, ChevronLeft, ChevronRight, Clock3, ExternalLink, Mail, Plus, Search, Send, X } from 'lucide-react'
import { addContact, contactDetail, contactsPage, draftOutreach, type Contact, type ContactDetail, type ContactFilters, type Sort, type Stage } from '../api/contacts'
import { useCredentials } from '../app/Auth'
import { AppShell } from '../components/Shell'
import { DataState, LoadingRows, MetricCard, RightDrawer, StateBadge } from '../components/Primitives'

const stages: { label: string; value: Stage | '' }[] = [
  { label: 'All', value: '' }, { label: 'New', value: 'new' },
  { label: 'Qualified', value: 'qualified' }, { label: 'Draft ready', value: 'draft_ready' },
  { label: 'Contacted', value: 'contacted' }, { label: 'Suppressed', value: 'suppressed' },
]
const sorts: { label: string; value: Sort }[] = [
  { label: 'Last updated', value: 'recent' }, { label: 'Oldest updated', value: 'oldest' },
  { label: 'Contact name', value: 'name' }, { label: 'Fit score', value: 'score' },
  { label: 'Company', value: 'company' },
]
const column = createColumnHelper<Contact>()

function initials(value: string) { return value.split(/\s+/).slice(0, 2).map(word => word[0] || '').join('').toUpperCase() || '—' }
function displayName(contact: Contact) { return contact.full_name || contact.email || 'Unnamed contact' }
function dateText(value: string | null | undefined) {
  if (!value) return 'No touch'
  const date = new Date(value)
  if (Number.isNaN(date.getTime())) return 'Unknown'
  const days = Math.round((date.getTime() - Date.now()) / 86_400_000)
  if (Math.abs(days) < 1) return new Intl.DateTimeFormat(undefined, { hour: 'numeric', minute: '2-digit' }).format(date)
  if (Math.abs(days) < 31) return new Intl.RelativeTimeFormat(undefined, { numeric: 'auto' }).format(days, 'day')
  return new Intl.DateTimeFormat(undefined, { month: 'short', day: 'numeric', year: 'numeric' }).format(date)
}
function emailState(contact: Contact) {
  if (!contact.email) return <span className="email-state muted"><span className="status-dot" />No email</span>
  const state = contact.verification_status?.toLowerCase()
  if (state === 'valid') return <span className="email-state green"><span className="status-dot" />Verified</span>
  if (state === 'invalid' || state === 'disposable') return <span className="email-state red"><span className="status-dot" />{state === 'invalid' ? 'Invalid' : 'Disposable'}</span>
  return <span className="email-state yellow"><span className="status-dot" />Unverified</span>
}
function nextAction(contact: Contact) {
  if (contact.stage === 'suppressed') return 'Suppressed'
  if (contact.stage === 'draft_ready' || contact.stage === 'approved') return 'View draft'
  if (contact.email) return 'Draft outreach'
  return 'Needs email'
}

function ContactTable({ items, selected, onSelect }: { items: Contact[]; selected: string | null; onSelect: (id: string) => void }) {
  const columns = useMemo(() => [
    column.display({ id: 'contact', header: 'Contact', cell: info => <div className="person-cell"><span className="avatar row-avatar">{initials(displayName(info.row.original))}</span><span className="cell-truncate">{displayName(info.row.original)}</span></div> }),
    column.accessor('company', { header: 'Company', cell: info => <div className="company-cell"><span className="company-icon"><Building2 size={14} /></span><span className="cell-truncate">{info.getValue() || info.row.original.company_domain || '—'}</span></div> }),
    column.accessor('job_title', { header: 'Role', cell: info => <span className="cell-truncate">{info.getValue() || '—'}</span> }),
    column.display({ id: 'email', header: 'Email status', cell: info => emailState(info.row.original) }),
    column.accessor('lead_score', { header: 'Fit', cell: info => <span className={`score ${info.getValue() >= 80 ? 'high' : info.getValue() >= 60 ? 'medium' : 'low'}`}>{info.getValue()}</span> }),
    column.accessor('source', { header: 'Source', cell: info => <span className="source-cell cell-truncate">{info.getValue()}</span> }),
    column.accessor('last_touch_at', { header: 'Last touch', cell: info => <span title={info.getValue() || undefined}>{dateText(info.getValue())}</span> }),
    column.display({ id: 'action', header: 'Next action', cell: info => <button className="row-action" onClick={event => { event.stopPropagation(); onSelect(info.row.original.id) }}>{nextAction(info.row.original)}</button> }),
  ], [onSelect])
  const table = useReactTable({ data: items, columns, getCoreRowModel: getCoreRowModel() })
  return <div className="table-scroll"><table className="contacts-table"><thead>{table.getHeaderGroups().map(group => <tr key={group.id}>{group.headers.map(header => <th key={header.id}>{flexRender(header.column.columnDef.header, header.getContext())}</th>)}</tr>)}</thead><tbody>{table.getRowModel().rows.map(row => <tr key={row.id} className={selected === row.original.id ? 'selected' : ''} tabIndex={0} onClick={() => onSelect(row.original.id)} onKeyDown={event => { if (event.key === 'Enter' || event.key === ' ') { event.preventDefault(); onSelect(row.original.id) } }} aria-selected={selected === row.original.id}>{row.getVisibleCells().map(cell => <td key={cell.id}>{flexRender(cell.column.columnDef.cell, cell.getContext())}</td>)}</tr>)}</tbody></table></div>
}

function ContactDrawer({ id, onClose }: { id: string; onClose: () => void }) {
  const credentials = useCredentials()
  const queryClient = useQueryClient()
  const [tab, setTab] = useState<'overview' | 'company' | 'activity'>('overview')
  const [token, setToken] = useState('')
  const [showDraftPrompt, setShowDraftPrompt] = useState(false)
  const [actionError, setActionError] = useState('')
  const [confirmation, setConfirmation] = useState('')
  const detail = useQuery({ queryKey: ['contact', id], queryFn: () => contactDetail(credentials, id) })
  const draft = useMutation({ mutationFn: () => draftOutreach(credentials, id, token), onSuccess: async () => {
    await Promise.all([queryClient.invalidateQueries({ queryKey: ['contacts'] }), queryClient.invalidateQueries({ queryKey: ['contact', id] })])
    setToken('')
    setShowDraftPrompt(false)
    setActionError('')
    setConfirmation('Draft saved. Review it before approval or sending.')
  } })
  useEffect(() => { setTab('overview'); setToken(''); setShowDraftPrompt(false); setActionError(''); setConfirmation('') }, [id])
  const contact = detail.data
  const canDraft = Boolean(contact?.email && contact.stage !== 'suppressed')
  const companyDescription = contact && typeof contact.company_profile?.summary?.description === 'string'
    ? contact.company_profile.summary.description : null
  async function submitDraft(event: FormEvent<HTMLFormElement>) {
    event.preventDefault()
    setActionError('')
    setConfirmation('')
    try { await draft.mutateAsync() } catch (reason) { setActionError(reason instanceof Error ? reason.message : 'Draft failed') }
  }
  return <RightDrawer title="Contact details" onClose={onClose}>
    {detail.isPending ? <div className="drawer-state"><span className="skeleton medium" /><span className="skeleton medium" /><span className="skeleton short" /></div> : detail.isError ? <DataState title="Contact unavailable" detail={detail.error.message} retry={() => detail.refetch()} /> : contact ? <>
      <div className="drawer-identity"><span className="avatar detail-avatar">{initials(displayName(contact))}</span><div className="drawer-name"><h2>{displayName(contact)}</h2><p>{contact.job_title || 'Role not provided'}</p><span className="drawer-company"><Building2 size={14} />{contact.company || contact.company_domain || 'Company not provided'}</span></div></div>
      <div className="drawer-contact-methods">
        {contact.email ? <a href={`mailto:${contact.email}`}><Mail size={16} /><span>{contact.email}</span></a> : <div><Mail size={16} /><span>No email on record</span></div>}
        {contact.contact_profile.linkedin_url && <a href={contact.contact_profile.linkedin_url} target="_blank" rel="noreferrer"><ExternalLink size={16} /><span>LinkedIn profile</span></a>}
        {contact.phone && <a href={`tel:${contact.phone}`}><span className="phone-icon">☎</span><span>{contact.phone}</span></a>}
        {contact.country && <div><span className="location-icon">⌖</span><span>{contact.country}</span></div>}
        <div><Clock3 size={16} /><span>Updated {dateText(contact.updated_at)}</span></div>
      </div>
      <div className="drawer-status"><StateBadge tone={contact.stage === 'suppressed' ? 'red' : contact.stage === 'draft_ready' ? 'blue' : 'neutral'}>{contact.stage.replaceAll('_', ' ')}</StateBadge><span className="score detail-score">{contact.lead_score}</span></div>
      <div className="drawer-footer">
        {confirmation && <p className="success-message" role="status">{confirmation}</p>}
        {canDraft ? showDraftPrompt ? <form onSubmit={submitDraft}><label className="sr-only" htmlFor="draft-token">Founder action token</label><input id="draft-token" type="password" placeholder="Founder action token" autoComplete="off" required value={token} onChange={event => setToken(event.target.value)} /><div className="draft-prompt-actions"><button type="button" className="button secondary" onClick={() => { setShowDraftPrompt(false); setToken(''); setActionError('') }}>Cancel</button><button className="button primary" disabled={draft.isPending}><Send size={16} />{draft.isPending ? 'Saving…' : 'Save draft'}</button></div></form> : <button className="button primary" onClick={() => setShowDraftPrompt(true)}><Send size={16} />{contact.drafts.length ? 'Create another draft' : 'Draft outreach'}</button> : <p className="muted-copy">{contact.stage === 'suppressed' ? 'Outreach is disabled for suppressed contacts.' : 'An email is needed to draft outreach.'}</p>}
        {actionError && <p className="form-error" role="alert">{actionError}</p>}
      </div>
      <div className="drawer-tabs" role="tablist" aria-label="Contact detail sections">{(['overview', 'company', 'activity'] as const).map(value => <button key={value} role="tab" aria-selected={tab === value} onClick={() => setTab(value)}>{value[0].toUpperCase() + value.slice(1)}</button>)}</div>
      <div className="drawer-body">
        {tab === 'overview' && <>
          <section className="detail-card"><h3>About</h3>{companyDescription && <p className="about-summary">{companyDescription}</p>}<dl className="detail-grid"><div><dt>Fit score</dt><dd>{contact.lead_score}</dd></div><div><dt>Email</dt><dd>{emailState(contact)}</dd></div><div><dt>Source</dt><dd>{contact.source}</dd></div><div><dt>Last touch</dt><dd>{dateText(contact.last_touch_at)}</dd></div></dl></section>
          <section className="detail-card"><h3>Contact context</h3>{contact.message ? <p className="long-text">{contact.message}</p> : <p className="muted-copy">No intake message on record.</p>}{contact.source_detail && <p className="source-detail">Source detail: {contact.source_detail}</p>}</section>
          <section className="detail-card"><h3>Latest draft</h3>{contact.drafts.length ? <><strong>{contact.drafts[0].subject}</strong><p className="muted-copy">Status: {contact.drafts[0].status}</p></> : <p className="muted-copy">No outreach draft yet.</p>}</section>
        </>}
        {tab === 'company' && <CompanyPanel contact={contact} />}
        {tab === 'activity' && <ActivityPanel contact={contact} />}
      </div>
    </> : null}
  </RightDrawer>
}

function CompanyPanel({ contact }: { contact: ContactDetail }) {
  const profile = contact.company_profile
  const summary = profile?.summary && typeof profile.summary === 'object' ? profile.summary as Record<string, unknown> : null
  const entries = summary ? Object.entries(summary).filter(([, value]) => typeof value === 'string' || typeof value === 'number') : []
  return <section className="detail-card"><h3>{contact.company || contact.company_domain || 'Company'}</h3>{contact.company_domain && <a className="company-domain" href={`https://${contact.company_domain}`} target="_blank" rel="noreferrer">{contact.company_domain}<ExternalLink size={13} /></a>}{entries.length ? <dl className="company-fields">{entries.map(([key, value]) => <div key={key}><dt>{key.replaceAll('_', ' ')}</dt><dd>{String(value)}</dd></div>)}</dl> : <p className="muted-copy">No company research is stored for this contact.</p>}</section>
}

function ActivityPanel({ contact }: { contact: ContactDetail }) {
  const items = [...contact.interactions.map(item => ({ id: `i${item.id}`, title: `${item.direction} ${item.channel}`, detail: item.subject || item.kind, at: item.created_at })), ...contact.recent_events.map(item => ({ id: `e${item.id}`, title: item.event.replaceAll('.', ' '), detail: '', at: item.created_at }))].sort((a, b) => String(b.at).localeCompare(String(a.at)))
  return <section className="detail-card"><h3>Recent activity</h3>{items.length ? <ul className="activity-list">{items.map(item => <li key={item.id}><strong>{item.title}</strong>{item.detail && <span>{item.detail}</span>}<small>{dateText(item.at)}</small></li>)}</ul> : <p className="muted-copy">No activity recorded yet.</p>}</section>
}

function AddContactDialog({ onClose, onCreated }: { onClose: () => void; onCreated: (id: string) => void }) {
  const credentials = useCredentials()
  const queryClient = useQueryClient()
  const [error, setError] = useState('')
  const create = useMutation({ mutationFn: ({ value, token }: { value: Parameters<typeof addContact>[1]; token: string }) => addContact(credentials, value, token) })
  async function submit(event: FormEvent<HTMLFormElement>) {
    event.preventDefault()
    setError('')
    const data = new FormData(event.currentTarget)
    const email = String(data.get('email') || '').trim()
    const phone = String(data.get('phone') || '').trim()
    if (!email && !phone) { setError('Enter an email or phone number.'); return }
    const value = { full_name: String(data.get('full_name') || '').trim() || null, email: email || null, phone: phone || null, company: String(data.get('company') || '').trim() || null, job_title: String(data.get('job_title') || '').trim() || null, source: 'manual', consent: false }
    try {
      const result = await create.mutateAsync({ value, token: String(data.get('token') || '') })
      await queryClient.invalidateQueries({ queryKey: ['contacts'] })
      onCreated(result.lead.id)
    } catch (reason) { setError(reason instanceof Error ? reason.message : 'Could not add contact') }
  }
  return <div className="modal-backdrop" onMouseDown={event => { if (event.target === event.currentTarget) onClose() }}><div className="modal" role="dialog" aria-modal="true" aria-labelledby="add-contact-title"><button className="icon-button modal-close" aria-label="Close" onClick={onClose}><X size={19} /></button><h2 id="add-contact-title">Add contact</h2><p>Save a person in the existing sales lead store.</p><form onSubmit={submit}><label>Name<input name="full_name" maxLength={160} /></label><div className="form-pair"><label>Email<input name="email" type="email" /></label><label>Phone<input name="phone" maxLength={60} /></label></div><div className="form-pair"><label>Company<input name="company" maxLength={200} /></label><label>Role<input name="job_title" maxLength={160} /></label></div><label>Founder action token<input name="token" type="password" autoComplete="off" required /></label>{error && <p className="form-error" role="alert">{error}</p>}<div className="modal-actions"><button type="button" className="button secondary" onClick={onClose}>Cancel</button><button type="submit" className="button primary" disabled={create.isPending}>{create.isPending ? 'Saving…' : 'Add contact'}</button></div></form></div></div>
}

export function ContactsPage() {
  const credentials = useCredentials()
  const [params, setParams] = useSearchParams()
  const stageParam = params.get('stage') || ''
  const sortParam = params.get('sort') || 'recent'
  const pageParam = Number(params.get('page') || 1)
  const filters: ContactFilters = { page: Number.isInteger(pageParam) && pageParam > 0 ? pageParam : 1, q: params.get('q') || '', stage: stages.some(item => item.value === stageParam) ? stageParam as Stage | '' : '', sort: sorts.some(item => item.value === sortParam) ? sortParam as Sort : 'recent' }
  const selected = params.get('contact')
  const [searchText, setSearchText] = useState(filters.q)
  const [showAdd, setShowAdd] = useState(false)
  const update = useCallback((values: Record<string, string | null>, replace = false) => {
    setParams(current => { const next = new URLSearchParams(current); Object.entries(values).forEach(([key, value]) => value ? next.set(key, value) : next.delete(key)); return next }, { replace })
  }, [setParams])
  useEffect(() => { setSearchText(filters.q) }, [filters.q])
  useEffect(() => { if (searchText === filters.q) return; const timer = window.setTimeout(() => update({ q: searchText, page: '1' }, true), 300); return () => window.clearTimeout(timer) }, [searchText, filters.q, update])
  const query = useQuery({ queryKey: ['contacts', filters.page, filters.q, filters.stage, filters.sort], queryFn: () => contactsPage(credentials, filters), placeholderData: keepPreviousData })
  const result = query.data
  const pages = result ? Math.max(1, Math.ceil(result.total / result.page_size)) : 1
  useEffect(() => { if (result && filters.page > pages) update({ page: String(pages) }, true) }, [result, pages, filters.page, update])
  const onSelect = useCallback((id: string) => update({ contact: id }), [update])
  return <AppShell active="Contacts" query={searchText} onQueryChange={setSearchText}>
    <div className={`page-layout ${selected ? 'with-drawer' : ''}`}>
      <main className="page-main">
        <div className="page-content">
          <div className="page-heading"><div><h1>Contacts</h1><p>Resolve, qualify, and manage your contacts.</p></div><div className="heading-actions"><button className="button primary" onClick={() => setShowAdd(true)}><Plus size={18} />Add contact</button></div></div>
          <div className="metrics-grid"><MetricCard label="Total contacts" value={result?.metrics.total} kind="total" /><MetricCard label="Can draft outreach" value={result?.metrics.ready} kind="ready" /><MetricCard label="Verified emails" value={result?.metrics.verified} kind="verified" /><MetricCard label="Suppressed" value={result?.metrics.suppressed} kind="suppressed" /></div>
          <div className="table-toolbar"><div className="view-tabs" role="group" aria-label="Contact status filter">{stages.map(item => <button key={item.label} className={filters.stage === item.value ? 'active' : ''} onClick={() => update({ stage: item.value, page: '1' })}>{item.label}{result ? ` (${item.value ? result.metrics.by_stage[item.value] || 0 : result.metrics.total})` : ''}</button>)}</div><div className="toolbar-actions"><label className="sort-control"><span>Sort:</span><select aria-label="Sort contacts" value={filters.sort} onChange={event => update({ sort: event.target.value, page: '1' })}>{sorts.map(item => <option key={item.value} value={item.value}>{item.label}</option>)}</select><ArrowDown size={13} /></label></div></div>
          {filters.q && <div className="filter-chip"><Search size={14} /> Search: {filters.q}<button aria-label="Clear search" onClick={() => { setSearchText(''); update({ q: null, page: '1' }) }}><X size={13} /></button></div>}
          {query.isError && result && <div className="operational-error" role="alert">Refresh failed: {query.error.message} <button onClick={() => query.refetch()}>Retry</button></div>}
          <div className="table-panel">{query.isPending ? <LoadingRows /> : query.isError && !result ? <DataState title="Contacts could not be loaded" detail={query.error.message} retry={() => query.refetch()} /> : result?.items.length ? <ContactTable items={result.items} selected={selected} onSelect={onSelect} /> : <DataState title="No contacts found" detail={filters.q || filters.stage ? 'Try clearing the search or choosing another status.' : 'Add a contact to get started.'} />}</div>
          <div className="table-footer"><span>{result ? `Showing ${result.total ? (filters.page - 1) * result.page_size + 1 : 0}–${Math.min(filters.page * result.page_size, result.total)} of ${result.total.toLocaleString()} contacts` : 'Loading contacts…'}{query.isFetching && !query.isPending && <span className="refreshing"> · Refreshing…</span>}</span><div className="pagination"><button aria-label="Previous page" disabled={filters.page <= 1} onClick={() => update({ page: String(filters.page - 1), contact: null })}><ChevronLeft size={17} /></button><span className="current-page">{filters.page}</span><span className="page-total">of {pages}</span><button aria-label="Next page" disabled={filters.page >= pages} onClick={() => update({ page: String(filters.page + 1), contact: null })}><ChevronRight size={17} /></button></div></div>
        </div>
      </main>
      {selected && <ContactDrawer id={selected} onClose={() => update({ contact: null })} />}
    </div>
    {showAdd && <AddContactDialog onClose={() => setShowAdd(false)} onCreated={id => { setShowAdd(false); update({ contact: id, stage: null, q: null, page: '1' }); setSearchText('') }} />}
  </AppShell>
}
