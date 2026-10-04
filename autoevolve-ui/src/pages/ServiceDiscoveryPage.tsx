import { useState, type FormEvent } from 'react'
import { useQuery, useQueryClient } from '@tanstack/react-query'
import { ArrowRight, RefreshCw } from 'lucide-react'
import { Link } from 'react-router-dom'
import { retargetService, searchService, serviceDiscovery, type ServiceDiscoveryView, type ServiceTargetEdit } from '../api/serviceDiscovery'
import { useCredentials } from '../app/Auth'
import { AppShell } from '../components/Shell'
import { DataState, LoadingRows, StateBadge } from '../components/Primitives'

type Run = ServiceDiscoveryView['runs'][number]
const lines = (value: string) => value.split(/\n|,/).map(item => item.trim()).filter(Boolean)

function TargetForm({ run, token, busy, onSearch }: { run: Run; token: string; busy: boolean; onSearch: (target: ServiceTargetEdit) => Promise<void> }) {
  const [industry, setIndustry] = useState(run.plan.buyer_industry)
  const [keywords, setKeywords] = useState(run.plan.search_keywords.join('\n'))
  const [titles, setTitles] = useState(run.plan.buyer_titles.join('\n'))
  const [market, setMarket] = useState(run.market || '')
  const [count, setCount] = useState(run.desired_contacts)
  function submit(event: FormEvent<HTMLFormElement>) {
    event.preventDefault()
    void onSearch({
      buyer_industry: industry.trim(), search_keywords: lines(keywords), buyer_titles: lines(titles),
      market: market.trim() || null, desired_contacts: count,
    })
  }
  return <form className="onboarding-form" onSubmit={submit}>
    <div className="onboarding-grid">
      <label>Buyer industry (context)<input value={industry} onChange={event => setIndustry(event.target.value)} minLength={2} maxLength={120} required /></label>
      <label>Market (optional)<input value={market} onChange={event => setMarket(event.target.value)} maxLength={120} placeholder="All markets" /></label>
    </div>
    <div className="onboarding-grid">
      <label>Search keywords · one per line<textarea value={keywords} onChange={event => setKeywords(event.target.value)} required /></label>
      <label>Buyer titles · one per line<textarea value={titles} onChange={event => setTitles(event.target.value)} required /></label>
    </div>
    <label>Number of contacts<input type="number" min={1} max={25} value={count} onChange={event => setCount(Number(event.target.value))} required /></label>
    <button className="button secondary" disabled={busy || !token.trim()}><RefreshCw size={15} /> Search again with edits</button>
  </form>
}

export function ServiceDiscoveryPage() {
  const credentials = useCredentials()
  const queryClient = useQueryClient()
  const query = useQuery({ queryKey: ['service-discovery'], queryFn: () => serviceDiscovery(credentials) })
  const [service, setService] = useState('')
  const [count, setCount] = useState(5)
  const [token, setToken] = useState('')
  const [selectedId, setSelectedId] = useState<string | null>(null)
  const [pending, setPending] = useState('')
  const [error, setError] = useState('')
  const runs = query.data?.runs || []
  const selected = runs.find(item => item.id === selectedId) || runs[0]

  async function runSearch(action: () => Promise<ServiceDiscoveryView>, label: string) {
    if (!token.trim()) { setError('Enter the founder action token before searching.'); return }
    setError(''); setPending(label)
    try {
      const view = await action()
      queryClient.setQueryData(['service-discovery'], view)
      if (label === 'new service') setSelectedId(view.runs[0]?.id || null)
      await queryClient.invalidateQueries({ queryKey: ['contacts'] })
    } catch (reason) { setError(reason instanceof Error ? reason.message : 'Service search failed.') }
    finally { setPending('') }
  }

  function submit(event: FormEvent<HTMLFormElement>) {
    event.preventDefault()
    void runSearch(() => searchService(credentials, service.trim(), count, token), 'new service')
  }

  return <AppShell active="Service discovery" query="" onQueryChange={() => undefined}><div className="page-layout"><main className="page-main"><div className="page-content onboarding-page">
    <div className="page-heading"><div><h1>Start with a service</h1><p>Describe what you sell and choose how many contacts to find. AI sets the search terms; configured prospect providers return real contact previews.</p></div><div className="heading-actions"><Link className="button secondary" to="/onboarding">Company-first setup</Link></div></div>
    <section className="onboarding-panel"><div className="onboarding-panel-head"><h2>1. Enter a service</h2><p>A single submission plans and runs the first prospect search. You can edit the AI targeting and search again afterward.</p></div>
      <form className="onboarding-form" onSubmit={submit}>
        <label>Service to sell<textarea value={service} onChange={event => setService(event.target.value)} minLength={5} maxLength={1000} placeholder="e.g. Appointment scheduling for dental clinics" required /></label>
        <label>Number of contacts<input type="number" min={1} max={25} value={count} onChange={event => setCount(Number(event.target.value))} required /></label>
        <label>Founder action token<input type="password" autoComplete="off" value={token} onChange={event => setToken(event.target.value)} required /></label>
        <p className="operational-note">Search uses Apollo previews first, then Prospeo when more contacts are needed. Local 24-hour request caps limit calls. Email and phone reveal are separate actions and do not run here.</p>
        <button className="button primary" disabled={!!pending}>{pending === 'new service' ? 'Planning and searching…' : 'Find contacts'} <ArrowRight size={16} /></button>
      </form>
    </section>
    {pending && <p className="operational-note" role="status">{pending === 'new service' ? 'AI is choosing keywords and buyer titles, then searching providers…' : 'Searching providers with your edits…'}</p>}
    {error && <p className="form-error" role="alert">{error}</p>}
    {query.isPending ? <LoadingRows label="Loading saved service searches" /> : query.isError && !query.data ? <DataState title="Service searches could not be loaded" detail={query.error.message} retry={() => query.refetch()} /> : selected && <section className="onboarding-panel service-results"><div className="onboarding-panel-head"><h2>2. Review saved contacts</h2><p>These are contact previews, not verified service fit. Open a contact to review its saved record before outreach.</p></div>
      {runs.length > 1 && <label className="service-run-picker">Saved searches<select aria-label="Saved service searches" value={selected.id} onChange={event => setSelectedId(event.target.value)}>{runs.map(item => <option key={item.id} value={item.id}>{item.service.slice(0, 70)} · {item.contacts.length} contacts</option>)}</select></label>}
      <div className="onboarding-progress"><span>Service: <strong>{selected.service}</strong></span><StateBadge tone={selected.contacts.length ? 'green' : 'yellow'}>{selected.status.replaceAll('_', ' ')}</StateBadge><span>{selected.contacts.length} of {selected.desired_contacts} requested</span></div>
      <div className="onboarding-proposal"><h3>AI targeting hypothesis</h3><p>Buyer industry: <strong>{selected.plan.buyer_industry}</strong>{selected.market ? ` · Market: ${selected.market}` : ' · All markets'}</p><p>Search keywords: {selected.plan.search_keywords.join(', ')}</p><p>Likely buyers: {selected.plan.buyer_titles.join(', ')}</p><p>{selected.plan.rationale}</p><p>Provider previews: {Object.entries(selected.provider_counts || {}).map(([provider, total]) => `${provider} ${total}`).join(' · ') || 'None'}</p></div>
      <TargetForm key={`${selected.id}:${selected.plan.buyer_industry}:${selected.market || ''}`} run={selected} token={token} busy={!!pending} onSearch={target => runSearch(() => retargetService(credentials, selected.id, target, token), 'retarget')} />
      {(selected.warnings || []).map((warning, index) => <p className="operational-error" key={`${index}:${warning}`}>{warning}</p>)}
      {selected.contacts.length ? <div className="onboarding-list">{selected.contacts.map(contact => <div className="onboarding-candidate" key={contact.lead_id}><div><strong>{contact.name}</strong><small>{[contact.job_title, contact.company, contact.country, contact.source].filter(Boolean).join(' · ')}</small><small>{contact.email || 'Email not revealed'}</small></div><Link className="button secondary" to={`/contacts?contact=${encodeURIComponent(contact.lead_id)}`}>Review contact <ArrowRight size={15} /></Link></div>)}</div> : <p className="operational-note">No contacts were saved. Edit the search keywords, buyer titles, or market and search again.</p>}
    </section>}
  </div></main></div></AppShell>
}
