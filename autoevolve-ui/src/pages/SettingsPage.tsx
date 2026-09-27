import { useState, type FormEvent } from 'react'
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'
import { Link, useSearchParams } from 'react-router-dom'
import { Building2, Check, ExternalLink, Globe2, LockKeyhole, Plus, Settings2 } from 'lucide-react'
import { useCredentials } from '../app/Auth'
import { createOrganization, selectOrganization, setOrganizationCapabilities, settingsView, type WorkspaceOrg } from '../api/operational'
import { AppShell } from '../components/Shell'
import { DataState, StateBadge } from '../components/Primitives'

const sections = ['Workspace', 'Public links'] as const
type Section = typeof sections[number]

function OrganizationEditor({ org, capabilities, onSaved }: { org: WorkspaceOrg; capabilities: string[]; onSaved: () => Promise<unknown> }) {
  const credentials = useCredentials()
  const [choices, setChoices] = useState<Record<string, boolean>>(org.capabilities)
  const [message, setMessage] = useState('')
  const [error, setError] = useState('')
  const save = useMutation({ mutationFn: () => setOrganizationCapabilities(credentials, org.id, choices), onSuccess: async result => { await onSaved(); setChoices(result.capabilities); setMessage('Capabilities saved and refreshed from the backend.'); setError('') } })
  const changed = capabilities.some(name => Boolean(choices[name]) !== Boolean(org.capabilities[name]))
  return <section className="settings-card"><div className="settings-card-heading"><div><h2>{org.name}</h2><p>Organization identity and enabled capabilities.</p></div><StateBadge tone="blue">{org.status || 'Status unavailable'}</StateBadge></div>
    <dl className="settings-facts"><div><dt>Name</dt><dd>{org.name}</dd></div><div><dt>URL slug</dt><dd>{org.slug}</dd></div><div><dt>Domain</dt><dd>{org.domain || 'Not recorded'}</dd></div><div><dt>Organization ID</dt><dd>{org.id}</dd></div></dl>
    <div className="settings-card-heading capabilities-heading"><div><h3>Capabilities</h3><p>Enable the functions supported by this organization.</p></div></div>
    {capabilities.length ? <div className="capability-grid">{capabilities.map(name => <label key={name} className="capability-item"><span><strong>{name.replaceAll('_', ' ')}</strong><small>{choices[name] ? 'Enabled' : 'Disabled'}</small></span><input type="checkbox" checked={Boolean(choices[name])} onChange={event => { setChoices({ ...choices, [name]: event.target.checked }); setMessage('') }} /></label>)}</div> : <p className="muted-copy">No capabilities are defined by the backend.</p>}
    {error && <p className="form-error" role="alert">{error}</p>}{message && <p className="success-message" role="status">{message}</p>}
    <div className="settings-card-actions"><button className="button primary" disabled={!changed || save.isPending} onClick={async () => { try { await save.mutateAsync() } catch (reason) { setError(reason instanceof Error ? reason.message : 'Could not save capabilities.') } }}>Save capabilities</button></div>
  </section>
}

export function SettingsPage() {
  const credentials = useCredentials()
  const queryClient = useQueryClient()
  const [params, setParams] = useSearchParams()
  const section: Section = params.get('section') === 'links' ? 'Public links' : 'Workspace'
  const [name, setName] = useState('')
  const [domain, setDomain] = useState('')
  const [error, setError] = useState('')
  const [message, setMessage] = useState('')
  const query = useQuery({ queryKey: ['settings'], queryFn: () => settingsView(credentials) })
  const orgs = query.data?.orgs || []
  const requestedOrg = Number(params.get('org'))
  const activeOrg = orgs.find(org => org.id === requestedOrg) || orgs.find(org => org.id === query.data?.active_org_id) || orgs[0]
  async function refresh() { await queryClient.invalidateQueries({ queryKey: ['settings'] }) }
  const create = useMutation({ mutationFn: () => createOrganization(credentials, { name: name.trim(), domain: domain.trim() }), onSuccess: async result => { await refresh(); setName(''); setDomain(''); setMessage(`Organization ${result.org.name} created. Select it to make it active.`); setError('') } })
  const activate = useMutation({ mutationFn: (id: number) => selectOrganization(credentials, id), onSuccess: async () => { await refresh(); setMessage('Active organization updated and confirmed by the backend.'); setError('') } })
  async function submitCreate(event: FormEvent<HTMLFormElement>) { event.preventDefault(); setError(''); setMessage(''); try { await create.mutateAsync() } catch (reason) { setError(reason instanceof Error ? reason.message : 'Could not create organization.') } }
  function chooseSection(next: Section) { const values = new URLSearchParams(params); if (next === 'Workspace') values.delete('section'); else values.set('section', 'links'); setParams(values) }
  function chooseOrg(id: number) { const values = new URLSearchParams(params); values.set('org', String(id)); setParams(values) }
  return <AppShell active="Settings" query="" onQueryChange={() => {}}><div className="page-layout"><main className="page-main"><div className="page-content settings-page">
    <div className="page-heading"><div><h1>Settings</h1><p>Manage organizations, capabilities, and public-link configuration.</p></div></div>
    {query.isError && query.data && <div className="operational-error" role="alert">Refresh failed: {query.error.message} <button onClick={() => query.refetch()}>Retry</button></div>}
    {message && <div className="company-page-notice" role="status">{message}<button onClick={() => setMessage('')} aria-label="Dismiss message">×</button></div>}
    {error && <div className="operational-error" role="alert">{error}</div>}
    {query.isPending ? <DataState title="Loading settings" detail="Reading workspace configuration." /> : query.isError && !query.data ? <DataState title="Settings could not be loaded" detail={query.error.message} retry={() => query.refetch()} /> : <div className="settings-layout">
      <nav className="settings-side-nav" aria-label="Settings sections">{sections.map(item => <button key={item} className={section === item ? 'active' : ''} onClick={() => chooseSection(item)}>{item === 'Workspace' ? <Building2 size={17} /> : <Globe2 size={17} />}{item}</button>)}</nav>
      <div className="settings-content">{section === 'Workspace' ? <>
        <section className="settings-card"><div className="settings-card-heading"><div><h2>Workspace</h2><p>Choose the organization used by marketing workflows.</p></div></div>
          {orgs.length ? <div className="org-selector"><label>Organization<select aria-label="Organization" value={activeOrg?.id || ''} onChange={event => chooseOrg(Number(event.target.value))}>{orgs.map(org => <option key={org.id} value={org.id}>{org.name}</option>)}</select></label><div><StateBadge tone={activeOrg?.id === query.data?.active_org_id ? 'green' : 'neutral'}>{activeOrg?.id === query.data?.active_org_id ? 'Active' : 'Not active'}</StateBadge>{activeOrg && activeOrg.id !== query.data?.active_org_id && <button className="button secondary" disabled={activate.isPending} onClick={async () => { setError(''); try { await activate.mutateAsync(activeOrg.id) } catch (reason) { setError(reason instanceof Error ? reason.message : 'Could not activate organization.') } }}>Make active</button>}</div></div> : <p className="muted-copy">No organizations exist. Create one below to configure capabilities.</p>}
        </section>
        {activeOrg && <OrganizationEditor key={activeOrg.id} org={activeOrg} capabilities={query.data?.available_capabilities || []} onSaved={refresh} />}
        <section className="settings-card"><div className="settings-card-heading"><div><h2>Create organization</h2><p>Creates a marketing organization. A company candidate or prospect is a separate record.</p></div><Plus size={18} /></div><form className="org-create-form" onSubmit={submitCreate}><label>Name<input required minLength={1} maxLength={120} value={name} onChange={event => setName(event.target.value)} placeholder="Organization name" /></label><label>Domain (optional)<input maxLength={253} value={domain} onChange={event => setDomain(event.target.value)} placeholder="example.org" /></label><button className="button primary" disabled={create.isPending}>Create organization</button></form></section>
      </> : <section className="settings-card"><div className="settings-card-heading"><div><h2>Public links</h2><p>Configured destinations only. Reachability is not verified here.</p></div><Globe2 size={19} /></div><div className="public-link-list">{query.data?.public_links.map(link => <div key={link.id}><div><strong>{link.label}</strong><small>{link.url || 'No valid URL configured'}</small></div><StateBadge tone={link.state === 'configured' ? 'green' : link.state === 'local' ? 'blue' : 'yellow'}>{link.state === 'configured' ? 'Configured, unverified' : link.state === 'local' ? 'Local only' : link.state === 'placeholder' ? 'Placeholder' : 'Invalid URL'}</StateBadge>{link.url && link.state === 'configured' && <a href={link.url} target="_blank" rel="noreferrer" aria-label={`Open ${link.label}`}><ExternalLink size={16} /></a>}</div>)}</div><p className="operational-note">These URLs are read from backend configuration. Local and placeholder links cannot provide a public deployment.</p></section>}</div>
      <aside className="settings-info"><section className="settings-info-card"><h3><LockKeyhole size={17} />Backend access</h3><p>Dashboard Basic authentication is required. Provider key changes also require the founder action token.</p><StateBadge tone="green">Authenticated session</StateBadge></section><section className="settings-info-card"><h3><Globe2 size={17} />Public-link status</h3>{query.data?.public_links.map(link => <div className="side-fact" key={link.id}><span>{link.label}</span><strong>{link.state}</strong></div>)}</section><section className="settings-info-card"><h3><Settings2 size={17} />Quick links</h3><Link to="/integrations">Manage integrations <ExternalLink size={13} /></Link><a href="/docs" target="_blank" rel="noreferrer">View API docs <ExternalLink size={13} /></a></section><section className="settings-info-card"><h3><Check size={17} />Source of truth</h3><p>Organization identity and capabilities come from the backend store. Environment health and backups are not available through this contract.</p></section></aside>
    </div>}
  </div></main></div></AppShell>
}
