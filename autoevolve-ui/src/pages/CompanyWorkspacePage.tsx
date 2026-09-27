import { useCallback, useEffect, useMemo, useState, type FormEvent } from 'react'
import { keepPreviousData, useMutation, useQuery, useQueryClient } from '@tanstack/react-query'
import { createColumnHelper, flexRender, getCoreRowModel, useReactTable } from '@tanstack/react-table'
import { Link, useSearchParams } from 'react-router-dom'
import { ArrowDown, ChevronLeft, ChevronRight, ExternalLink, MapPin, Plus, Search, UsersRound, X } from 'lucide-react'
import { companiesPage, companyDetail, prospectCompany, resolveCompanyProfile, runCompanyResearch, type CompanyFilters, type CompanySort, type CompanySummary, type CompanyView } from '../api/companies'
import { useCredentials } from '../app/Auth'
import { AppShell } from '../components/Shell'
import { DataState, LoadingRows, MetricCard, RightDrawer, StateBadge } from '../components/Primitives'

const views: { label: string; value: CompanyView; metric: 'total' | 'candidates' | 'profiled' | 'with_contacts' }[] = [
  { label: 'All companies', value: 'all', metric: 'total' },
  { label: 'Candidates', value: 'candidates', metric: 'candidates' },
  { label: 'Profiled', value: 'profiled', metric: 'profiled' },
  { label: 'With contacts', value: 'with_contacts', metric: 'with_contacts' },
]
const sorts: { label: string; value: CompanySort }[] = [
  { label: 'Last seen', value: 'recent' }, { label: 'Name A–Z', value: 'name' },
  { label: 'Most contacts', value: 'contacts' },
]
const column = createColumnHelper<CompanySummary>()

function initials(value: string) { return value.split(/\s+/).slice(0, 2).map(word => word[0] || '').join('').toUpperCase() || '—' }
function dateText(value: string | null | undefined) {
  if (!value) return 'No activity'
  const date = new Date(value)
  if (Number.isNaN(date.getTime())) return 'Unknown'
  const days = Math.round((date.getTime() - Date.now()) / 86_400_000)
  if (Math.abs(days) < 1) return new Intl.DateTimeFormat(undefined, { hour: 'numeric', minute: '2-digit' }).format(date)
  if (Math.abs(days) < 31) return new Intl.RelativeTimeFormat(undefined, { numeric: 'auto' }).format(days, 'day')
  return new Intl.DateTimeFormat(undefined, { month: 'short', day: 'numeric', year: 'numeric' }).format(date)
}
function safeWebUrl(value: string | null | undefined) {
  if (!value) return null
  try {
    const url = new URL(value.startsWith('http') ? value : `https://${value}`)
    return ['http:', 'https:'].includes(url.protocol) ? url.href : null
  } catch { return null }
}
function nextStep(company: CompanySummary) {
  if (!company.has_profile && company.representative_lead_id) return 'Resolve profile'
  if (company.domain && !company.contact_count) return 'Find contacts'
  return 'View company'
}

function CompanyTable({ items, selected, onSelect }: { items: CompanySummary[]; selected: string | null; onSelect: (id: string) => void }) {
  const columns = useMemo(() => [
    column.display({ id: 'company', header: 'Company', cell: info => <div className="company-record"><span className="company-record-icon">{initials(info.row.original.name).slice(0, 1)}</span><span className="company-record-name"><strong>{info.row.original.name}</strong><small>{info.row.original.domain || 'Domain not recorded'}</small></span></div> }),
    column.accessor('industry', { header: 'Industry', cell: info => <span className="cell-truncate">{info.getValue() || '—'}</span> }),
    column.display({ id: 'profile', header: 'Profile', cell: info => info.row.original.has_profile ? <StateBadge tone={info.row.original.profile_status === 'resolved' ? 'green' : 'yellow'}>{info.row.original.profile_status || 'Saved'}</StateBadge> : <span className="muted-copy">Not resolved</span> }),
    column.accessor('contact_count', { header: 'Contacts', cell: info => <span className="contact-count"><UsersRound size={13} />{info.getValue()}</span> }),
    column.accessor('source', { header: 'Source', cell: info => <span className="source-cell">{info.getValue() || 'Profile'}</span> }),
    column.accessor('last_seen_at', { header: 'Last seen', cell: info => <span title={info.getValue() || undefined}>{dateText(info.getValue())}</span> }),
    column.display({ id: 'action', header: 'Next step', cell: info => <button className="row-action" onClick={event => { event.stopPropagation(); onSelect(info.row.original.id) }}>{nextStep(info.row.original)}</button> }),
  ], [onSelect])
  const table = useReactTable({ data: items, columns, getCoreRowModel: getCoreRowModel() })
  return <div className="table-scroll"><table className="company-table"><thead>{table.getHeaderGroups().map(group => <tr key={group.id}>{group.headers.map(header => <th key={header.id}>{flexRender(header.column.columnDef.header, header.getContext())}</th>)}</tr>)}</thead><tbody>{table.getRowModel().rows.map(row => <tr key={row.id} className={selected === row.original.id ? 'selected' : ''} tabIndex={0} onClick={() => onSelect(row.original.id)} onKeyDown={event => { if (event.key === 'Enter' || event.key === ' ') { event.preventDefault(); onSelect(row.original.id) } }} aria-selected={selected === row.original.id}>{row.getVisibleCells().map(cell => <td key={cell.id}>{flexRender(cell.column.columnDef.cell, cell.getContext())}</td>)}</tr>)}</tbody></table></div>
}

function CompanyDrawer({ id, onClose }: { id: string; onClose: () => void }) {
  const credentials = useCredentials()
  const queryClient = useQueryClient()
  const [tab, setTab] = useState<'overview' | 'contacts' | 'context'>('overview')
  const [action, setAction] = useState<'profile' | 'contacts' | null>(null)
  const [token, setToken] = useState('')
  const [provider, setProvider] = useState<'hunter' | 'apollo'>('hunter')
  const [error, setError] = useState('')
  const [confirmation, setConfirmation] = useState('')
  const detail = useQuery({ queryKey: ['company', id], queryFn: () => companyDetail(credentials, id) })
  const mutation = useMutation({ mutationFn: async () => {
    const company = detail.data
    if (!company) throw new Error('Company details are unavailable')
    if (action === 'profile' && company.representative_lead_id) { await resolveCompanyProfile(credentials, company.representative_lead_id, token); return { kind: 'profile' as const } }
    if (action === 'contacts' && company.domain) { const result = await prospectCompany(credentials, company.domain, provider, token); return { kind: 'contacts' as const, count: result.results.length } }
    throw new Error('This action is unavailable for this company')
  }, onSuccess: async result => {
    await Promise.all([queryClient.invalidateQueries({ queryKey: ['companies'] }), queryClient.invalidateQueries({ queryKey: ['company', id] }), queryClient.invalidateQueries({ queryKey: ['contacts'] })])
    setConfirmation(result.kind === 'profile' ? 'Company profile updated from the backend.' : result.count ? 'Contact search completed. Review the saved contacts below.' : 'Contact search completed; no contacts were saved.')
    setAction(null)
    setToken('')
    setError('')
  } })
  useEffect(() => { setTab('overview'); setAction(null); setToken(''); setError(''); setConfirmation('') }, [id])
  const company = detail.data
  const website = safeWebUrl(company?.website || company?.domain)
  async function submitAction(event: FormEvent<HTMLFormElement>) {
    event.preventDefault()
    setError('')
    setConfirmation('')
    try { await mutation.mutateAsync() } catch (reason) { setError(reason instanceof Error ? reason.message : 'Action failed') }
  }
  return <RightDrawer title="Company details" onClose={onClose}>
    {detail.isPending ? <div className="drawer-state"><span className="skeleton medium" /><span className="skeleton medium" /><span className="skeleton short" /></div> : detail.isError ? <DataState title="Company unavailable" detail={detail.error.message} retry={() => detail.refetch()} /> : company ? <>
      <div className="drawer-identity"><span className="company-detail-icon">{initials(company.name).slice(0, 1)}</span><div className="drawer-name"><h2>{company.name}</h2><p>{[company.industry, company.size].filter(Boolean).join(' · ') || 'Company details not enriched'}</p>{website && <a className="company-domain" href={website} target="_blank" rel="noreferrer">{company.domain || 'Website'} <ExternalLink size={12} /></a>}</div></div>
      <div className="drawer-status"><StateBadge tone={company.has_profile ? 'green' : 'yellow'}>{company.has_profile ? company.profile_status || 'Profile saved' : 'No profile'}</StateBadge><span className="muted-copy">{company.contact_count} {company.contact_count === 1 ? 'contact' : 'contacts'}</span></div>
      <div className="drawer-tabs" role="tablist" aria-label="Company detail sections">{(['overview', 'contacts', 'context'] as const).map(value => <button key={value} role="tab" aria-selected={tab === value} onClick={() => setTab(value)}>{value[0].toUpperCase() + value.slice(1)}</button>)}</div>
      <div className="drawer-body">
        {tab === 'overview' && <>
          <section className="detail-card"><h3>Company summary</h3>{company.description ? <p className="long-text">{company.description}</p> : <p className="muted-copy">No company description is saved.</p>}<dl className="company-fields"><div><dt>Industry</dt><dd>{company.industry || 'Not recorded'}</dd></div><div><dt>Size</dt><dd>{company.size || 'Not recorded'}</dd></div><div><dt>Country</dt><dd>{company.country || 'Not recorded'}</dd></div><div><dt>Source</dt><dd>{company.source || company.profile_provider || 'Not recorded'}</dd></div><div><dt>Last seen</dt><dd>{dateText(company.last_seen_at)}</dd></div></dl></section>
          <section className="detail-card"><h3>Saved contacts</h3>{company.contacts.length ? <ul className="activity-list">{company.contacts.slice(0, 3).map(contact => <li key={contact.id}><Link className="contact-link" to={`/contacts?contact=${encodeURIComponent(contact.id)}`}>{contact.full_name || contact.email || 'Unnamed contact'}</Link><span>{contact.job_title || 'Role not recorded'}</span></li>)}</ul> : <p className="muted-copy">No person record is linked to this company yet.</p>}</section>
        </>}
        {tab === 'contacts' && <section className="detail-card"><h3>Saved contacts</h3>{company.contacts.length ? <ul className="activity-list">{company.contacts.map(contact => <li key={contact.id}><Link className="contact-link" to={`/contacts?contact=${encodeURIComponent(contact.id)}`}>{contact.full_name || contact.email || 'Unnamed contact'}</Link><span>{contact.job_title || 'Role not recorded'}{contact.email ? ` · ${contact.email}` : ''}</span></li>)}</ul> : <p className="muted-copy">No person record is linked to this company yet.</p>}</section>}
        {tab === 'context' && <><section className="detail-card"><h3>Enrichment context</h3>{company.summary_line && <p className="long-text">{company.summary_line}</p>}{company.technologies.length ? <div className="tag-list">{company.technologies.map(value => <span key={value}>{value}</span>)}</div> : <p className="muted-copy">No technologies are saved.</p>}</section>{company.specialties.length > 0 && <section className="detail-card"><h3>Specialties</h3><div className="tag-list">{company.specialties.map(value => <span key={value}>{value}</span>)}</div></section>}</>}
      </div>
      <div className="drawer-footer company-actions">
        {confirmation && <p className="success-message" role="status">{confirmation}</p>}
        {action ? <form onSubmit={submitAction}>{action === 'contacts' && <label>Provider<select value={provider} onChange={event => setProvider(event.target.value as 'hunter' | 'apollo')}><option value="hunter">Hunter</option><option value="apollo">Apollo</option></select></label>}<label>Founder action token<input type="password" autoComplete="off" required value={token} onChange={event => setToken(event.target.value)} /></label><p className="muted-copy">Use the configured action token, separate from your dashboard password. This action may use provider credits.</p><div className="draft-prompt-actions"><button className="button secondary" type="button" disabled={mutation.isPending} onClick={() => { setAction(null); setToken(''); setError('') }}>Cancel</button><button className="button primary" disabled={mutation.isPending}>{mutation.isPending ? 'Working…' : action === 'profile' ? 'Resolve profile' : 'Find contacts'}</button></div></form> : <div className="company-action-buttons">{!company.has_profile && company.representative_lead_id && <button className="button secondary" onClick={() => setAction('profile')}>Resolve profile</button>}{company.domain && <button className="button primary" onClick={() => setAction('contacts')}><UsersRound size={15} />Find contacts</button>}</div>}
        {error && <p className="form-error" role="alert">{error}</p>}
      </div>
    </> : null}
  </RightDrawer>
}

function ResearchDialog({ onClose, onComplete }: { onClose: () => void; onComplete: (message: string) => void }) {
  const credentials = useCredentials()
  const queryClient = useQueryClient()
  const [error, setError] = useState('')
  const mutation = useMutation({ mutationFn: ({ input, token }: { input: { industry: string; location?: string; limit_per_provider: number }; token: string }) => runCompanyResearch(credentials, input, token) })
  async function submit(event: FormEvent<HTMLFormElement>) {
    event.preventDefault()
    const data = new FormData(event.currentTarget)
    const input = { industry: String(data.get('industry') || '').trim(), location: String(data.get('location') || '').trim() || undefined, limit_per_provider: Number(data.get('limit') || 5) }
    setError('')
    try {
      const response = await mutation.mutateAsync({ input, token: String(data.get('token') || '') })
      await queryClient.invalidateQueries({ queryKey: ['companies'] })
      onComplete(response.warnings.length ? `Research completed with ${response.warnings.length} provider warning(s). Review the saved records.` : 'Research completed. Review the saved company records.')
    } catch (reason) { setError(reason instanceof Error ? reason.message : 'Research failed') }
  }
  return <div className="modal-backdrop" onMouseDown={event => { if (event.target === event.currentTarget) onClose() }}><div className="modal" role="dialog" aria-modal="true" aria-labelledby="new-research-title"><button className="icon-button modal-close" aria-label="Close" onClick={onClose}><X size={19} /></button><h2 id="new-research-title">New company research</h2><p>Search configured providers and save company candidates. This can use provider credits.</p><form onSubmit={submit}><label>Industry<input name="industry" required minLength={2} maxLength={160} placeholder="e.g. Logistics" /></label><label>Location (optional)<input name="location" maxLength={120} placeholder="e.g. North America" /></label><label>Results per provider<select name="limit" defaultValue="5"><option value="1">1</option><option value="3">3</option><option value="5">5</option></select></label><label>Founder action token<input name="token" type="password" autoComplete="off" required /></label><p className="muted-copy">Separate from your dashboard password.</p>{error && <p className="form-error" role="alert">{error}</p>}<div className="modal-actions"><button className="button secondary" type="button" onClick={onClose}>Cancel</button><button className="button primary" disabled={mutation.isPending}>{mutation.isPending ? 'Researching…' : 'Run research'}</button></div></form></div></div>
}

export function CompanyWorkspacePage({ mode }: { mode: 'research' | 'companies' }) {
  const credentials = useCredentials()
  const [params, setParams] = useSearchParams()
  const rawView = params.get('view') || 'all'
  const rawSort = params.get('sort') || 'recent'
  const rawPage = Number(params.get('page') || 1)
  const filters: CompanyFilters = {
    page: Number.isInteger(rawPage) && rawPage > 0 ? rawPage : 1,
    q: params.get('q') || '',
    view: views.some(item => item.value === rawView) ? rawView as CompanyView : 'all',
    sort: sorts.some(item => item.value === rawSort) ? rawSort as CompanySort : 'recent',
    industry: params.get('industry') || '',
    country: params.get('country') || '',
  }
  const selected = params.get('company')
  const [searchText, setSearchText] = useState(filters.q)
  const [industryText, setIndustryText] = useState(filters.industry)
  const [countryText, setCountryText] = useState(filters.country)
  const [showResearch, setShowResearch] = useState(false)
  const [confirmation, setConfirmation] = useState('')
  const update = useCallback((values: Record<string, string | null>, replace = false) => {
    setParams(current => { const next = new URLSearchParams(current); Object.entries(values).forEach(([key, value]) => value ? next.set(key, value) : next.delete(key)); return next }, { replace })
  }, [setParams])
  useEffect(() => { setSearchText(filters.q) }, [filters.q])
  useEffect(() => { setIndustryText(filters.industry); setCountryText(filters.country) }, [filters.industry, filters.country])
  useEffect(() => { if (searchText === filters.q) return; const timer = window.setTimeout(() => update({ q: searchText, page: '1' }, true), 300); return () => window.clearTimeout(timer) }, [searchText, filters.q, update])
  const query = useQuery({ queryKey: ['companies', filters.page, filters.q, filters.view, filters.sort, filters.industry, filters.country], queryFn: () => companiesPage(credentials, filters), placeholderData: keepPreviousData })
  const result = query.data
  const pages = result ? Math.max(1, Math.ceil(result.total / result.page_size)) : 1
  useEffect(() => { if (result && filters.page > pages) update({ page: String(pages) }, true) }, [result, filters.page, pages, update])
  const onSelect = useCallback((id: string) => update({ company: id }), [update])
  const title = mode === 'research' ? 'Research' : 'Companies'
  return <AppShell active={title} query={searchText} onQueryChange={setSearchText}>
    <div className={`page-layout ${selected ? 'with-drawer' : ''}`}>
      <main className="page-main"><div className="page-content">
        <div className="page-heading"><div><h1>{title}</h1><p>{mode === 'research' ? 'Discover and review companies before spending contact credits.' : 'Review saved companies, profiles, and linked contacts.'}</p></div><div className="heading-actions">{mode === 'companies' && <Link className="button secondary" to="/research"><Search size={16} />Research</Link>}<button className="button primary" onClick={() => setShowResearch(true)}><Plus size={18} />New research</button></div></div>
        <div className="metrics-grid"><MetricCard label="Companies recorded" value={result?.metrics.total} kind="companies" /><MetricCard label="Research candidates" value={result?.metrics.candidates} kind="candidates" /><MetricCard label="Profiles saved" value={result?.metrics.profiled} kind="profiled" /><MetricCard label="With contacts" value={result?.metrics.with_contacts} kind="contacts" /></div>
        {confirmation && <p className="company-page-notice" role="status">{confirmation}<button aria-label="Dismiss message" onClick={() => setConfirmation('')}><X size={13} /></button></p>}
        <div className={mode === 'research' ? 'research-workspace-grid' : ''}>
          {mode === 'research' && <aside className="research-filters" aria-label="Research filters"><div className="filter-title">Filters<button type="button" onClick={() => { setIndustryText(''); setCountryText(''); update({ industry: null, country: null, page: '1' }) }}>Clear all</button></div><form onSubmit={event => { event.preventDefault(); update({ industry: industryText.trim(), country: countryText.trim(), page: '1' }) }}><label>Industry<input value={industryText} onChange={event => setIndustryText(event.target.value)} placeholder="All industries" maxLength={100} /></label><label>Country<input value={countryText} onChange={event => setCountryText(event.target.value)} placeholder="All countries" maxLength={100} /></label><button className="button secondary" type="submit">Apply filters</button></form><p>Industry and country appear only when saved by a provider or lead.</p></aside>}
          <div className="company-results"><div className="table-toolbar"><div className="view-tabs" role="group" aria-label="Company view filter">{views.map(item => <button key={item.value} className={filters.view === item.value ? 'active' : ''} onClick={() => update({ view: item.value === 'all' ? null : item.value, page: '1' })}>{item.label}{result ? ` (${result.metrics[item.metric]})` : ''}</button>)}</div><div className="toolbar-actions"><label className="sort-control"><span>Sort:</span><select aria-label="Sort companies" value={filters.sort} onChange={event => update({ sort: event.target.value, page: '1' })}>{sorts.map(item => <option key={item.value} value={item.value}>{item.label}</option>)}</select><ArrowDown size={13} /></label></div></div>
            {(filters.q || filters.industry || filters.country) && <div className="company-filter-chips">{filters.q && <span className="filter-chip"><Search size={13} />Search: {filters.q}<button aria-label="Clear search" onClick={() => { setSearchText(''); update({ q: null, page: '1' }) }}><X size={12} /></button></span>}{filters.industry && <span className="filter-chip">Industry: {filters.industry}<button aria-label="Clear industry" onClick={() => update({ industry: null, page: '1' })}><X size={12} /></button></span>}{filters.country && <span className="filter-chip"><MapPin size={12} />Country: {filters.country}<button aria-label="Clear country" onClick={() => update({ country: null, page: '1' })}><X size={12} /></button></span>}</div>}
            {query.isError && result && <div className="operational-error" role="alert">Refresh failed: {query.error.message} <button onClick={() => query.refetch()}>Retry</button></div>}
            <div className="table-panel">{query.isPending ? <LoadingRows label="Loading companies" /> : query.isError && !result ? <DataState title="Companies could not be loaded" detail={query.error.message} retry={() => query.refetch()} /> : result?.items.length ? <CompanyTable items={result.items} selected={selected} onSelect={onSelect} /> : <DataState title="No companies found" detail={filters.q || filters.view !== 'all' || filters.industry || filters.country ? 'Try clearing a filter or search.' : 'Run research or add a contact with a company to get started.'} />}</div>
            <div className="table-footer"><span>{result ? `Showing ${result.total ? (filters.page - 1) * result.page_size + 1 : 0}–${Math.min(filters.page * result.page_size, result.total)} of ${result.total.toLocaleString()} companies` : 'Loading companies…'}{query.isFetching && !query.isPending && <span className="refreshing"> · Refreshing…</span>}</span><div className="pagination"><button aria-label="Previous page" disabled={filters.page <= 1} onClick={() => update({ page: String(filters.page - 1), company: null })}><ChevronLeft size={17} /></button><span className="current-page">{filters.page}</span><span className="page-total">of {pages}</span><button aria-label="Next page" disabled={filters.page >= pages} onClick={() => update({ page: String(filters.page + 1), company: null })}><ChevronRight size={17} /></button></div></div>
          </div>
        </div>
      </div></main>
      {selected && <CompanyDrawer id={selected} onClose={() => update({ company: null })} />}
    </div>
    {showResearch && <ResearchDialog onClose={() => setShowResearch(false)} onComplete={message => { setShowResearch(false); setConfirmation(message); update({ page: '1', view: null, q: null, industry: null, country: null }); setSearchText('') }} />}
  </AppShell>
}
