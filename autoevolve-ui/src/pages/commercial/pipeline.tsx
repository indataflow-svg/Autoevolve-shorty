/** Pipeline as a visual sales workflow. Moves are validated server-side; rejections explain why. */
import { useState } from 'react'
import { useQuery, useQueryClient } from '@tanstack/react-query'
import type { Credentials } from '../../api/client'
import { commercialApi, commercialWrite, type CAccount, type Opportunity } from '../../api/commercial'
import { contactsPage } from '../../api/contacts'
import { RightDrawer, StateBadge } from '../../components/Primitives'
import { Dialog, Empty, Field, SearchPicker, Section } from './shared'
import { groupByStage, stageLabel } from './helpers'

type StageDef = { key: string; label?: string; allowed_next?: string[]; required_fields?: string[] }
type OppDetail = Opportunity & {
  value?: number | null; currency?: string; next_action?: string
  stage_history_json?: string; account?: { id: string; company_name: string }
  activities?: Array<{ id: string; type: string; timestamp: string; outcome: string }>
}

export function PipelineSection({ credentials, token }: { credentials: Credentials; token: string }) {
  const queryClient = useQueryClient()
  const api = commercialApi(credentials)
  const [pipeId, setPipeId] = useState('')
  const [stageFilter, setStageFilter] = useState('')
  const [search, setSearch] = useState('')
  const [openId, setOpenId] = useState<string | null>(null)
  const [showCreate, setShowCreate] = useState(false)

  const pipes = useQuery({ queryKey: ['c-pipelines'], queryFn: api.pipelines })
  const pipe = (pipes.data || []).find(p => p.id === (pipeId || p.id)) || (pipes.data || [])[0]
  const stages: StageDef[] = (() => { try { return JSON.parse(pipe?.stages_json || '[]') } catch { return [] } })()
  const opps = useQuery({ queryKey: ['c-opps-board', pipe?.id, stageFilter], queryFn: () => api.opportunities(stageFilter) })
  const accounts = useQuery({ queryKey: ['c-accounts-names'], queryFn: () => api.accounts({ page_size: 100 }) })
  const names = new Map((accounts.data?.items || []).map(a => [a.id, a.company_name]))

  const items = (opps.data?.items || []).filter(o =>
    !search.trim() || (names.get(o.account_id) || '').toLowerCase().includes(search.trim().toLowerCase()))
  const groups = groupByStage(items)

  return <Section title="Pipeline" intro="Every move is checked against the pipeline's rules. A rejected move explains what is missing — the board never shows a move the backend refused."
    action={<><select aria-label="Pipeline" value={pipe?.id || ''} onChange={e => setPipeId(e.target.value)}>
      {(pipes.data || []).map(p => <option key={p.id} value={p.id}>{p.name}</option>)}
    </select>
    <button className="button primary" onClick={() => setShowCreate(true)}>New opportunity</button></>}>
    <div className="cx-toolbar">
      <input aria-label="Search opportunities" value={search} onChange={e => setSearch(e.target.value)} placeholder="Search by company…" />
      <select aria-label="Stage filter" value={stageFilter} onChange={e => setStageFilter(e.target.value)}>
        <option value="">All stages</option>
        {stages.map(s => <option key={s.key} value={s.key}>{s.label || s.key}</option>)}
      </select>
    </div>
    {opps.isPending ? <p className="cx-note">Loading pipeline…</p> : items.length === 0
      ? <Empty title="No opportunities here" detail={stageFilter || search ? 'Nothing matches this filter.' : 'Create the first opportunity to start working this pipeline.'}
        action={!stageFilter && !search ? <button className="button primary" onClick={() => setShowCreate(true)}>New opportunity</button> : undefined} />
      : <div className="cx-board">{stages.filter(s => !stageFilter || s.key === stageFilter).map(s =>
        <div key={s.key} className="cx-col"><h3>{s.label || s.key}<span>{groups.get(s.key)?.length || 0}</span></h3>
          {(groups.get(s.key) || []).map(o => <button key={o.id} className="cx-card cx-pick" onClick={() => setOpenId(o.id)}>
            <strong>{names.get(o.account_id) || 'Account'}</strong>
            <span>{(o as OppDetail).value != null ? `${(o as OppDetail).value} ${(o as OppDetail).currency || 'USD'}` : 'No value set'}</span>
            <StateBadge tone={o.outcome === 'open' ? 'blue' : o.outcome === 'won' ? 'green' : 'neutral'}>{o.outcome}</StateBadge>
          </button>)}
        </div>)}</div>}
    {openId && <RightDrawer title="Opportunity" onClose={() => setOpenId(null)}>
      <OppDetailView credentials={credentials} token={token} id={openId} stages={stages} />
    </RightDrawer>}
    {showCreate && <CreateOppDialog credentials={credentials} token={token} pipeId={pipe?.id} onClose={() => setShowCreate(false)}
      onSaved={() => { setShowCreate(false); void queryClient.invalidateQueries({ queryKey: ['c-opps-board'] }) }} />}
  </Section>
}

function OppDetailView({ credentials, token, id, stages }: {
  credentials: Credentials; token: string; id: string; stages: StageDef[]
}) {
  const queryClient = useQueryClient()
  const api = commercialApi(credentials)
  const detail = useQuery({ queryKey: ['c-opp', id], queryFn: () => api.opportunity(id) })
  const [target, setTarget] = useState('')
  const [reason, setReason] = useState('')
  const [error, setError] = useState('')
  const [busy, setBusy] = useState(false)
  const d = detail.data as OppDetail | undefined
  const history: Array<{ stage: string; at: string; by: string }> = (() => {
    try { return JSON.parse(d?.stage_history_json || '[]') } catch { return [] }
  })()
  const current = stages.find(s => s.key === d?.stage)
  const needsReason = target && ['lost', 'deferred', 'disqualified'].includes(target)

  async function move() {
    if (!target) { setError('Choose the next stage.'); return }
    if (needsReason && !reason.trim()) { setError('This stage requires a reason.'); return }
    if (!token.trim()) { setError('Enter the founder action token at the top of the page first.'); return }
    setError(''); setBusy(true)
    try {
      await commercialWrite(credentials, token).moveOpportunity(id, { stage: target, lost_reason: reason.trim() })
      setTarget(''); setReason('')
      await queryClient.invalidateQueries({ queryKey: ['c-opp', id] })
      await queryClient.invalidateQueries({ queryKey: ['c-opps-board'] })
    } catch (e) { setError(e instanceof Error ? e.message : 'Move refused.') }
    finally { setBusy(false) }
  }

  if (detail.isPending) return <p className="cx-note">Loading…</p>
  if (!d) return <p className="cx-note">Not found.</p>
  return <div>
    <div className="drawer-identity"><div className="drawer-name">
      <h2>{d.account?.company_name || 'Opportunity'}</h2>
      <p>{stageLabel(stages, d.stage)} · {d.outcome}</p></div></div>
    <dl className="detail-grid">
      <div><dt>Value</dt><dd>{d.value != null ? `${d.value} ${d.currency || 'USD'}` : 'Not set'}</dd></div>
      <div><dt>Next action</dt><dd>{d.next_action || '—'}</dd></div>
    </dl>
    <h3>Move stage</h3>
    <p className="cx-note">Allowed from here: {(current?.allowed_next || []).map(k => stageLabel(stages, k)).join(', ') || 'none'}.</p>
    <div className="cx-form">
      <Field label="Next stage"><select aria-label="Next stage" value={target} onChange={e => setTarget(e.target.value)}>
        <option value="">Choose…</option>
        {(current?.allowed_next || []).map(k => <option key={k} value={k}>{stageLabel(stages, k)}</option>)}
      </select></Field>
      {needsReason && <Field label="Reason" hint="Required for lost, deferred, and disqualified."><input value={reason} onChange={e => setReason(e.target.value)} placeholder="e.g. Budget frozen" /></Field>}
      {error && <p className="form-error" role="alert">{error}</p>}
      <div className="modal-actions"><button className="button primary" disabled={busy || !target} onClick={() => void move()}>{busy ? 'Moving…' : 'Move stage'}</button></div>
    </div>
    <h3>History</h3>
    {history.length === 0 ? <p className="cx-note">No moves recorded.</p>
      : <ul className="activity-list">{history.map((h, i) =>
        <li key={i}><strong>{stageLabel(stages, h.stage)}</strong><small>{h.at} · {h.by}</small></li>)}</ul>}
    {(d.activities || []).length > 0 && <><h3>Activity</h3>
      <ul className="activity-list">{d.activities!.map(a =>
        <li key={a.id}><strong>{a.type}</strong><span>{a.outcome || '—'}</span><small>{a.timestamp}</small></li>)}</ul></>}
  </div>
}

function CreateOppDialog({ credentials, token, pipeId, onClose, onSaved }: {
  credentials: Credentials; token: string; pipeId?: string; onClose: () => void; onSaved: () => void
}) {
  const api = commercialApi(credentials)
  const [account, setAccount] = useState<CAccount | null>(null)
  const [contact, setContact] = useState<{ id: string; label: string } | null>(null)
  const [value, setValue] = useState('')
  const [next, setNext] = useState('')
  const [error, setError] = useState('')
  const [busy, setBusy] = useState(false)

  async function save() {
    if (!account) { setError('Choose the account first.'); return }
    if (!token.trim()) { setError('Enter the founder action token at the top of the page first.'); return }
    setError(''); setBusy(true)
    try {
      await commercialWrite(credentials, token).createOpportunity({
        account_id: account.id,
        contact_ids: contact ? [contact.id] : [],
        pipeline_id: pipeId,
        value: value.trim() ? Number(value) : null,
        next_action: next.trim(),
      })
      onSaved()
    } catch (e) { setError(e instanceof Error ? e.message : 'Opportunity could not be created.') }
    finally { setBusy(false) }
  }
  return <Dialog title="New opportunity" intro="Pick real records — names in, IDs resolved behind the scenes." onClose={onClose}>
    <div className="cx-form">
      <SearchPicker label="Account" placeholder="Type at least 2 letters…" selected={account}
        renderOption={a => a.company_name}
        onSearch={async text => (await api.accounts({ q: text, page_size: 8 })).items}
        onPick={setAccount} />
      <SearchPicker label="Contact (optional)" placeholder="Type at least 2 letters…"
        selected={contact} renderOption={c => c.label}
        onSearch={async text => {
          const page = await contactsPage(credentials, { page: 1, q: text, stage: '', sort: 'recent' })
          return (page.items || []).map(c => ({ id: c.id, label: `${c.full_name || c.email} — ${c.company || ''}` }))
        }}
        onPick={setContact} />
      <div className="cx-grid">
        <Field label="Value (optional)"><input value={value} onChange={e => setValue(e.target.value)} inputMode="decimal" placeholder="e.g. 5000" /></Field>
        <Field label="Next action"><input value={next} onChange={e => setNext(e.target.value)} placeholder="e.g. Send proposal" /></Field>
      </div>
      {error && <p className="form-error" role="alert">{error}</p>}
      <div className="modal-actions"><button className="button secondary" onClick={onClose}>Cancel</button>
        <button className="button primary" disabled={busy} onClick={() => void save()}>{busy ? 'Saving…' : 'Create opportunity'}</button></div>
    </div>
  </Dialog>
}
