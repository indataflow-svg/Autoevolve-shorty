import { useEffect, useRef, useState } from 'react'
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'
import { useSearchParams } from 'react-router-dom'
import { BookOpen, Check, ChevronDown, KeyRound, PlugZap, Search, ShieldAlert } from 'lucide-react'
import { useCredentials } from '../app/Auth'
import {
  bufferSetupAccounts,
  connectBuffer,
  discoverBuffer,
  incidentsView,
  integrationsView,
  saveProviderKeys,
  testProviderKeys,
  type BufferDiscovery,
  type BufferSetupAccount,
  type ProviderGroup,
} from '../api/operational'
import { AppShell } from '../components/Shell'
import { DataState, RightDrawer, StateBadge } from '../components/Primitives'

function status(group: ProviderGroup) {
  const connections = group.connections || []
  if (connections.some(connection => connection.status === 'healthy' || connection.status === 'connected')) return { label: 'Connected', tone: 'green' as const }
  if (connections.length) return { label: 'Needs attention', tone: 'yellow' as const }
  if (group.accounts?.length) {
    const ready = group.accounts.filter(account => account.channels.length)
    return ready.length === group.accounts.length
      ? { label: `${ready.length} Buffer account${ready.length === 1 ? '' : 's'} ready`, tone: 'green' as const }
      : { label: 'Buffer accounts need channels', tone: 'yellow' as const }
  }
  if (group.configured_count === 0) return { label: 'Not configured', tone: 'neutral' as const }
  if (group.missing_keys.length) return { label: 'Partially configured', tone: 'yellow' as const }
  return { label: 'Keys configured', tone: 'green' as const }
}

function isSecretKey(name: string) {
  return /(KEY|TOKEN|SECRET|PASSWORD)/.test(name)
}

function accountLabel(account: BufferSetupAccount) {
  const channels = [
    account.instagram_channel_id && 'Instagram',
    account.x_channel_id && 'X',
    account.linkedin_channel_id && 'LinkedIn',
  ].filter(Boolean)
  return `${account.name} · ${channels.length ? channels.join(' + ') : 'no channels bound'}`
}

function ProviderOverviewDrawer({ group, close, configure }: { group: ProviderGroup; close: () => void; configure: () => void }) {
  const keyNames = [...group.configured_keys, ...group.missing_keys]
  const current = status(group)
  const connections = group.connections || []
  return <RightDrawer title="Integration details" onClose={close} className="integration-drawer">
    <div className="drawer-identity"><span className="provider-icon"><PlugZap size={24} /></span><div className="drawer-name"><h2>{group.label}</h2><p>{group.category}</p></div></div>
    <div className="drawer-status"><StateBadge tone={current.tone}>{current.label}</StateBadge><span className="muted-copy">{group.accounts?.length ? `${group.accounts.length} Buffer account${group.accounts.length === 1 ? '' : 's'} configured` : `${group.configured_count} of ${group.total_keys} keys present`}</span></div>
    <div className="drawer-tabs"><button aria-selected="true">Overview</button></div>
    <div className="drawer-body">
      <section className="detail-card"><h3>Capabilities</h3><div className="tag-list">{group.capabilities.map(capability => <span key={capability}>{capability}</span>)}</div><p className="operational-note">Capabilities describe this integration; they are not health checks.</p></section>
      <section className="detail-card"><h3>Configuration</h3>{group.accounts?.length ? <><div className="key-list">{group.accounts.map(account => <div key={account.name}><code>{account.name}</code><StateBadge tone={account.channels.length ? 'green' : 'yellow'}>{account.channels.length ? account.channels.join(' + ') : 'no channels'}</StateBadge></div>)}</div><p className="operational-note">Named Buffer accounts are listed first. The keys below belong to the default account.</p></> : null}<div className="key-list">{keyNames.map(key => <div key={key}><code>{key}</code><StateBadge tone={group.configured_keys.includes(key) ? 'green' : 'neutral'}>{group.configured_keys.includes(key) ? 'Present' : 'Missing'}</StateBadge></div>)}</div><p className="operational-note">Saved values are never returned by the API. Setup lives on its own tab.</p></section>
      {connections.length > 0 && <section className="detail-card"><h3>Organization connections</h3><div className="key-list">{connections.map(connection => <div key={connection.provider}><code>{connection.provider}</code><StateBadge tone={connection.status === 'healthy' || connection.status === 'connected' ? 'green' : 'yellow'}>{connection.status.replaceAll('_', ' ')} · sync {connection.sync_status.replaceAll('_', ' ')}</StateBadge></div>)}</div><p className="operational-note">Keys say what is configured; only these rows say what is connected.</p></section>}
    </div>
    <div className="drawer-footer">{keyNames.length === 0
      ? <p className="muted-copy">This row lists organization connections only; there are no keys to configure here. Manage connections from the Commercial workspace.</p>
      : <button className="button primary" onClick={configure}>Configure keys</button>}</div>
  </RightDrawer>
}

function BufferSetup({ onSaved }: { onSaved: () => Promise<void> }) {
  const credentials = useCredentials()
  const queryClient = useQueryClient()
  const accounts = useQuery({ queryKey: ['buffer-setup-accounts'], queryFn: () => bufferSetupAccounts(credentials) })
  const [account, setAccount] = useState('default')
  const [newAccount, setNewAccount] = useState('')
  const [apiKey, setApiKey] = useState('')
  const [token, setToken] = useState('')
  const [discovery, setDiscovery] = useState<BufferDiscovery | null>(null)
  const [organizationId, setOrganizationId] = useState('')
  const [channels, setChannels] = useState({ instagram: '', x: '', linkedin: '' })
  const [warnings, setWarnings] = useState<string[]>([])
  const [error, setError] = useState('')
  const [feedback, setFeedback] = useState('')

  const existing = accounts.data?.accounts
  const creating = account === '__new__'
  const effectiveAccount = creating ? newAccount.trim().toLowerCase() : account
  const selected = existing?.find(item => item.name === account)
  const initialized = useRef(false)

  useEffect(() => {
    // Pick the first configured account once, then respect the operator's choice.
    if (initialized.current || !existing?.length) return
    initialized.current = true
    if (!existing.some(item => item.name === account)) setAccount(existing[0].name)
  }, [existing, account])

  function resetDiscovery() {
    setDiscovery(null)
    setOrganizationId('')
    setChannels({ instagram: '', x: '', linkedin: '' })
    setWarnings([])
  }

  function chooseOrganization(found: BufferDiscovery, orgId: string) {
    setOrganizationId(orgId)
    const organization = found.organizations.find(item => item.id === orgId)
    const pick = (platform: 'instagram' | 'x' | 'linkedin') => organization?.channels.find(channel => channel.platform === platform && channel.usable)?.id || ''
    setChannels({ instagram: pick('instagram'), x: pick('x'), linkedin: pick('linkedin') })
  }

  const discover = useMutation({
    mutationFn: () => discoverBuffer(credentials, { account: effectiveAccount, api_key: apiKey.trim() || null }, token.trim()),
  })
  const connect = useMutation({
    mutationFn: () => connectBuffer(credentials, {
      account: effectiveAccount,
      api_key: apiKey.trim() || null,
      organization_id: organizationId,
      instagram_channel_id: channels.instagram || null,
      x_channel_id: channels.x || null,
      linkedin_channel_id: channels.linkedin || null,
    }, token.trim()),
  })

  async function runDiscover() {
    setError(''); setFeedback(''); setWarnings([])
    if (!effectiveAccount) { setError('Name the new Buffer account first.'); return }
    if (!token.trim()) { setError('Enter the founder action token.'); return }
    if (!selected?.api_key_present && !apiKey.trim()) { setError('Enter the Buffer API key for this account.'); return }
    try {
      const found = await discover.mutateAsync()
      setDiscovery(found)
      const first = found.organizations[0]
      if (first) chooseOrganization(found, first.id)
      setFeedback(`Found ${found.organizations.length} organization${found.organizations.length === 1 ? '' : 's'}. Choose the channels to bind.`)
    } catch (reason) { setError(reason instanceof Error ? reason.message : 'Buffer discovery failed.') }
  }

  async function runConnect() {
    setError(''); setFeedback(''); setWarnings([])
    if (!discovery) { setError('Discover the channels before saving.'); return }
    if (!organizationId) { setError('Choose an organization.'); return }
    if (!token.trim()) { setError('Enter the founder action token.'); return }
    try {
      const saved = await connect.mutateAsync()
      setWarnings(saved.warnings)
      setApiKey('')
      await queryClient.invalidateQueries({ queryKey: ['buffer-setup-accounts'] })
      await queryClient.invalidateQueries({ queryKey: ['integrations'] })
      await queryClient.invalidateQueries({ queryKey: ['buffer-accounts'] })
      if (creating) { setAccount(saved.account); setNewAccount('') }
      setFeedback(saved.restart_required ? 'Buffer account saved. Restart the backend before scheduling.' : 'Buffer account saved. The channels are available now.')
      await onSaved()
    } catch (reason) { setError(reason instanceof Error ? reason.message : 'The Buffer account could not be saved.') }
  }

  const organization = discovery?.organizations.find(item => item.id === organizationId)
  const usable = (platform: 'instagram' | 'x' | 'linkedin') => organization?.channels.filter(channel => channel.platform === platform && channel.usable) || []
  const unsupported = organization?.channels.filter(channel => !channel.supported) || []
  const unavailable = organization?.channels.filter(channel => channel.supported && !channel.usable) || []

  return <>
    <section className="home-panel">
      <div className="home-panel-heading"><h2>1 · Buffer account</h2><span className="muted-copy">One token per account</span></div>
      <div className="setup-stack">
        <label className="operational-label">Account<select value={account} onChange={event => { setAccount(event.target.value); setApiKey(''); resetDiscovery(); setFeedback(''); setError('') }}>
          {(existing || []).map(item => <option key={item.name} value={item.name}>{accountLabel(item)}</option>)}
          {!existing?.some(item => item.name === 'default') && <option value="default">default · not configured</option>}
          <option value="__new__">New named account…</option>
        </select></label>
        {accounts.isPending && <p className="field-note">Reading saved Buffer accounts…</p>}
        {accounts.isError && <p className="field-note">Saved account state could not be read: {accounts.error.message}. You can still enter a key below.</p>}
        {creating && <><label className="operational-label">Account name<input value={newAccount} onChange={event => { setNewAccount(event.target.value); resetDiscovery() }} placeholder="acme" maxLength={31} autoComplete="off" /></label><p className="field-note">Lowercase letters, digits, - or _ (max 31 characters).</p></>}
        {selected && <div className="key-list">
          <div><code>API key</code><StateBadge tone={selected.api_key_present ? 'green' : 'neutral'}>{selected.api_key_present ? 'Saved' : 'Missing'}</StateBadge></div>
          <div><code>Organization</code><span className="muted-copy break-value">{selected.organization_id || 'not bound'}</span></div>
          <div><code>Instagram channel</code><span className="muted-copy break-value">{selected.instagram_channel_id || 'not bound'}</span></div>
          <div><code>X channel</code><span className="muted-copy break-value">{selected.x_channel_id || 'not bound'}</span></div>
          <div><code>LinkedIn channel</code><span className="muted-copy break-value">{selected.linkedin_channel_id || 'not bound'}</span></div>
        </div>}
        <label className="operational-label">Buffer API key<input type="password" autoComplete="off" value={apiKey} onChange={event => setApiKey(event.target.value)} placeholder={selected?.api_key_present ? 'Saved — leave blank to reuse' : 'Paste the Buffer access token'} /></label>
        <p className="field-note">The token is used once to read the organizations and channels this account can reach. It is never returned. One token authorizes every channel in the account.</p>
        <label className="operational-label">Founder action token<input type="password" autoComplete="off" value={token} onChange={event => setToken(event.target.value)} /></label>
        <p className="field-note">This is the dashboard's founder action token, not the Buffer key.</p>
        {error && <p className="form-error" role="alert">{error}</p>}
        {feedback && <p className="success-message" role="status">{feedback}</p>}
        <div className="operational-actions"><button className="button secondary" type="button" onClick={() => void runDiscover()} disabled={discover.isPending || connect.isPending}>{discover.isPending ? 'Reading Buffer…' : discovery ? 'Rediscover channels' : 'Discover channels'}</button></div>
      </div>
    </section>

    {discovery && <section className="home-panel">
      <div className="home-panel-heading"><h2>2 · Channels</h2><span className="muted-copy">{discovery.account_id || discovery.account}</span></div>
      <div className="setup-stack">
        {discovery.organizations.length > 1
          ? <label className="operational-label">Organization<select value={organizationId} onChange={event => chooseOrganization(discovery, event.target.value)}>{discovery.organizations.map(item => <option key={item.id} value={item.id}>{item.name}</option>)}</select></label>
          : <p className="operational-note">Organization: <strong>{organization?.name}</strong> <code>{organization?.id}</code></p>}
        {(['instagram', 'x', 'linkedin'] as const).map(platform => {
          const choices = usable(platform)
          const label = platform === 'instagram' ? 'Instagram' : platform === 'x' ? 'X' : 'LinkedIn'
          return <div className="channel-row" key={platform}>
            <strong>{label}</strong>
            {choices.length
              ? <div className="channel-choice">
                <select aria-label={`${label} channel`} value={channels[platform]} onChange={event => setChannels(current => ({ ...current, [platform]: event.target.value }))}>
                  <option value="">Do not bind</option>
                  {choices.map(channel => <option key={channel.id} value={channel.id}>{channel.display_name || channel.name} · {channel.descriptor || channel.service}</option>)}
                </select>
                {channels[platform] && <small className="muted-copy break-value">Channel ID: {channels[platform]}</small>}
              </div>
              : <span className="muted-copy">No usable {label} channel in this organization.</span>}
          </div>
        })}
        {unsupported.length > 0 && <p className="field-note">Not supported by the G3 handoff, so left unbound: {unsupported.map(channel => `${channel.service} (${channel.display_name || channel.name})`).join(', ')}.</p>}
        {unavailable.length > 0 && <p className="field-note">Disconnected or locked, so not selectable: {unavailable.map(channel => `${channel.display_name || channel.name} (${channel.service})`).join(', ')}.</p>}
        <p className="field-note">These are channel IDs, not extra secrets. The single token above authorizes all of them.</p>
        {warnings.length > 0 && <div className="setup-warning" role="status">{warnings.join(' ')}</div>}
        <div className="operational-actions"><button className="button primary" type="button" onClick={() => void runConnect()} disabled={connect.isPending || !organizationId}>{connect.isPending ? 'Saving…' : 'Save account'}</button></div>
      </div>
    </section>}
  </>
}

function ProviderKeyForm({ group, onSaved }: { group: ProviderGroup; onSaved: () => Promise<void> }) {
  const credentials = useCredentials()
  const queryClient = useQueryClient()
  const [values, setValues] = useState<Record<string, string>>({})
  const [token, setToken] = useState('')
  const [tested, setTested] = useState('')
  const [error, setError] = useState('')
  const [feedback, setFeedback] = useState('')

  const filled = Object.fromEntries(Object.entries(values).filter(([, value]) => value.trim()))
  const signature = JSON.stringify(filled)
  const test = useMutation({ mutationFn: () => testProviderKeys(credentials, { group: group.id, values: filled }, token.trim()) })
  const save = useMutation({
    mutationFn: () => saveProviderKeys(credentials, { group: group.id, values: filled }, token.trim()),
    onSuccess: async () => {
      setValues({}); setTested(''); setFeedback('Values saved. Restart may be required before the provider uses them; health is not verified.')
      await queryClient.invalidateQueries({ queryKey: ['integrations'] })
      await onSaved()
    },
  })

  async function run(action: 'test' | 'save') {
    setError(''); setFeedback('')
    if (!Object.keys(filled).length) { setError('Enter at least one value.'); return }
    if (!token.trim()) { setError('Enter the founder action token.'); return }
    try {
      if (action === 'test') {
        await test.mutateAsync()
        setTested(signature)
        setFeedback('Backend validation passed. This does not prove provider health or save the values.')
      } else {
        if (tested !== signature) { setError('Test these exact values before saving.'); return }
        await save.mutateAsync()
      }
    } catch (reason) { setError(reason instanceof Error ? reason.message : 'The action failed.') }
  }

  function setValue(key: string, value: string) {
    setValues(current => ({ ...current, [key]: value }))
    setTested('')
  }

  return <section className="home-panel">
    <div className="home-panel-heading"><h2>{group.label}</h2><StateBadge tone={status(group).tone}>{status(group).label}</StateBadge></div>
    <div className="setup-stack">
      {group.missing_keys.length
        ? group.missing_keys.map(key => <label className="operational-label" key={key}>{key}<input type={isSecretKey(key) ? 'password' : 'text'} autoComplete="off" value={values[key] || ''} onChange={event => setValue(key, event.target.value)} /></label>)
        : <p className="operational-note">Every key in this group is present. Rotate a value below if needed.</p>}
      {group.configured_keys.length > 0 && <details className="key-replace"><summary>Replace a saved value</summary><div className="setup-stack">{group.configured_keys.map(key => <label className="operational-label" key={key}>{key}<input type={isSecretKey(key) ? 'password' : 'text'} autoComplete="off" value={values[key] || ''} onChange={event => setValue(key, event.target.value)} placeholder="Leave blank to keep the saved value" /></label>)}</div></details>}
      <label className="operational-label">Founder action token<input type="password" autoComplete="off" value={token} onChange={event => setToken(event.target.value)} /></label>
      <p className="field-note">This authorizes the change; it is not the provider key.</p>
      {group.id === 'ai_gateway' && <p className="field-note">Testing an AI gateway URL calls its /models endpoint.</p>}
      {error && <p className="form-error" role="alert">{error}</p>}
      {feedback && <p className="success-message" role="status">{feedback}</p>}
      <div className="operational-actions">
        <button className="button secondary" type="button" onClick={() => void run('test')} disabled={test.isPending || save.isPending || !Object.keys(filled).length}>{test.isPending ? 'Testing…' : 'Test values'}</button>
        <button className="button primary" type="button" onClick={() => void run('save')} disabled={save.isPending || !Object.keys(filled).length || tested !== signature}>{save.isPending ? 'Saving…' : 'Save values'}</button>
      </div>
    </div>
  </section>
}

export function IntegrationsPage() {
  const credentials = useCredentials()
  const [params, setParams] = useSearchParams()
  const category = params.get('category') || 'All'
  const search = params.get('q') || ''
  const sort = params.get('sort') === 'configured' ? 'configured' : 'name'
  const selected = params.get('integration')
  const showIncidents = params.get('view') === 'incidents'
  const tab = params.get('tab') === 'setup' ? 'setup' : 'overview'
  const query = useQuery({ queryKey: ['integrations'], queryFn: () => integrationsView(credentials) })
  const incidents = useQuery({ queryKey: ['incidents'], queryFn: () => incidentsView(credentials), enabled: showIncidents })
  const groups = query.data?.groups || []
  const categories = ['All', ...Array.from(new Set(groups.map(group => group.category)))]
  const visible = groups.filter(group => (category === 'All' || group.category === category) && `${group.label} ${group.category} ${group.capabilities.join(' ')}`.toLowerCase().includes(search.toLowerCase())).sort((a, b) => sort === 'configured' ? b.configured_count - a.configured_count || a.label.localeCompare(b.label) : a.label.localeCompare(b.label))
  const active = groups.find(group => group.id === selected)
  const setupGroup = groups.find(group => group.id === (selected || 'social')) || groups.find(group => group.id === 'social') || groups[0]
  function update(changes: Record<string, string | null>) { const next = new URLSearchParams(params); for (const [key, value] of Object.entries(changes)) { if (value) next.set(key, value); else next.delete(key) } setParams(next) }
  async function refresh() { await query.refetch() }

  return <AppShell active="Integrations" query={search} onQueryChange={value => update({ q: value, integration: null })}>
    <div className="page-layout"><main className="page-main"><div className="page-content operational-page">
      <div className="page-heading"><div><h1>Integrations</h1><p>Overview first. Setup asks only for fields the backend can verify.</p></div><div className="heading-actions"><a className="button secondary" href="/docs" target="_blank" rel="noreferrer"><BookOpen size={16} />View API docs</a></div></div>
      <div className="view-tabs page-tabs">
        <button className={tab === 'overview' ? 'active' : ''} onClick={() => update({ tab: null, integration: null, view: null })}>Overview</button>
        <button className={tab === 'setup' ? 'active' : ''} onClick={() => update({ tab: 'setup', integration: null, view: null })}>Setup</button>
      </div>

      {tab === 'overview' && <>
        {showIncidents && <section className="home-panel" id="incidents"><div className="home-panel-heading"><h2>Service incidents</h2><button className="row-action" onClick={() => update({ view: null })}>Close</button></div>{incidents.isPending ? <p className="operational-note">Loading saved incidents…</p> : incidents.isError && !incidents.data ? <DataState title="Incidents could not be loaded" detail={incidents.error.message} retry={() => incidents.refetch()} /> : <div className="onboarding-list">{incidents.isError && <p className="operational-error" role="alert">Incident refresh failed: {incidents.error.message}</p>}{incidents.data?.incidents.filter(item => !['resolved', 'closed'].includes(item.status)).length ? incidents.data.incidents.filter(item => !['resolved', 'closed'].includes(item.status)).map(item => <div className="onboarding-candidate" key={item.id}><div><strong>{item.service} · {item.trigger}</strong><small>{item.severity} · {item.status} · {item.created_at}</small></div></div>) : <p className="operational-note">No open service incidents are recorded.</p>}</div>}</section>}
        <div className="operational-metrics"><div><PlugZap /><span>Provider groups<strong>{query.data?.total_groups ?? '—'}</strong></span></div><div><KeyRound /><span>Groups configured<strong>{query.data?.groups_with_configuration ?? '—'}</strong></span></div><div><Check /><span>Fully configured<strong>{query.data?.fully_configured_groups ?? '—'}</strong></span></div><div><ShieldAlert /><span>Configured keys<strong>{query.data?.configured_keys ?? '—'}</strong></span></div></div>
        {query.isError && query.data && <div className="operational-error" role="alert">Refresh failed: {query.error.message} <button onClick={() => query.refetch()}>Retry</button></div>}
        <div className="table-toolbar operational-toolbar"><div className="view-tabs">{categories.map(item => <button key={item} className={category === item ? 'active' : ''} onClick={() => update({ category: item === 'All' ? null : item, integration: null })}>{item} ({item === 'All' ? groups.length : groups.filter(group => group.category === item).length})</button>)}</div><label className="sort-control">Sort <select aria-label="Sort integrations" value={sort} onChange={event => update({ sort: event.target.value })}><option value="name">Name A–Z</option><option value="configured">Most keys</option></select><ChevronDown size={14} /></label></div>
        <div className="table-panel">{query.isPending ? <DataState title="Loading integrations" detail="Reading configured provider groups." /> : query.isError && !query.data ? <DataState title="Integrations could not be loaded" detail={query.error.message} retry={() => query.refetch()} /> : visible.length ? <div className="table-scroll"><table className="operational-table"><thead><tr><th>Integration</th><th>Category</th><th>Configuration</th><th>Keys / accounts</th><th>Capabilities</th><th>Actions</th></tr></thead><tbody>{visible.map(group => { const current = status(group); return <tr key={group.id} className={selected === group.id ? 'selected' : ''} onClick={() => update({ integration: group.id })}><td><span className="provider-name"><span className="provider-mini"><PlugZap size={17} /></span><strong>{group.label}</strong></span></td><td>{group.category}</td><td><StateBadge tone={current.tone}>{current.label}</StateBadge></td><td>{group.accounts?.length ? <>{group.accounts.length} account{group.accounts.length === 1 ? '' : 's'}{group.configured_count > 0 && <> · default {group.configured_count}/{group.total_keys}</>}<br /><small className="muted-copy">{group.accounts.map(account => `${account.name}: ${account.channels.join(' + ') || 'no channels'}`).join(' · ')}</small></> : <>{group.configured_count} / {group.total_keys}{group.missing_keys.length > 0 && <><br /><small className="muted-copy">Missing: {group.missing_keys.join(', ')}</small></>}</>}</td><td><div className="tag-list">{group.capabilities.map(value => <span key={value}>{value}</span>)}</div></td><td><button className="row-action" onClick={event => { event.stopPropagation(); update({ tab: 'setup', integration: group.id }) }}>Configure</button></td></tr> })}</tbody></table></div> : <DataState title="No integrations found" detail="Try another category or search." />}</div>
        <div className="operational-footnote"><Search size={16} /><span>Configuration is shown from saved keys. Organization connections come from the canonical registry; keys alone never imply a working connection.</span></div>
      </>}

      {tab === 'setup' && (query.isPending
        ? <DataState title="Loading setup" detail="Reading the provider registry." />
        : query.isError && !query.data
          ? <DataState title="Setup could not be loaded" detail={query.error.message} retry={() => query.refetch()} />
          : <div className="setup-layout">
            <section className="home-panel">
              <div className="home-panel-heading"><h2>What are you connecting?</h2><span className="muted-copy">{groups.length} provider groups</span></div>
              <div className="setup-stack">
                <label className="operational-label">Integration<select value={setupGroup?.id || ''} onChange={event => update({ integration: event.target.value })}>{groups.map(group => <option key={group.id} value={group.id}>{group.label} · {group.accounts?.length ? `${group.accounts.length} account${group.accounts.length === 1 ? '' : 's'}` : `${group.configured_count}/${group.total_keys} keys`}</option>)}</select></label>
                <p className="field-note">The fields below come from the backend provider registry. Missing keys are shown individually; nothing here is a fixed UI list.</p>
              </div>
            </section>
            {setupGroup?.id === 'social'
              ? <BufferSetup onSaved={refresh} />
              : setupGroup && setupGroup.total_keys > 0
                ? <ProviderKeyForm key={setupGroup.id} group={setupGroup} onSaved={refresh} />
                : <section className="home-panel"><div className="home-panel-heading"><h2>{setupGroup?.label || 'No setup fields'}</h2></div><div className="setup-stack"><p className="operational-note">This group has no keys to configure. Manage organization connections from the Commercial workspace.</p></div></section>}
          </div>)}
    </div></main>{tab === 'overview' && active && <ProviderOverviewDrawer group={active} close={() => update({ integration: null })} configure={() => update({ tab: 'setup', integration: active.id })} />}</div>
  </AppShell>
}
