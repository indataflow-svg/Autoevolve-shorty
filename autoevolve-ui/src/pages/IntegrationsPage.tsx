import { useState, type FormEvent } from 'react'
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'
import { useSearchParams } from 'react-router-dom'
import { BookOpen, Check, ChevronDown, KeyRound, PlugZap, Search, ShieldAlert } from 'lucide-react'
import { useCredentials } from '../app/Auth'
import { incidentsView, integrationsView, saveProviderKeys, testProviderKeys, type ProviderGroup } from '../api/operational'
import { AppShell } from '../components/Shell'
import { DataState, RightDrawer, StateBadge } from '../components/Primitives'

function status(group: ProviderGroup) {
  if (group.configured_count === 0) return { label: 'Not configured', tone: 'neutral' as const }
  if (group.missing_keys.length) return { label: 'Partially configured', tone: 'yellow' as const }
  return { label: 'Keys configured', tone: 'green' as const }
}

function ProviderDrawer({ group, close }: { group: ProviderGroup; close: () => void }) {
  const credentials = useCredentials()
  const queryClient = useQueryClient()
  const [keyName, setKeyName] = useState(group.missing_keys[0] || group.configured_keys[0] || '')
  const [value, setValue] = useState('')
  const [token, setToken] = useState('')
  const [feedback, setFeedback] = useState('')
  const [error, setError] = useState('')
  const [testedValue, setTestedValue] = useState('')
  const test = useMutation({ mutationFn: () => testProviderKeys(credentials, { group: group.id, values: { [keyName]: value.trim() } }, token.trim()) })
  const save = useMutation({ mutationFn: () => saveProviderKeys(credentials, { group: group.id, values: { [keyName]: value.trim() } }, token.trim()), onSuccess: async () => {
    await queryClient.invalidateQueries({ queryKey: ['integrations'] })
    setValue('')
    setTestedValue('')
    setFeedback('Key saved and configuration refreshed from the backend. Restart may be required before the provider uses it; health is not verified.')
  } })
  async function submit(event: FormEvent, action: 'test' | 'save') {
    event.preventDefault()
    setError('')
    setFeedback('')
    if (!keyName || !value.trim() || !token.trim()) { setError('Choose a key, enter its value, and provide the founder action token.'); return }
    try {
      if (action === 'test') {
        await test.mutateAsync()
        setTestedValue(value)
        setFeedback('Backend validation passed. This does not prove provider health or save the key.')
      } else {
        if (testedValue !== value) { setError('Test this exact value before saving.'); return }
        await save.mutateAsync()
      }
    } catch (reason) { setError(reason instanceof Error ? reason.message : 'The action failed.') }
  }
  const keyNames = [...group.configured_keys, ...group.missing_keys]
  const current = status(group)
  return <RightDrawer title="Integration details" onClose={close} className="integration-drawer">
    <div className="drawer-identity"><span className="provider-icon"><PlugZap size={24} /></span><div className="drawer-name"><h2>{group.label}</h2><p>{group.category}</p></div></div>
    <div className="drawer-status"><StateBadge tone={current.tone}>{current.label}</StateBadge><span className="muted-copy">{group.configured_count} of {group.total_keys} keys present</span></div>
    <div className="drawer-tabs"><button aria-selected="true">Overview</button></div>
    <div className="drawer-body">
      <section className="detail-card"><h3>Capabilities</h3><div className="tag-list">{group.capabilities.map(capability => <span key={capability}>{capability}</span>)}</div><p className="operational-note">Capabilities describe this integration; they are not health checks.</p></section>
      <section className="detail-card"><h3>Configuration</h3><div className="key-list">{keyNames.map(key => <div key={key}><code>{key}</code><StateBadge tone={group.configured_keys.includes(key) ? 'green' : 'neutral'}>{group.configured_keys.includes(key) ? 'Present' : 'Missing'}</StateBadge></div>)}</div><p className="operational-note">Saved values are never returned by the API.</p></section>
    </div>
    <div className="drawer-footer"><form onSubmit={event => submit(event, 'test')}>
      <label className="operational-label">Key to configure<select value={keyName} onChange={event => { setKeyName(event.target.value); setTestedValue(''); setFeedback('') }}>{keyNames.map(key => <option key={key} value={key}>{key}</option>)}</select></label>
      <label className="operational-label">New value<input aria-label="New key value" type={/(KEY|TOKEN|SECRET|PASSWORD)/.test(keyName) ? 'password' : 'text'} autoComplete="off" value={value} onChange={event => { setValue(event.target.value); setTestedValue(''); setFeedback('') }} /></label>
      <label className="operational-label">Founder action token<input type="password" aria-label="Founder action token" autoComplete="off" value={token} onChange={event => setToken(event.target.value)} /></label>
      {group.id === 'ai_gateway' && <p className="muted-copy">Testing an AI gateway URL calls its /models endpoint.</p>}
      {error && <p className="form-error" role="alert">{error}</p>}{feedback && <p className="success-message" role="status">{feedback}</p>}
      <div className="operational-actions"><button className="button secondary" type="submit" disabled={test.isPending || save.isPending}>Test value</button><button className="button primary" type="button" onClick={event => submit(event, 'save')} disabled={test.isPending || save.isPending || testedValue !== value || !value}>Save key</button></div>
    </form></div>
  </RightDrawer>
}

export function IntegrationsPage() {
  const credentials = useCredentials()
  const [params, setParams] = useSearchParams()
  const category = params.get('category') || 'All'
  const search = params.get('q') || ''
  const sort = params.get('sort') === 'configured' ? 'configured' : 'name'
  const selected = params.get('integration')
  const showIncidents = params.get('view') === 'incidents'
  const query = useQuery({ queryKey: ['integrations'], queryFn: () => integrationsView(credentials) })
  const incidents = useQuery({ queryKey: ['incidents'], queryFn: () => incidentsView(credentials), enabled: showIncidents })
  const groups = query.data?.groups || []
  const categories = ['All', ...Array.from(new Set(groups.map(group => group.category)))]
  const visible = groups.filter(group => (category === 'All' || group.category === category) && `${group.label} ${group.category} ${group.capabilities.join(' ')}`.toLowerCase().includes(search.toLowerCase())).sort((a, b) => sort === 'configured' ? b.configured_count - a.configured_count || a.label.localeCompare(b.label) : a.label.localeCompare(b.label))
  const active = groups.find(group => group.id === selected)
  function update(changes: Record<string, string | null>) { const next = new URLSearchParams(params); for (const [key, value] of Object.entries(changes)) { if (value) next.set(key, value); else next.delete(key) } setParams(next) }
  return <AppShell active="Integrations" query={search} onQueryChange={value => update({ q: value, integration: null })}>
    <div className="page-layout"><main className="page-main"><div className="page-content operational-page">
      <div className="page-heading"><div><h1>Integrations</h1><p>Configure the providers used by AutoEvolve.</p></div><div className="heading-actions"><a className="button secondary" href="/docs" target="_blank" rel="noreferrer"><BookOpen size={16} />View API docs</a></div></div>
      {showIncidents && <section className="home-panel" id="incidents"><div className="home-panel-heading"><h2>Service incidents</h2><button className="row-action" onClick={() => update({ view: null })}>Close</button></div>{incidents.isPending ? <p className="operational-note">Loading saved incidents…</p> : incidents.isError && !incidents.data ? <DataState title="Incidents could not be loaded" detail={incidents.error.message} retry={() => incidents.refetch()} /> : <div className="onboarding-list">{incidents.isError && <p className="operational-error" role="alert">Incident refresh failed: {incidents.error.message}</p>}{incidents.data?.incidents.filter(item => !['resolved', 'closed'].includes(item.status)).length ? incidents.data.incidents.filter(item => !['resolved', 'closed'].includes(item.status)).map(item => <div className="onboarding-candidate" key={item.id}><div><strong>{item.service} · {item.trigger}</strong><small>{item.severity} · {item.status} · {item.created_at}</small></div></div>) : <p className="operational-note">No open service incidents are recorded.</p>}</div>}</section>}
      <div className="operational-metrics"><div><PlugZap /><span>Provider groups<strong>{query.data?.total_groups ?? '—'}</strong></span></div><div><KeyRound /><span>Groups with keys<strong>{query.data?.groups_with_configuration ?? '—'}</strong></span></div><div><Check /><span>Fully configured<strong>{query.data?.fully_configured_groups ?? '—'}</strong></span></div><div><ShieldAlert /><span>Configured keys<strong>{query.data?.configured_keys ?? '—'}</strong></span></div></div>
      {query.isError && query.data && <div className="operational-error" role="alert">Refresh failed: {query.error.message} <button onClick={() => query.refetch()}>Retry</button></div>}
      <div className="table-toolbar operational-toolbar"><div className="view-tabs">{categories.map(item => <button key={item} className={category === item ? 'active' : ''} onClick={() => update({ category: item === 'All' ? null : item, integration: null })}>{item} ({item === 'All' ? groups.length : groups.filter(group => group.category === item).length})</button>)}</div><label className="sort-control">Sort <select aria-label="Sort integrations" value={sort} onChange={event => update({ sort: event.target.value })}><option value="name">Name A–Z</option><option value="configured">Most keys</option></select><ChevronDown size={14} /></label></div>
      <div className="table-panel">{query.isPending ? <DataState title="Loading integrations" detail="Reading configured provider groups." /> : query.isError && !query.data ? <DataState title="Integrations could not be loaded" detail={query.error.message} retry={() => query.refetch()} /> : visible.length ? <div className="table-scroll"><table className="operational-table"><thead><tr><th>Integration</th><th>Category</th><th>Configuration</th><th>Keys present</th><th>Capabilities</th><th>Actions</th></tr></thead><tbody>{visible.map(group => { const current = status(group); return <tr key={group.id} className={selected === group.id ? 'selected' : ''} onClick={() => update({ integration: group.id })}><td><span className="provider-name"><span className="provider-mini"><PlugZap size={17} /></span><strong>{group.label}</strong></span></td><td>{group.category}</td><td><StateBadge tone={current.tone}>{current.label}</StateBadge></td><td>{group.configured_count} / {group.total_keys}</td><td><div className="tag-list">{group.capabilities.map(value => <span key={value}>{value}</span>)}</div></td><td><button className="row-action" onClick={event => { event.stopPropagation(); update({ integration: group.id }) }}>Configure</button></td></tr> })}</tbody></table></div> : <DataState title="No integrations found" detail="Try another category or search." />}</div>
      <div className="operational-footnote"><Search size={16} /><span>Configuration is shown from saved keys. Provider health, spend, activity, and sync status are unavailable from the current backend.</span></div>
    </div></main>{active && <ProviderDrawer key={active.id} group={active} close={() => update({ integration: null })} />}</div>
  </AppShell>
}
