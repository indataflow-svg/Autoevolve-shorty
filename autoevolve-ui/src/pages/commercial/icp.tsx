/** ICP workspace (configure) kept separate from qualification (evaluate). */
import { useEffect, useState } from 'react'
import { useQuery, useQueryClient } from '@tanstack/react-query'
import type { Credentials } from '../../api/client'
import { commercialApi, commercialWrite, type CAccount, type ICPDetail } from '../../api/commercial'
import { StateBadge } from '../../components/Primitives'
import { Dialog, Empty, Field, SearchPicker, Section } from './shared'

const SECTIONS: Array<{ title: string; fields: string[] }> = [
  { title: 'Company profile', fields: ['industry', 'company_size', 'company_name', 'domain'] },
  { title: 'Geographic and operational fit', fields: ['region', 'country'] },
  { title: 'Problem intensity', fields: ['problem', 'pain'] },
  { title: 'Economic fit', fields: ['budget', 'pricing', 'revenue'] },
  { title: 'Buying readiness', fields: ['readiness', 'timeline', 'authority'] },
]

function sectionFor(field: string): string {
  for (const s of SECTIONS) if (s.fields.includes(field)) return s.title
  return 'Other criteria'
}

type Criterion = { field: string; operator: string; value: unknown; weight?: number }

export function IcpSection({ credentials, token, presetAccount, onPresetConsumed }: {
  credentials: Credentials; token: string
  presetAccount: CAccount | null; onPresetConsumed: () => void
}) {
  const queryClient = useQueryClient()
  const api = commercialApi(credentials)
  const [openId, setOpenId] = useState<string | null>(null)
  const [showCreate, setShowCreate] = useState(false)
  const icps = useQuery({ queryKey: ['c-icps'], queryFn: api.icps })

  return <div className="cx-two">
    <Section title="ICP profiles" intro={`${(icps.data || []).length} profile(s). Provisional until validated with evidence.`}
      action={<button className="button primary" onClick={() => setShowCreate(true)}>Create ICP</button>}>
      {icps.isError && <p className="form-error" role="alert">ICP profiles could not be loaded.</p>}
      {(icps.data || []).length === 0
        ? <Empty title="No ICP yet" detail="Create a hypothesis to score accounts against. It stays provisional until you validate it." action={<button className="button primary" onClick={() => setShowCreate(true)}>Create ICP</button>} />
        : <ul className="cx-cards cx-cards-row">{(icps.data || []).map(i =>
          <li key={i.id}><button className={`cx-card cx-pick${openId === i.id ? ' active' : ''}`} onClick={() => setOpenId(i.id)}>
            <strong>{i.name}</strong><span>v{i.version} · {i.segment || 'no segment'}</span>
            <StateBadge tone={i.status === 'validated' ? 'green' : i.status === 'archived' ? 'neutral' : 'yellow'}>{i.status}</StateBadge>
          </button></li>)}</ul>}
      {openId && <IcpDetail credentials={credentials} token={token} id={openId}
        onClose={() => setOpenId(null)}
        onChanged={() => void queryClient.invalidateQueries({ queryKey: ['c-icps'] })} />}
      {showCreate && <CreateIcpDialog credentials={credentials} token={token} onClose={() => setShowCreate(false)}
        onSaved={() => { setShowCreate(false); void queryClient.invalidateQueries({ queryKey: ['c-icps'] }) }} />}
    </Section>
    <QualifyWorkspace credentials={credentials} token={token} presetAccount={presetAccount} onPresetConsumed={onPresetConsumed} />
  </div>
}

function parsed(json: string): Criterion[] {
  try { const v = JSON.parse(json); return Array.isArray(v) ? v : [] } catch { return [] }
}

function IcpDetail({ credentials, token, id, onClose, onChanged }: {
  credentials: Credentials; token: string; id: string; onClose: () => void; onChanged: () => void
}) {
  const api = commercialApi(credentials)
  const queryClient = useQueryClient()
  const detail = useQuery({ queryKey: ['c-icp', id], queryFn: () => api.icp(id) })
  const [error, setError] = useState('')
  const [busy, setBusy] = useState(false)
  const [newField, setNewField] = useState('')
  const [newValue, setNewValue] = useState('')

  async function patch(patch: Record<string, unknown>, label: string) {
    if (!token.trim()) { setError('Enter the founder action token at the top of the page first.'); return }
    setError(''); setBusy(true)
    try {
      await commercialWrite(credentials, token).updateICP(id, patch)
      await queryClient.invalidateQueries({ queryKey: ['c-icp', id] })
      onChanged()
    } catch (e) { setError(e instanceof Error ? e.message : `${label} failed.`) }
    finally { setBusy(false) }
  }

  const d = detail.data as ICPDetail | undefined
  const criteria = d ? parsed(d.criteria_json) : []
  const exclusions = d ? parsed(d.exclusions_json) : []
  const provenance: Record<string, string> = (() => { try { return JSON.parse(d?.provenance_json || '{}') } catch { return {} } })()
  const groups = new Map<string, Criterion[]>()
  for (const c of criteria) {
    const g = sectionFor(c.field)
    groups.set(g, [...(groups.get(g) || []), c])
  }

  return <Dialog title={d ? d.name : 'ICP'} intro={d ? `Version ${d.version} · ${d.status} · confidence ${d.confidence}` : undefined} onClose={onClose} wide>
    {detail.isPending ? <p className="cx-note">Loading…</p> : !d ? <p className="cx-note">Not found.</p> : <>
      {error && <p className="form-error" role="alert">{error}</p>}
      {[...groups.entries()].map(([title, list]) => <div key={title}><h3>{title}</h3>
        <ul className="cx-list">{list.map((c, i) => <li key={i}>
          <strong>{c.field}</strong> {c.operator} “{String(c.value)}”
          <small> · {provenance[c.field] || 'user-defined'}</small>
          <button className="cx-link" disabled={busy} onClick={() => void patch(
            { criteria: criteria.filter(x => x !== c) }, 'Removing criterion')}>remove</button>
        </li>)}</ul></div>)}
      {groups.size === 0 && <Empty title="No criteria yet" detail="Add the first attribute this ICP should match on." />}
      <div className="cx-form"><div className="cx-grid">
        <Field label="New criterion field"><input value={newField} onChange={e => setNewField(e.target.value)} placeholder="e.g. industry" /></Field>
        <Field label="Value it should match"><input value={newValue} onChange={e => setNewValue(e.target.value)} placeholder="e.g. logistics" /></Field>
      </div>
        <div className="modal-actions">
          <button className="button secondary" disabled={busy || !newField.trim() || !newValue.trim()}
            onClick={() => { void patch({ criteria: [...criteria, { field: newField.trim(), operator: 'contains', value: newValue.trim(), weight: 1 }] }, 'Adding criterion'); setNewField(''); setNewValue('') }}>Add criterion</button>
        </div></div>
      {exclusions.length > 0 && <><h3>Exclusions</h3>
        <ul className="cx-list">{exclusions.map((c, i) => <li key={i}><strong>{c.field}</strong> must not be “{String(c.value)}”</li>)}</ul></>}
      <div className="modal-actions">
        {d.status !== 'validated' && <button className="button secondary" disabled={busy} onClick={() => void patch({ status: 'validated' }, 'Validating')}>Mark validated</button>}
        {d.status !== 'archived' && <button className="button secondary" disabled={busy}
          onClick={() => { if (window.confirm('Archive this ICP? Linked accounts keep their last score.')) void patch({ status: 'archived' }, 'Archiving') }}>Archive</button>}
      </div>
    </>}
  </Dialog>
}

function CreateIcpDialog({ credentials, token, onClose, onSaved }: {
  credentials: Credentials; token: string; onClose: () => void; onSaved: () => void
}) {
  const api = commercialApi(credentials)
  const templates = useQuery({ queryKey: ['c-icp-templates'], queryFn: api.icpTemplates })
  const [name, setName] = useState('')
  const [industry, setIndustry] = useState('')
  const [template, setTemplate] = useState('')
  const [error, setError] = useState('')
  const [busy, setBusy] = useState(false)
  async function save() {
    if (!name.trim()) { setError('Give the ICP a name.'); return }
    if (!token.trim()) { setError('Enter the founder action token at the top of the page first.'); return }
    setError(''); setBusy(true)
    try {
      const tpl = (templates.data || []).find(t => t.key === template)
      const criteria = tpl ? (tpl.criteria as Criterion[]).map(c =>
        c.field === 'industry' && industry.trim() ? { ...c, value: industry.trim() } : c)
        : [{ field: 'industry', operator: 'contains', value: industry.trim() || name.trim(), weight: 2 }]
      await commercialWrite(credentials, token).createICP({
        name: name.trim(), criteria, exclusions: tpl ? tpl.exclusions : [],
      })
      onSaved()
    } catch (e) { setError(e instanceof Error ? e.message : 'ICP could not be saved.') }
    finally { setBusy(false) }
  }
  return <Dialog title="Create ICP" intro="New profiles are provisional. Templates are editable starting points, never verified truths." onClose={onClose}>
    <div className="cx-form">
      <Field label="ICP name"><input value={name} onChange={e => setName(e.target.value)} placeholder="e.g. Logistics SMB" /></Field>
      <Field label="Industry it matches"><input value={industry} onChange={e => setIndustry(e.target.value)} placeholder="e.g. logistics" /></Field>
      <Field label="Start from a template (optional)"><select aria-label="ICP template" value={template} onChange={e => setTemplate(e.target.value)}>
        <option value="">Blank hypothesis</option>
        {(templates.data || []).map(t => <option key={t.key} value={t.key}>{t.name}</option>)}
      </select></Field>
      {error && <p className="form-error" role="alert">{error}</p>}
      <div className="modal-actions"><button className="button secondary" onClick={onClose}>Cancel</button>
        <button className="button primary" disabled={busy} onClick={() => void save()}>{busy ? 'Saving…' : 'Save provisional ICP'}</button></div>
    </div>
  </Dialog>
}

type QualifyShape = {
  qualified: boolean; needs_human: boolean; hard_fail: boolean; unmet: string[]
  fit: { score?: number | null; grade: string; explanations?: Array<{ field: string; result: string; reason?: string; actual?: unknown }>; missing?: string[] }
  intent: { score: number; level: string; note: string; signals?: Array<{ signal: string }> }
}

export function QualifyWorkspace({ credentials, token, presetAccount, onPresetConsumed }: {
  credentials: Credentials; token: string
  presetAccount: CAccount | null; onPresetConsumed: () => void
}) {
  const api = commercialApi(credentials)
  const [account, setAccount] = useState<CAccount | null>(null)
  const [result, setResult] = useState<QualifyShape | null>(null)
  const [error, setError] = useState('')
  const [busy, setBusy] = useState(false)
  const shown = presetAccount || account
  useEffect(() => {
    if (presetAccount) { setAccount(presetAccount); setResult(null); onPresetConsumed() }
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [presetAccount?.id])

  async function qualify() {
    const id = shown?.id
    if (!id) { setError('Pick an account first.'); return }
    if (!token.trim()) { setError('Enter the founder action token at the top of the page first.'); return }
    setError(''); setBusy(true); setResult(null)
    try { setResult(await commercialWrite(credentials, token).qualify(id) as QualifyShape) }
    catch (e) { setError(e instanceof Error ? e.message : 'Qualification failed.') }
    finally { setBusy(false) }
  }

  return <Section title="Qualification" intro="Fit, intent, and rules are evaluated separately by the backend. Missing evidence never counts as a match.">
    <SearchPicker label="Account" placeholder="Type at least 2 letters of the company name…"
      selected={shown} renderOption={a => `${a.company_name}`}
      onSearch={async text => (await api.accounts({ q: text, page_size: 8 })).items}
      onPick={a => { setAccount(a); setResult(null) }} />
    <div className="validation-actions">
      <button className="button primary" disabled={busy || !shown} onClick={() => void qualify()}>{busy ? 'Evaluating…' : 'Evaluate account'}</button>
    </div>
    {error && <p className="form-error" role="alert">{error}</p>}
    {result && <div className="cx-result">
      <h3>Verdict: {result.qualified ? 'Qualified' : 'Not qualified'}</h3>
      <p className="cx-note">Fit {result.fit.score ?? '—'} ({result.fit.grade}) · intent {result.intent.score} ({result.intent.level}) · {result.intent.note}</p>
      {(result.fit.explanations || []).filter(e => e.result !== 'unknown').length > 0 && <>
        <h4>What matched or missed</h4>
        <ul className="cx-list">{(result.fit.explanations || []).filter(e => e.result !== 'unknown').map((e, i) =>
          <li key={i}>{e.field}: {e.result}{e.actual !== undefined ? ` (found “${String(e.actual)}”)` : ''}</li>)}</ul></>}
      {(result.fit.explanations || []).filter(e => e.result === 'unknown').length > 0 && <>
        <h4>Missing evidence</h4>
        <ul className="cx-list">{(result.fit.explanations || []).filter(e => e.result === 'unknown').map((e, i) =>
          <li key={i}>{e.field}: {e.reason || 'no data — not counted either way'}</li>)}</ul></>}
      {result.unmet.length > 0 && <><h4>Unmet conditions</h4>
        <ul className="cx-list">{result.unmet.map(u => <li key={u}>{u}</li>)}</ul></>}
      {result.needs_human && <p className="cx-note">Human review required before advancing this account.</p>}
    </div>}
  </Section>
}
