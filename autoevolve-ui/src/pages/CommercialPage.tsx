import { useState } from 'react'
import { useQuery, useQueryClient } from '@tanstack/react-query'
import { useCredentials } from '../app/Auth'
import { AppShell } from '../components/Shell'
import { DataState, LoadingRows, StateBadge } from '../components/Primitives'
import { commercialApi, commercialWrite, previewImport, type ImportPreview } from '../api/commercial'
import { ApiError } from '../api/client'

function Token({ token, setToken }: { token: string; setToken: (v: string) => void }) {
  return <label className="onboarding-token">Founder action token
    <input type="password" autoComplete="off" aria-label="Founder action token" value={token} onChange={e => setToken(e.target.value)} />
    <small>Held only in this page's memory.</small></label>
}

export function CommercialPage() {
  const credentials = useCredentials()
  const queryClient = useQueryClient()
  const api = commercialApi(credentials)
  const [token, setToken] = useState('')
  const [error, setError] = useState('')
  const [busy, setBusy] = useState('')
  const [tab, setTab] = useState<'setup' | 'accounts' | 'pipeline' | 'integrations'>('setup')
  const [preview, setPreview] = useState<ImportPreview | null>(null)
  const [mappingText, setMappingText] = useState('')
  const [qualifyId, setQualifyId] = useState('')
  const [qualResult, setQualResult] = useState<unknown>(null)
  const [form, setForm] = useState<Record<string, string>>({})

  const offers = useQuery({ queryKey: ['c-offers'], queryFn: api.offers })
  const icps = useQuery({ queryKey: ['c-icps'], queryFn: api.icps })
  const accounts = useQuery({ queryKey: ['c-accounts'], queryFn: api.accounts })
  const pipelines = useQuery({ queryKey: ['c-pipelines'], queryFn: api.pipelines })
  const opps = useQuery({ queryKey: ['c-opps'], queryFn: api.opportunities })
  const rules = useQuery({ queryKey: ['c-rules'], queryFn: api.rules })
  const integrations = useQuery({ queryKey: ['c-integrations'], queryFn: api.integrations })
  const sessions = useQuery({ queryKey: ['c-sessions'], queryFn: api.sessions })
  const loading = [offers, icps, accounts, pipelines, opps, rules, integrations, sessions].some(q => q.isPending)
  const failed = [offers, icps, accounts, pipelines, opps, rules, integrations, sessions].find(q => q.isError)

  async function run(label: string, fn: (w: ReturnType<typeof commercialWrite>) => Promise<unknown>, invalidate: string[]) {
    if (!token.trim()) { setError('Enter the founder action token first.'); return }
    setError(''); setBusy(label)
    try {
      await fn(commercialWrite(credentials, token))
      for (const k of invalidate) await queryClient.invalidateQueries({ queryKey: [k] })
    } catch (e) {
      setError(e instanceof Error ? e.message : `${label} failed`)
    } finally { setBusy('') }
  }

  async function onFile(file: File | undefined) {
    if (!file) return
    if (!token.trim()) { setError('Enter the founder action token first.'); return }
    setError(''); setBusy('Previewing CSV')
    try {
      const p = await previewImport(credentials, token, 'account', file)
      setPreview(p)
      setMappingText(JSON.stringify(p.suggested_mapping, null, 1))
    } catch (e) {
      setError(e instanceof Error ? e.message : 'preview failed')
    } finally { setBusy('') }
  }

  const f = (k: string) => form[k] || ''
  const set = (k: string, v: string) => setForm(s => ({ ...s, [k]: v }))

  return <AppShell active="Commercial" query="" onQueryChange={() => undefined}>
    <div className="page-layout"><main className="page-main"><div className="page-content validation-page">
      <div className="page-heading"><div><p className="eyebrow">Phase 1</p><h1>Commercial foundation</h1>
        <p className="lede">Offers, ICPs, accounts, pipelines, qualification and integrations on one canonical model. Provisional stays provisional; unknowns stay unknown.</p></div></div>
      <Token token={token} setToken={setToken} />
      {error && <p className="form-error" role="alert">{error}</p>}
      {busy && <p role="status" className="operational-note">{busy}…</p>}
      <div className="validation-actions" role="tablist" aria-label="Commercial sections">
        {(['setup', 'accounts', 'pipeline', 'integrations'] as const).map(t =>
          <button key={t} role="tab" aria-selected={tab === t} className={`button ${tab === t ? 'primary' : 'secondary'}`} onClick={() => setTab(t)}>{t}</button>)}
      </div>
      {loading ? <LoadingRows label="Loading commercial foundation" /> : failed
        ? <DataState title="Commercial data could not be loaded" detail={failed.error instanceof ApiError ? failed.error.message : 'request failed'} retry={() => queryClient.invalidateQueries()} />
        : <>
          {tab === 'setup' && <>
            <section className="onboarding-panel"><div className="onboarding-panel-head"><h2>Onboarding paths</h2>
              <p>Path A starts from zero; path B starts from existing data and CSV. Both persist server-side and resume.</p></div>
              <div className="validation-actions">
                <button className="button secondary" disabled={busy !== ''} onClick={() => void run('Starting path A', w => w.createSession({ path: 'A' }), ['c-sessions'])}>Start path A</button>
                <button className="button secondary" disabled={busy !== ''} onClick={() => void run('Starting path B', w => w.createSession({ path: 'B' }), ['c-sessions'])}>Start path B</button>
              </div>
              <ul className="onboarding-list">{(sessions.data || []).map(s =>
                <li key={s.id}><strong>{s.id}</strong> · path {s.path} · step {s.current_step} · {s.completed ? 'complete' : 'in progress'}</li>)}</ul>
            </section>
            <section className="onboarding-panel"><div className="onboarding-panel-head"><h2>Offers</h2><p>Multiple offers allowed. Never global defaults.</p></div>
              <div className="context-answer-form">
                <label>New offer<input aria-label="New offer" value={f('offer')} onChange={e => set('offer', e.target.value)} placeholder="Name and one-line description" /></label>
              </div>
              <div className="validation-actions">
                <button className="button secondary" disabled={busy !== '' || !f('offer').trim()} onClick={() => void run('Saving offer', w => w.createOffer({ name: f('offer') }), ['c-offers'])}>Save offer</button>
              </div>
              <ul className="onboarding-list">{(offers.data || []).map(o =>
                <li key={o.id}><strong>{o.name}</strong> <StateBadge tone={o.status === 'active' ? 'green' : 'neutral'}>{o.status}</StateBadge></li>)}</ul>
            </section>
            <section className="onboarding-panel"><div className="onboarding-panel-head"><h2>ICP profiles</h2><p>Provisional until validated. Edits re-fit linked accounts.</p></div>
              <div className="context-answer-form">
                <label>New ICP<input aria-label="New ICP" value={f('icp')} onChange={e => set('icp', e.target.value)} placeholder="e.g. Logistics SMB" /></label>
              </div>
              <div className="validation-actions">
                <button className="button secondary" disabled={busy !== '' || !f('icp').trim()} onClick={() => void run('Saving ICP', w => w.createICP({ name: f('icp'), criteria: [{ field: 'industry', operator: 'contains', value: f('icp') }] }), ['c-icps'])}>Save provisional ICP</button>
              </div>
              <ul className="onboarding-list">{(icps.data || []).map(i =>
                <li key={i.id}><strong>{i.name}</strong> v{i.version} <StateBadge tone={i.status === 'validated' ? 'green' : 'yellow'}>{i.status}</StateBadge></li>)}</ul>
            </section>
            <section className="onboarding-panel"><div className="onboarding-panel-head"><h2>Qualification rules</h2><p>Fit, intent and qualification are separate. Hard disqualifiers enforced.</p></div>
              <div className="context-answer-form">
                <label>New rule<input aria-label="New rule" value={f('rule')} onChange={e => set('rule', e.target.value)} placeholder="e.g. fit score at least 40" /></label>
              </div>
              <div className="validation-actions">
                <button className="button secondary" disabled={busy !== '' || !f('rule').trim()} onClick={() => void run('Saving rule', w => w.createRule({ name: f('rule'), criterion: f('rule'), rule_type: 'fit', threshold: 40 }), ['c-rules'])}>Save rule</button>
              </div>
              <ul className="onboarding-list">{(rules.data || []).map(r =>
                <li key={r.id}><strong>{r.name}</strong> <StateBadge tone="blue">{r.rule_type}</StateBadge></li>)}</ul>
            </section>
          </>}
          {tab === 'accounts' && <>
            <section className="onboarding-panel"><div className="onboarding-panel-head"><h2>Target accounts</h2><p>Source is always preserved. Unknowns stay unknown.</p></div>
              <div className="context-answer-form">
                <label>New account<input aria-label="New account" value={f('acct')} onChange={e => set('acct', e.target.value)} placeholder="Company name" /></label>
              </div>
              <div className="validation-actions">
                <button className="button secondary" disabled={busy !== '' || !f('acct').trim()} onClick={() => void run('Saving account', w => w.createAccount({ company_name: f('acct') }), ['c-accounts'])}>Save account</button>
              </div>
              <ul className="onboarding-list">{(accounts.data || []).slice(0, 30).map(a =>
                <li key={a.id}><strong>{a.company_name}</strong> · {a.fit_grade}{typeof a.fit_score === 'number' ? ` (${a.fit_score})` : ''} · {a.lifecycle_status}</li>)}</ul>
            </section>
            <section className="onboarding-panel"><div className="onboarding-panel-head"><h2>CSV import</h2><p>Preview, map, dedupe, then commit. Retries never duplicate.</p></div>
              <label className="onboarding-token">CSV file<input type="file" accept=".csv" aria-label="CSV file" onChange={e => void onFile(e.target.files?.[0])} /></label>
              {preview && <>
                <p className="operational-note">Rows {preview.totals.rows} · exact duplicates {preview.totals.exact_duplicates} · ambiguous {preview.totals.ambiguous} · to create {preview.totals.to_create}</p>
                <div className="context-answer-form"><label>Column mapping (CSV header → canonical field)
                  <textarea aria-label="Column mapping" rows={4} value={mappingText} onChange={e => setMappingText(e.target.value)} /></label></div>
                <div className="validation-actions">
                  <button className="button primary" disabled={busy !== ''} onClick={() => {
                    let mapping: Record<string, string> = {}
                    try { mapping = JSON.parse(mappingText) } catch { setError('Mapping is not valid JSON'); return }
                    void run('Committing import', w => w.commitImport(preview.import_id, { mapping }), ['c-accounts'])
                  }}>Commit import</button>
                </div>
              </>}
            </section>
            <section className="onboarding-panel"><div className="onboarding-panel-head"><h2>Qualify</h2><p>Fit, intent and rules evaluated separately, with reasons.</p></div>
              <div className="context-answer-form">
                <label>Account id<input aria-label="Account id" value={qualifyId} onChange={e => setQualifyId(e.target.value)} placeholder="acct_…" /></label>
              </div>
              <div className="validation-actions">
                <button className="button secondary" disabled={busy !== '' || !qualifyId.trim()} onClick={() => {
                  if (!token.trim()) { setError('Enter the founder action token first.'); return }
                  setBusy('Qualifying'); setError('')
                  commercialWrite(credentials, token).qualify(qualifyId.trim())
                    .then(r => setQualResult(r)).catch(e => setError(e instanceof Error ? e.message : 'qualify failed'))
                    .finally(() => setBusy(''))
                }}>Qualify account</button>
              </div>
              {qualResult !== null && <pre className="operational-note">{JSON.stringify(qualResult, null, 1)}</pre>}
            </section>
          </>}
          {tab === 'pipeline' && <>
            <section className="onboarding-panel"><div className="onboarding-panel-head"><h2>Pipelines</h2><p>Stage order and allowed transitions are enforced server-side.</p></div>
              <ul className="onboarding-list">{(pipelines.data || []).map(p => {
                let stages: Array<{ key: string; label: string }> = []
                try { stages = JSON.parse(p.stages_json) } catch { stages = [] }
                return <li key={p.id}><strong>{p.name}</strong> · {stages.map(s => s.label || s.key).join(' → ')}</li>
              })}</ul>
            </section>
            <section className="onboarding-panel"><div className="onboarding-panel-head"><h2>Opportunities</h2><p>Moves outside the allowed transitions are refused with a reason.</p></div>
              <div className="context-answer-form">
                <label>New opportunity (account id)<input aria-label="New opportunity account" value={f('opp')} onChange={e => set('opp', e.target.value)} placeholder="acct_…" /></label>
                <label>Move opportunity (opp id:stage)<input aria-label="Move opportunity" value={f('move')} onChange={e => set('move', e.target.value)} placeholder="opp_…:qualified" /></label>
              </div>
              <div className="validation-actions">
                <button className="button secondary" disabled={busy !== '' || !f('opp').trim()} onClick={() => void run('Creating opportunity', w => w.createOpportunity({ account_id: f('opp').trim() }), ['c-opps'])}>Create</button>
                <button className="button secondary" disabled={busy !== '' || !f('move').includes(':')} onClick={() => {
                  const [id, stage] = f('move').split(':')
                  void run('Moving opportunity', w => w.moveOpportunity(id.trim(), { stage: stage.trim(), lost_reason: stage.trim() === 'lost' ? 'stated on page' : '' }), ['c-opps'])
                }}>Move</button>
              </div>
              <ul className="onboarding-list">{(opps.data || []).map(o =>
                <li key={o.id}><strong>{o.id}</strong> · {o.stage} · {o.outcome}</li>)}</ul>
            </section>
          </>}
          {tab === 'integrations' && <>
            <section className="onboarding-panel"><div className="onboarding-panel-head"><h2>Integration catalog</h2><p>States come from the backend and provider checks. Nothing is marked connected because a button was clicked.</p></div>
              <ul className="onboarding-list">{(integrations.data || []).map(c =>
                <li key={c.provider}><strong>{c.label}</strong> · {c.connection ? `${c.connection.status} / sync ${c.connection.sync_status}` : (c.state || 'unavailable')}{c.blocker ? ` — ${c.blocker}` : ''}
                  <span className="validation-actions">
                    {!c.connection && c.state === 'available' && <button className="button secondary" disabled={busy !== ''} onClick={() => void run(`Connecting ${c.provider}`, w => w.connect(c.provider, {}), ['c-integrations'])}>Connect</button>}
                    {c.connection && <button className="button secondary" disabled={busy !== ''} onClick={() => void run(`Syncing ${c.provider}`, w => w.sync(c.provider), ['c-integrations'])}>Sync</button>}
                    {c.connection && <button className="button secondary" disabled={busy !== ''} onClick={() => void run(`Disconnecting ${c.provider}`, w => w.disconnect(c.provider), ['c-integrations'])}>Disconnect</button>}
                  </span></li>)}</ul>
            </section>
          </>}
        </>}
    </div></main></div>
  </AppShell>
}
