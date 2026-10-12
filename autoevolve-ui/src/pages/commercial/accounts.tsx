/** Accounts as a working table: search, filter, paginate, open, add, import. */
import { useEffect, useState } from 'react'
import { useQuery, useQueryClient } from '@tanstack/react-query'
import type { Credentials } from '../../api/client'
import { commercialApi, commercialWrite, type CAccount } from '../../api/commercial'
import { RightDrawer, StateBadge } from '../../components/Primitives'
import { Dialog, Empty, Field, Section } from './shared'
import { CsvWizard } from './csvWizard'

export type AccountDetail = CAccount & {
  industry?: string; region?: string; source?: string; next_action?: string
  verification_status?: string; owner?: string
  intent?: { score: number; level: string; note: string }
  activities?: Array<{ id: string; type: string; timestamp: string; outcome: string }>
  linked_leads?: Array<{ id: string; email: string; full_name: string; stage: string; source: string }>
}

export function AccountsSection({ credentials, token, onQualify }: {
  credentials: Credentials; token: string
  onQualify: (account: CAccount) => void
}) {
  const queryClient = useQueryClient()
  const api = commercialApi(credentials)
  const [q, setQ] = useState('')
  const [lifecycle, setLifecycle] = useState('')
  const [page, setPage] = useState(1)
  const [openId, setOpenId] = useState<string | null>(null)
  const [showAdd, setShowAdd] = useState(false)
  const [showCsv, setShowCsv] = useState(false)
  const [showSuggest, setShowSuggest] = useState(false)

  const list = useQuery({ queryKey: ['c-accounts', q, lifecycle, page], queryFn: () => api.accounts({ q, lifecycle_status: lifecycle, page, page_size: 15 }) })
  const detail = useQuery({
    queryKey: ['c-account', openId], queryFn: () => api.account(openId || ''),
    enabled: openId !== null,
  })

  const items = list.data?.items || []
  const total = list.data?.total || 0

  return <Section title="Accounts" intro={`${total} account${total === 1 ? '' : 's'} on record. Sources are preserved; fit shows only when an ICP has scored the account.`}
    action={<><button className="button secondary" onClick={() => setShowCsv(true)}>Import CSV</button>
      <button className="button secondary" onClick={() => setShowSuggest(true)}>Suggest accounts</button>
      <button className="button primary" onClick={() => setShowAdd(true)}>Add account</button></>}>
    <div className="cx-toolbar">
      <input aria-label="Search accounts" value={q} onChange={e => { setQ(e.target.value); setPage(1) }} placeholder="Search name, domain, industry…" />
      <select aria-label="Lifecycle filter" value={lifecycle} onChange={e => { setLifecycle(e.target.value); setPage(1) }}>
        <option value="">All lifecycles</option>
        {['target', 'engaged', 'customer', 'former'].map(s => <option key={s} value={s}>{s}</option>)}
      </select>
    </div>
    {list.isError && <p className="form-error" role="alert">Accounts could not be loaded.</p>}
    {list.isPending ? <p className="cx-note">Loading accounts…</p> : items.length === 0
      ? <Empty title={q || lifecycle ? 'No accounts match' : 'No accounts yet'}
        detail={q || lifecycle ? 'Try a different search or clear the filter.' : 'Add your first account or import a list to get started.'}
        action={!q && !lifecycle ? <><button className="button primary" onClick={() => setShowAdd(true)}>Add account</button>
          <button className="button secondary" onClick={() => setShowCsv(true)}>Import CSV</button></> : undefined} />
      : <>
        <table className="cx-table"><thead><tr><th>Account</th><th>Industry</th><th>Lifecycle</th><th>Fit</th><th>Next action</th></tr></thead>
          <tbody>{items.map(a => <tr key={a.id} className="cx-rowlink" onClick={() => setOpenId(a.id)}>
            <td><strong>{a.company_name}</strong><small>{a.domain || 'no domain'}</small></td>
            <td>{(a as AccountDetail).industry || '—'}</td>
            <td><StateBadge tone={a.lifecycle_status === 'customer' ? 'green' : 'neutral'}>{a.lifecycle_status || 'target'}</StateBadge></td>
            <td>{typeof a.fit_score === 'number' ? `${a.fit_grade} (${a.fit_score})` : a.fit_grade === 'unknown' ? 'Not scored' : a.fit_grade}</td>
            <td>{(a as AccountDetail).next_action || '—'}</td>
          </tr>)}</tbody></table>
        <div className="cx-pager">
          <button className="button secondary" disabled={page <= 1} onClick={() => setPage(p => p - 1)}>Previous</button>
          <span className="cx-note">Page {page} · {total} total</span>
          <button className="button secondary" disabled={page * 15 >= total} onClick={() => setPage(p => p + 1)}>Next</button>
        </div>
      </>}
    {openId && <RightDrawer title="Account" onClose={() => setOpenId(null)}>
      {detail.isPending ? <p className="cx-note">Loading…</p> : detail.data ? <AccountDetailView
        account={detail.data as AccountDetail}
        onQualify={() => { const a = detail.data as CAccount; setOpenId(null); onQualify(a) }} /> : <p className="cx-note">Not found.</p>}
    </RightDrawer>}
    {showAdd && <AddAccountDialog credentials={credentials} token={token} onClose={() => setShowAdd(false)}
      onSaved={() => { setShowAdd(false); void queryClient.invalidateQueries({ queryKey: ['c-accounts'] }) }} />}
    {showCsv && <CsvWizard credentials={credentials} token={token} onClose={() => setShowCsv(false)} />}
    {showSuggest && <SuggestDialog credentials={credentials} token={token} onClose={() => setShowSuggest(false)}
      onCreated={() => void queryClient.invalidateQueries({ queryKey: ['c-accounts'] })} />}
  </Section>
}

function AccountDetailView({ account, onQualify }: { account: AccountDetail; onQualify: () => void }) {
  return <div>
    <div className="drawer-identity"><div className="drawer-name">
      <h2>{account.company_name}</h2>
      <p>{account.domain || 'No domain recorded'}</p></div></div>
    <dl className="detail-grid">
      <div><dt>Lifecycle</dt><dd>{account.lifecycle_status || 'target'}</dd></div>
      <div><dt>Fit</dt><dd>{typeof account.fit_score === 'number' ? `${account.fit_grade} (${account.fit_score})` : 'Not scored yet'}</dd></div>
      <div><dt>Industry</dt><dd>{account.industry || 'Unknown'}</dd></div>
      <div><dt>Region</dt><dd>{account.region || 'Unknown'}</dd></div>
      <div><dt>Source</dt><dd>{account.source || 'manual'}</dd></div>
      <div><dt>Verification</dt><dd>{account.verification_status || 'unverified'}</dd></div>
    </dl>
    {account.next_action && <p className="cx-note">Next: {account.next_action}</p>}
    <div className="validation-actions"><button className="button primary" onClick={onQualify}>Qualify this account</button></div>
    <h3>Activity</h3>
    {(account.linked_leads || []).length > 0 && <><h3>Linked outreach ({account.linked_leads!.length})</h3>
      <ul className="activity-list">{account.linked_leads!.map(l =>
        <li key={l.id}><strong>{l.full_name || l.email}</strong><span>{l.email} · {l.stage}</span></li>)}</ul></>}
    {(account.activities || []).length === 0
      ? <p className="cx-note">No recorded activity yet.</p>
      : <ul className="activity-list">{account.activities!.map(a =>
        <li key={a.id}><strong>{a.type}</strong><span>{a.outcome || '—'}</span><small>{a.timestamp}</small></li>)}</ul>}
    {account.intent && <p className="cx-note">Buying intent: {account.intent.level} ({account.intent.score}) — {account.intent.note}</p>}
  </div>
}

function AddAccountDialog({ credentials, token, onClose, onSaved }: {
  credentials: Credentials; token: string; onClose: () => void; onSaved: () => void
}) {
  const [name, setName] = useState('')
  const [domain, setDomain] = useState('')
  const [industry, setIndustry] = useState('')
  const [error, setError] = useState('')
  const [busy, setBusy] = useState(false)
  async function save() {
    if (!name.trim()) { setError('Company name is required.'); return }
    if (!token.trim()) { setError('Enter the founder action token at the top of the page first.'); return }
    setError(''); setBusy(true)
    try {
      await commercialWrite(credentials, token).createAccount({
        company_name: name.trim(), domain: domain.trim(), industry: industry.trim(),
      })
      onSaved()
    } catch (e) { setError(e instanceof Error ? e.message : 'Account could not be saved.') }
    finally { setBusy(false) }
  }
  return <Dialog title="Add account" intro="Company name is the only required field." onClose={onClose}>
    <div className="cx-form">
      <Field label="Company name"><input value={name} onChange={e => setName(e.target.value)} placeholder="e.g. Northwind Logistics" /></Field>
      <div className="cx-grid">
        <Field label="Domain" hint="Used to detect duplicates."><input value={domain} onChange={e => setDomain(e.target.value)} placeholder="northwind.example" /></Field>
        <Field label="Industry"><input value={industry} onChange={e => setIndustry(e.target.value)} placeholder="Logistics" /></Field>
      </div>
      {error && <p className="form-error" role="alert">{error}</p>}
      <div className="modal-actions"><button className="button secondary" onClick={onClose}>Cancel</button>
        <button className="button primary" disabled={busy} onClick={() => void save()}>{busy ? 'Saving…' : 'Save account'}</button></div>
    </div>
  </Dialog>
}

type Suggestion = {
  company_name: string; domain: string
  evidence: { lead_count: number; stages: string[]; sources: string[]; research_candidate: boolean }
  reason: string
}

function SuggestDialog({ credentials, token, onClose, onCreated }: {
  credentials: Credentials; token: string
  onClose: () => void; onCreated: () => void
}) {
  const api = commercialApi(credentials)
  const [suggestions, setSuggestions] = useState<Suggestion[] | null>(null)
  const [from, setFrom] = useState<Record<string, number>>({})
  const [error, setError] = useState('')
  const [busy, setBusy] = useState<string | null>(null)
  const [created, setCreated] = useState<string[]>([])
  // eslint-disable-next-line react-hooks/exhaustive-deps
  useEffect(() => { void load() }, [])
  async function load() {
    setError(''); setBusy('loading')
    try {
      const out = await api.suggestAccounts()
      setSuggestions(out.suggestions)
      setFrom(out.generated_from)
    } catch (e) { setError(e instanceof Error ? e.message : 'Suggestions could not be loaded.') }
    finally { setBusy(null) }
  }
  async function create(s: Suggestion) {
    if (!token.trim()) { setError('Enter the founder action token at the top of the page first.'); return }
    setError(''); setBusy(s.domain)
    try {
      await commercialWrite(credentials, token).createAccount({
        company_name: s.company_name, domain: s.domain,
        source: `suggested:${s.evidence.sources.join(',')}`,
      })
      setCreated(c => [...c, s.domain])
      setSuggestions(list => (list || []).filter(x => x.domain !== s.domain))
      onCreated()
    } catch (e) { setError(e instanceof Error ? e.message : `“${s.company_name}” could not be created.`) }
    finally { setBusy(null) }
  }
  return <Dialog wide title="Suggested accounts" intro="Unclaimed lead domains and research candidates, each with its reasons. Creating one runs the same validation as manual entry." onClose={onClose}>
    {error && <p className="form-error" role="alert">{error}</p>}
    {busy === 'loading' || suggestions === null ? <p className="cx-note">Reading leads, imports, and research…</p>
      : suggestions.length === 0 ? <Empty title={created.length ? 'All caught up' : 'Nothing to suggest'}
        detail={created.length ? `${created.length} account(s) created from suggestions.` : 'Every lead domain already has an account, or there are no leads yet.'} />
      : <>
        <p className="cx-note">Based on {from.unclaimed_lead_domains ?? 0} unclaimed domain(s){from.research_candidates ? `, including ${from.research_candidates} research candidate(s)` : ''}.</p>
        <ul className="cx-cards">{suggestions.map(s => <li key={s.domain} className="cx-card">
          <div><strong>{s.company_name}</strong> <small>{s.domain} · {s.evidence.lead_count} lead(s) · {s.evidence.stages.join(', ') || 'new'}</small></div>
          <p>{s.reason}</p>
          <div className="cx-card-actions">
            <button className="button primary" disabled={busy !== null} onClick={() => void create(s)}>
              {busy === s.domain ? 'Creating…' : 'Create account'}</button>
          </div>
        </li>)}</ul>
      </>}
    <div className="modal-actions"><button className="button secondary" onClick={onClose}>Close</button></div>
  </Dialog>
}
