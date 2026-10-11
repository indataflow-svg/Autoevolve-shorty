import { useState } from 'react'
import { useQuery, useQueryClient } from '@tanstack/react-query'
import { useCredentials } from '../app/Auth'
import { AppShell } from '../components/Shell'
import { DataState, LoadingRows, StateBadge } from '../components/Primitives'
import { commercialApi, commercialWrite, previewImport, type ImportPreview } from '../api/commercial'
import { companyContext, replaceCompanyContext } from '../api/companyContext'
import { ApiError } from '../api/client'

function Token({ token, setToken }: { token: string; setToken: (v: string) => void }) {
  return <label className="onboarding-token">Founder action token
    <input type="password" autoComplete="off" aria-label="Founder action token" value={token} onChange={e => setToken(e.target.value)} />
    <small>Held only in this page's memory.</small></label>
}

type QualifyShape = {
  qualified: boolean; needs_human: boolean; hard_fail: boolean; unmet: string[]
  fit: { score?: number | null; grade: string; explanations?: Array<{ field: string; result: string; reason?: string; actual?: unknown }>; missing?: string[] }
  intent: { score: number; level: string; note: string; signals?: Array<{ signal: string; lead_id?: string }> }
}

function QualifyResult({ result }: { result: QualifyShape }) {
  const known = (result.fit.explanations || []).filter(e => e.result !== 'unknown')
  const unknown = (result.fit.explanations || []).filter(e => e.result === 'unknown')
  return <div className="validation-facts">
    <h3><StateBadge tone={result.qualified ? 'green' : 'yellow'}>{result.qualified ? 'Qualified' : 'Not qualified'}</StateBadge></h3>
    <p className="operational-note">Fit {result.fit.score ?? '—'} ({result.fit.grade}) · intent {result.intent.score} ({result.intent.level}) · {result.intent.note}</p>
    {known.length > 0 && <><h3><StateBadge tone="blue">Known</StateBadge></h3><ul>{known.map((e, i) =>
      <li key={i}>{e.field}: {e.result}{e.actual !== undefined ? ` (${String(e.actual)})` : ''}</li>)}</ul></>}
    {unknown.length > 0 && <><h3><StateBadge tone="yellow">Missing evidence</StateBadge></h3><ul>{unknown.map((e, i) =>
      <li key={i}>{e.field}: {e.reason || 'no data — not counted as a match'}</li>)}</ul></>}
    {result.unmet.length > 0 && <><h3><StateBadge tone="red">Unmet conditions</StateBadge></h3><ul>{result.unmet.map(u => <li key={u}>{u}</li>)}</ul></>}
    {result.needs_human && <p className="operational-note">Human review required before advancing.</p>}
  </div>
}

const PATH_STEPS: Record<string, string[]> = {
  A: ['company', 'icp', 'accounts', 'pipeline', 'rules', 'integrations', 'review'],
  B: ['company', 'discovery', 'import', 'customers', 'icp', 'pipeline', 'rules', 'integrations'],
}

const STEP_HELP: Record<string, string> = {
  company: 'Company and offer profile. Saved to the canonical company context.',
  icp: 'Initial ICP hypothesis. Provisional until validated with evidence.',
  accounts: 'Target-market and account list. Source is always preserved.',
  pipeline: 'CRM and pipeline configuration. Rules enforced server-side.',
  rules: 'Qualification rules. Fit, intent and qualification stay separate.',
  integrations: 'Optional integrations. Nothing is required to use the CRM or ICP.',
  review: 'Review and activation. Completion comes from saved data, not flags.',
  discovery: 'Existing data and platform review. Counts come from stored records.',
  import: 'CSV import or supported connections into the same canonical model.',
  customers: 'Existing customers and sales history. Suggested ICP follows from evidence.',
}

function OnboardingWizard({ sessions, activeId, onSelect, onStart, step, onStep, busy, children }: {
  sessions: Array<{ id: string; path: string; current_step: string; completed: number }>
  activeId: string
  onSelect: (id: string) => void
  onStart: (path: string) => void
  step: string
  onStep: (step: string) => void
  busy: boolean
  children: (step: string) => React.ReactNode
}) {
  const active = sessions.find(s => s.id === activeId)
  const steps = active ? PATH_STEPS[active.path] || [] : []
  return <section className="onboarding-panel"><div className="onboarding-panel-head">
    <h2>Guided setup</h2><p>Path A starts from zero · path B starts from existing data. Progress persists server-side; interrupted sessions resume where they stopped.</p></div>
    <div className="validation-actions">
      <button className="button secondary" disabled={busy} onClick={() => onStart('A')}>Start path A</button>
      <button className="button secondary" disabled={busy} onClick={() => onStart('B')}>Start path B</button>
      {sessions.map(s => <button key={s.id} className={`button ${s.id === activeId ? 'primary' : 'secondary'}`} disabled={busy} onClick={() => onSelect(s.id)}>Path {s.path} · {s.completed ? 'complete' : s.current_step}</button>)}
    </div>
    {active && <>
      <ol className="validation-lifecycle">{steps.map(s =>
        <li key={s} className={s === step ? 'reached' : ''}><StateBadge tone={s === step ? 'blue' : 'neutral'}>{s}</StateBadge></li>)}
      </ol>
      <p className="operational-note">{STEP_HELP[step] || ''}</p>
      {children(step)}
      <div className="validation-actions">
        <button className="button secondary" disabled={busy || steps.indexOf(step) <= 0} onClick={() => onStep(steps[steps.indexOf(step) - 1])}>Back</button>
        <button className="button primary" disabled={busy || steps.indexOf(step) >= steps.length - 1} onClick={() => onStep(steps[steps.indexOf(step) + 1])}>Next</button>
      </div>
    </>}
  </section>
}

export function CommercialPage() {
  const credentials = useCredentials()
  const queryClient = useQueryClient()
  const api = commercialApi(credentials)
  const [token, setToken] = useState('')
  const [error, setError] = useState('')
  const [busy, setBusy] = useState('')
  const [tab, setTab] = useState<'onboarding' | 'setup' | 'accounts' | 'pipeline' | 'integrations'>('onboarding')
  const [acctQuery, setAcctQuery] = useState('')
  const [acctLifecycle, setAcctLifecycle] = useState('')
  const [oppStage, setOppStage] = useState('')
  const [preview, setPreview] = useState<ImportPreview | null>(null)
  const [mappingText, setMappingText] = useState('')
  const [qualifyId, setQualifyId] = useState('')
  const [qualResult, setQualResult] = useState<unknown>(null)
  const [form, setForm] = useState<Record<string, string>>({})

  const offers = useQuery({ queryKey: ['c-offers'], queryFn: api.offers })
  const icps = useQuery({ queryKey: ['c-icps'], queryFn: api.icps })
  const accounts = useQuery({ queryKey: ['c-accounts', acctQuery, acctLifecycle], queryFn: () => api.accounts({ q: acctQuery, lifecycle_status: acctLifecycle, page_size: 30 }) })
  const pipelines = useQuery({ queryKey: ['c-pipelines'], queryFn: api.pipelines })
  const opps = useQuery({ queryKey: ['c-opps', oppStage], queryFn: () => api.opportunities(oppStage) })
  const rules = useQuery({ queryKey: ['c-rules'], queryFn: api.rules })
  const integrations = useQuery({ queryKey: ['c-integrations'], queryFn: api.integrations })
  const sessions = useQuery({ queryKey: ['c-sessions'], queryFn: api.sessions })
  const importsList = useQuery({ queryKey: ['c-imports'], queryFn: api.imports })
  const ctxView = useQuery({ queryKey: ['company-context'], queryFn: () => companyContext(credentials) })
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
  const [wizardId, setWizardId] = useState('')
  const [wizardStep, setWizardStep] = useState('company')

  const wizardSessions = (sessions.data || []).map(s => ({ id: s.id, path: s.path, current_step: s.current_step, completed: s.completed }))
  const wizardActive = wizardSessions.find(s => s.id === (wizardId || s.id)) || wizardSessions[0]
  const wizardIdEffective = wizardActive?.id || ''
  const wizardStepEffective = wizardActive && wizardIdEffective === wizardActive.id && wizardStep ? wizardStep : (wizardActive?.current_step || 'company')

  function persistStep(id: string, step: string, progress?: Record<string, unknown>) {
    if (!token.trim()) { setError('Enter the founder action token first.'); return }
    setError(''); setBusy('Saving progress')
    commercialWrite(credentials, token).updateSession(id, { current_step: step, ...(progress ? { progress } : {}) })
      .then(() => queryClient.invalidateQueries({ queryKey: ['c-sessions'] }))
      .catch(e => setError(e instanceof Error ? e.message : 'progress not saved'))
      .finally(() => setBusy(''))
  }

  // Completion is derived from saved data, never from frontend flags.
  const hasCompany = Boolean(ctxView.data && (ctxView.data.context as { company?: { name?: string } }).company?.name)
  const doneMap: Record<string, boolean> = {
    company: hasCompany && (offers.data || []).length > 0,
    icp: (icps.data || []).length > 0,
    accounts: (accounts.data?.total || 0) > 0,
    pipeline: (pipelines.data || []).length > 0,
    rules: (rules.data || []).length > 0,
    integrations: true,
    discovery: (accounts.data?.total || 0) > 0 || (importsList.data || []).length > 0,
    import: (importsList.data || []).some(i => i.status === 'committed'),
    customers: (accounts.data?.total || 0) > 0,
    review: hasCompany && (offers.data || []).length > 0 && (icps.data || []).length > 0
      && (accounts.data?.total || 0) > 0 && (pipelines.data || []).length > 0 && (rules.data || []).length > 0,
  }

  function wizardBody(step: string) {
    if (step === 'company') return <div className="context-answer-form">
      <label>Company name<input aria-label="Wizard company" value={f('wcompany')} onChange={e => set('wcompany', e.target.value)} placeholder={hasCompany ? 'Already saved — edit to update' : 'Company name'} /></label>
      <label>Offer name<input aria-label="Wizard offer" value={f('woffer')} onChange={e => set('woffer', e.target.value)} placeholder="Offer name" /></label>
      <div className="validation-actions"><button className="button secondary" disabled={busy !== '' || (!f('wcompany').trim() && !f('woffer').trim())} onClick={() => {
        if (!token.trim()) { setError('Enter the founder action token first.'); return }
        setError(''); setBusy('Saving company profile')
        const ctx = (ctxView.data?.context || {}) as Record<string, Record<string, string>>
        replaceCompanyContext(credentials, {
          ...ctxView.data?.context,
          company: { ...(ctx.company || {}), ...(f('wcompany').trim() ? { name: f('wcompany').trim() } : {}) },
        } as never, token)
          .then(() => queryClient.invalidateQueries({ queryKey: ['company-context'] }))
          .then(() => f('woffer').trim() ? commercialWrite(credentials, token).createOffer({ name: f('woffer').trim() }) : undefined)
          .then(() => queryClient.invalidateQueries({ queryKey: ['c-offers'] }))
          .catch(e => setError(e instanceof Error ? e.message : 'company not saved'))
          .finally(() => setBusy(''))
      }}>Save company and offer</button></div>
    </div>
    if (step === 'discovery') return <div>
      <p className="operational-note">Stored so far: {accounts.data?.total || 0} account(s) · {(importsList.data || []).length} import(s) · {(icps.data || []).length} ICP(s). Connect nothing to continue — integrations are optional.</p>
      <div className="validation-actions"><button className="button secondary" disabled={busy !== ''} onClick={() => wizardIdEffective && persistStep(wizardIdEffective, 'import', { discovery_reviewed: true })}>Mark reviewed</button></div>
    </div>
    if (step === 'import') return <p className="operational-note">Use the accounts tab to preview, map and commit a CSV, or connect a provider under integrations. {(importsList.data || []).filter(i => i.status === 'committed').length} committed import(s) so far.</p>
    if (step === 'customers') {
      const industries: Record<string, number> = {}
      for (const a of accounts.data?.items || []) {
        const ind = ((a as { industry?: string }).industry || '').trim() || 'unknown'
        industries[ind] = (industries[ind] || 0) + 1
      }
      const top = Object.entries(industries).sort((x, y) => y[1] - x[1])[0]
      return <div>
        <p className="operational-note">{accounts.data?.total || 0} account(s) on record.{top ? ` Most common industry: ${top[0]} (${top[1]}).` : ''}</p>
        {top && top[0] !== 'unknown' && <div className="validation-actions"><button className="button secondary" disabled={busy !== ''} onClick={() => void run('Suggesting ICP', w => w.createICP({ name: `${top[0]} ICP (suggested)`, criteria: [{ field: 'industry', operator: 'contains', value: top[0], weight: 2 }], assumptions: [`suggested from ${top[1]} stored account(s); validate before use`] }), ['c-icps'])}>Suggest ICP from evidence</button></div>}
        <p className="operational-note">Suggestions are provisional and editable — never verified truths.</p>
      </div>
    }
    if (step === 'review') {
      const items = ['company', 'icp', 'accounts', 'pipeline', 'rules'] as const
      return <div>
        <ul className="onboarding-list">{items.map(k => <li key={k}>{k}: {doneMap[k] ? 'complete' : 'missing'}</li>)}
          <li>integrations: optional ({(integrations.data || []).filter(c => c.connection).length} connected)</li></ul>
        <div className="validation-actions"><button className="button primary" disabled={busy !== '' || !doneMap.review} onClick={() => wizardIdEffective && persistStep(wizardIdEffective, 'review', { activated: true })}>Activate</button></div>
        {!doneMap.review && <p className="operational-note">Activation needs company, offer, ICP, account, pipeline and rule — finish the missing steps above.</p>}
      </div>
    }
    const go: Record<string, string> = { icp: 'setup', accounts: 'accounts', pipeline: 'pipeline', rules: 'setup', integrations: 'integrations' }
    return <div>
      <p className="operational-note">{doneMap[step] ? 'Complete from saved data.' : 'Not yet complete — use the linked tab.'}</p>
      <div className="validation-actions"><button className="button secondary" onClick={() => setTab((go[step] || 'setup') as typeof tab)}>Open {go[step] || 'setup'}</button></div>
    </div>
  }

  return <AppShell active="Commercial" query="" onQueryChange={() => undefined}>
    <div className="page-layout"><main className="page-main"><div className="page-content validation-page">
      <div className="page-heading"><div><p className="eyebrow">Phase 1</p><h1>Commercial foundation</h1>
        <p className="lede">Offers, ICPs, accounts, pipelines, qualification and integrations on one canonical model. Provisional stays provisional; unknowns stay unknown.</p></div></div>
      <Token token={token} setToken={setToken} />
      {error && <p className="form-error" role="alert">{error}</p>}
      {busy && <p role="status" className="operational-note">{busy}…</p>}
      <div className="validation-actions" role="tablist" aria-label="Commercial sections">
        {(['onboarding', 'setup', 'accounts', 'pipeline', 'integrations'] as const).map(t =>
          <button key={t} role="tab" aria-selected={tab === t} className={`button ${tab === t ? 'primary' : 'secondary'}`} onClick={() => setTab(t)}>{t}</button>)}
      </div>
      {loading ? <LoadingRows label="Loading commercial foundation" /> : failed
        ? <DataState title="Commercial data could not be loaded" detail={failed.error instanceof ApiError ? failed.error.message : 'request failed'} retry={() => queryClient.invalidateQueries()} />
        : <>
          {tab === 'onboarding' && <OnboardingWizard
            sessions={wizardSessions}
            activeId={wizardIdEffective}
            onSelect={id => {
              setWizardId(id)
              const s = wizardSessions.find(x => x.id === id)
              if (s) setWizardStep(s.current_step)
            }}
            onStart={path => {
              if (!token.trim()) { setError('Enter the founder action token first.'); return }
              setError(''); setBusy('Starting guided setup')
              commercialWrite(credentials, token).createSession({ path })
                .then(r => queryClient.invalidateQueries({ queryKey: ['c-sessions'] }).then(() => r))
                .then(r => { setWizardId((r as { id: string }).id); setWizardStep('company') })
                .catch(e => setError(e instanceof Error ? e.message : 'session not started'))
                .finally(() => setBusy(''))
            }}
            step={wizardStepEffective}
            onStep={s => { setWizardStep(s); if (wizardIdEffective) persistStep(wizardIdEffective, s) }}
            busy={busy !== ''}
          >{wizardBody}</OnboardingWizard>}
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
                <label>Search<input aria-label="Search accounts" value={acctQuery} onChange={e => setAcctQuery(e.target.value)} placeholder="Name, domain or industry" /></label>
                <label>Lifecycle<select aria-label="Lifecycle filter" value={acctLifecycle} onChange={e => setAcctLifecycle(e.target.value)}>
                  <option value="">All lifecycles</option>
                  {['target', 'engaged', 'customer', 'former'].map(s => <option key={s} value={s}>{s}</option>)}
                </select></label>
              </div>
              <div className="validation-actions">
                <button className="button secondary" disabled={busy !== '' || !f('acct').trim()} onClick={() => void run('Saving account', w => w.createAccount({ company_name: f('acct') }), ['c-accounts'])}>Save account</button>
                <span className="operational-note">{accounts.data?.total ?? 0} account(s)</span>
              </div>
              <ul className="onboarding-list">{(accounts.data?.items || []).map(a =>
                <li key={a.id}><strong>{a.company_name}</strong> · {a.fit_grade}{typeof a.fit_score === 'number' ? ` (${a.fit_score})` : ''} · {a.lifecycle_status}</li>)}</ul>
            </section>
            <section className="onboarding-panel"><div className="onboarding-panel-head"><h2>CSV import</h2><p>Preview, map, dedupe, then commit. Retries never duplicate.</p></div>
              <label className="onboarding-token">CSV file<input type="file" accept=".csv" aria-label="CSV file" onChange={e => void onFile(e.target.files?.[0])} /></label>
              {preview && <>
                <p className="operational-note">Rows {preview.totals.rows} · exact duplicates {preview.totals.exact_duplicates} · ambiguous {preview.totals.ambiguous} · to create {preview.totals.to_create}</p>
                {preview.ambiguous.length > 0 && <ul className="onboarding-list">{preview.ambiguous.map(a =>
                  <li key={a.row}>Row {a.row}: {a.reason} — skipped unless mapped below</li>)}</ul>}
                <div className="context-answer-form"><label>Column mapping (CSV header → canonical field)
                  <textarea aria-label="Column mapping" rows={4} value={mappingText} onChange={e => setMappingText(e.target.value)} /></label>
                  <label>Duplicate handling<select aria-label="Duplicate handling" value={f('impmode') || 'create_only'} onChange={e => set('impmode', e.target.value)}>
                    <option value="create_only">Skip existing (create only)</option>
                    <option value="upsert">Refresh existing with incoming fields</option>
                  </select></label>
                  <label>Skip rows (comma-separated)<input aria-label="Skip rows" value={f('skiprows')} onChange={e => set('skiprows', e.target.value)} placeholder="e.g. 2, 5" /></label></div>
                <div className="validation-actions">
                  <button className="button primary" disabled={busy !== ''} onClick={() => {
                    let mapping: Record<string, string> = {}
                    try { mapping = JSON.parse(mappingText) } catch { setError('Mapping is not valid JSON'); return }
                    const skip_rows = (f('skiprows') || '').split(',').map(s => parseInt(s.trim(), 10)).filter(n => Number.isFinite(n))
                    void run('Committing import', w => w.commitImport(preview.import_id, { mapping, skip_rows, mode: f('impmode') || 'create_only' }), ['c-accounts'])
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
              {qualResult !== null && <QualifyResult result={qualResult as QualifyShape} />}
            </section>
          </>}
          {tab === 'pipeline' && <>
            <section className="onboarding-panel"><div className="onboarding-panel-head"><h2>Pipelines</h2><p>Stage order and allowed transitions are enforced server-side. Stages in use cannot be removed.</p></div>
              <div className="context-answer-form">
                <label>Filter opportunities by stage<select aria-label="Stage filter" value={oppStage} onChange={e => setOppStage(e.target.value)}>
                  <option value="">All stages</option>
                  {['prospect', 'qualified', 'proposal', 'negotiation', 'won', 'lost', 'deferred', 'disqualified'].map(s => <option key={s} value={s}>{s}</option>)}
                </select></label>
              </div>
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
              <ul className="onboarding-list">{(opps.data?.items || []).map(o =>
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
