/** One coherent guided setup. Two starting choices, one stepper, no duplicate buttons. */
import { useEffect, useState } from 'react'
import { useQuery, useQueryClient } from '@tanstack/react-query'
import { useNavigate } from 'react-router-dom'
import type { Credentials } from '../../api/client'
import { commercialApi, commercialWrite } from '../../api/commercial'
import { companyContext, replaceCompanyContext } from '../../api/companyContext'
import { Empty, Field, Stepper } from './shared'
import { CsvWizard } from './csvWizard'

const STORAGE_KEY = 'cx-setup-session'
const STEPS = ['Company & offer', 'ICP & market', 'Accounts & data', 'Pipeline & qualification', 'Integrations', 'Review']

export function SetupWizard({ credentials, token }: { credentials: Credentials; token: string }) {
  const queryClient = useQueryClient()
  const navigate = useNavigate()
  const api = commercialApi(credentials)
  const [error, setError] = useState('')
  const [busy, setBusy] = useState<string | null>(null)
  const [activeId, setActiveId] = useState<string | null>(() => localStorage.getItem(STORAGE_KEY))
  const [step, setStep] = useState(0)
  const [details, setDetails] = useState(false)
  const [showCsv, setShowCsv] = useState(false)
  const [form, setForm] = useState<Record<string, string>>({})
  const set = (k: string, v: string) => setForm(s => ({ ...s, [k]: v }))

  const sessions = useQuery({ queryKey: ['c-sessions'], queryFn: api.sessions })
  const ctxView = useQuery({ queryKey: ['company-context'], queryFn: () => companyContext(credentials) })
  const offers = useQuery({ queryKey: ['c-offers'], queryFn: api.offers })
  const icps = useQuery({ queryKey: ['c-icps'], queryFn: api.icps })
  const templates = useQuery({ queryKey: ['c-icp-templates'], queryFn: api.icpTemplates })
  const accounts = useQuery({ queryKey: ['c-accounts-wizard'], queryFn: () => api.accounts({ page_size: 1 }) })
  const pipelines = useQuery({ queryKey: ['c-pipelines'], queryFn: api.pipelines })
  const rules = useQuery({ queryKey: ['c-rules'], queryFn: api.rules })
  const integrations = useQuery({ queryKey: ['c-integrations'], queryFn: api.integrations })
  const imports = useQuery({ queryKey: ['c-imports'], queryFn: api.imports })

  const active = (sessions.data || []).find(s => s.id === activeId) || null
  useEffect(() => {
    if (active) setStep(stepFromKey(active.current_step))
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [active?.id])

  const needToken = () => {
    if (!token.trim()) { setError('Enter the founder action token at the top of the page first.'); return false }
    return true
  }
  async function write(label: string, fn: () => Promise<unknown>, keys: string[]) {
    if (!needToken()) return
    setError(''); setBusy(label)
    try { await fn(); for (const k of keys) await queryClient.invalidateQueries({ queryKey: [k] }) }
    catch (e) { setError(e instanceof Error ? e.message : `${label} failed.`) }
    finally { setBusy(null) }
  }
  async function start(path: string) {
    if (!needToken()) return
    setError(''); setBusy('Starting guided setup')
    try {
      const s = await commercialWrite(credentials, token).createSession({ path }) as { id: string }
      localStorage.setItem(STORAGE_KEY, s.id)
      setActiveId(s.id)
      setStep(0)
      await queryClient.invalidateQueries({ queryKey: ['c-sessions'] })
    } catch (e) { setError(e instanceof Error ? e.message : 'Setup could not start.') }
    finally { setBusy(null) }
  }
  function resume(id: string) {
    localStorage.setItem(STORAGE_KEY, id)
    setActiveId(id)
  }
  function leave() {
    localStorage.removeItem(STORAGE_KEY)
    setActiveId(null)
  }
  function go(index: number) {
    setStep(index)
    if (active && needTokenSilent()) {
      void commercialWrite(credentials, token).updateSession(active.id, { current_step: stepKey(index) })
        .then(() => queryClient.invalidateQueries({ queryKey: ['c-sessions'] }))
        .catch(() => undefined)
    }
  }
  function needTokenSilent() { return token.trim().length > 0 }
  function persistStep(id: string, stepKeyValue: string, progress?: Record<string, unknown>) {
    if (!needTokenSilent()) return
    setError('')
    void commercialWrite(credentials, token).updateSession(id, { current_step: stepKeyValue, ...(progress ? { progress } : {}) })
      .then(() => queryClient.invalidateQueries({ queryKey: ['c-sessions'] }))
      .catch(() => undefined)
  }

  const company = (ctxView.data?.context as { company?: { name?: string } } | undefined)?.company
  const done = {
    company: Boolean(company?.name) && (offers.data || []).length > 0,
    icp: (icps.data || []).length > 0,
    accounts: (accounts.data?.total || 0) > 0,
    pipeline: (pipelines.data || []).length > 0 && (rules.data || []).length > 0,
    integrations: true,
    review: Boolean(company?.name) && (offers.data || []).length > 0 && (icps.data || []).length > 0
      && (accounts.data?.total || 0) > 0 && (pipelines.data || []).length > 0 && (rules.data || []).length > 0,
  }

  if (!active) {
    const open = (sessions.data || []).filter(s => !s.completed)
    return <div>
      <div className="cx-cards">
        <div className="cx-card"><h3>Starting from zero</h3>
          <p>For a company establishing its commercial process for the first time. Builds the profile, hypothesis, and pipeline step by step.</p>
          <button className="button primary" disabled={busy !== null} onClick={() => void start('A')}>{busy ? 'Starting…' : 'Start setup'}</button></div>
        <div className="cx-card"><h3>Already operating</h3>
          <p>For a company with existing customers, account lists, or CRM data. Imports what exists, then suggests an ICP from the evidence.</p>
          <button className="button primary" disabled={busy !== null} onClick={() => void start('B')}>{busy ? 'Starting…' : 'Start setup'}</button></div>
      </div>
      {open.length > 0 && <div className="cx-resume"><h3>Resume where you stopped</h3>
        <ul>{open.map(s => <li key={s.id}>
          <button className="button secondary" onClick={() => resume(s.id)}>Resume path {s.path} — at {s.current_step}</button>
        </li>)}</ul></div>}
      {error && <p className="form-error" role="alert">{error}</p>}
    </div>
  }

  return <div>
    <p className="cx-note">Path {active.path === 'A' ? 'A — starting from zero' : 'B — already operating'} · progress saves automatically · <button className="cx-link" onClick={leave}>leave setup and return later</button></p>
    {(active.progress || {}).track === 'research' && <p className="cx-note">Research track: strategy work continues in the guided research flow — values carry over, nothing resets.</p>}
    <Stepper steps={STEPS} current={step} onGo={go} />
    {error && <p className="form-error" role="alert">{error}</p>}
    {step === 0 && <CompanyStep company={company} form={form} set={set} details={details} setDetails={setDetails}
      busy={busy !== null} onSave={(patch, offer) => void write('Saving company profile', async () => {
        const prev = (ctxView.data?.context || {}) as Record<string, Record<string, string>>
        await replaceCompanyContext(credentials, { ...ctxView.data?.context, company: { ...(prev.company || {}), ...patch } } as never, token)
        if (offer) await commercialWrite(credentials, token).createOffer(offer)
      }, ['company-context', 'c-offers'])} />}
    {step === 1 && <IcpStep templates={templates.data || []} busy={busy !== null}
      count={(icps.data || []).length} isB={active.path === 'B'}
      onResearchTrack={() => {
        if (active) persistStep(active.id, 'icp', { track: 'research' })
        navigate('/onboarding')
      }}
      onSave={v => void write('Saving ICP', () => commercialWrite(credentials, token).createICP(v), ['c-icps'])} />}
    {step === 2 && <div>
      <div className="cx-form">
        <Field label="Company name" hint="The minimum needed. Everything else is optional.">
          <input value={form.acct || ''} onChange={e => set('acct', e.target.value)} placeholder="e.g. Northwind Logistics" /></Field>
        <div className="modal-actions">
          <button className="button secondary" disabled={busy !== null || !(form.acct || '').trim()}
            onClick={() => void write('Saving account', () => commercialWrite(credentials, token).createAccount({ company_name: form.acct.trim() }), ['c-accounts', 'c-accounts-wizard'])}>Add account</button>
          <button className="button secondary" onClick={() => setShowCsv(true)}>Import CSV instead</button>
        </div>
      </div>
      <p className="cx-note">{accounts.data?.total || 0} account(s) saved. {active.path === 'B' && `${(imports.data || []).filter(i => i.status === 'committed').length} import(s) committed.`}</p>
      {showCsv && <CsvWizard credentials={credentials} token={token} onClose={() => setShowCsv(false)} />}
    </div>}
    {step === 3 && <div>
      <p className="cx-note">{(pipelines.data || []).length} pipeline(s) · {(rules.data || []).length} qualification rule(s). The default pipeline is created automatically the first time pipelines are listed.</p>
      <div className="cx-form">
        <Field label="Qualification rule" hint="e.g. Fit score of at least 40.">
          <input value={form.rule || ''} onChange={e => set('rule', e.target.value)} placeholder="Rule name" /></Field>
        <div className="modal-actions">
          <button className="button secondary" disabled={busy !== null || !(form.rule || '').trim()}
            onClick={() => void write('Saving rule', () => commercialWrite(credentials, token).createRule({ name: form.rule.trim(), criterion: form.rule.trim(), rule_type: 'fit', threshold: 40 }), ['c-rules'])}>Save rule</button>
        </div>
      </div>
    </div>}
    {step === 4 && <div>
      <p className="cx-note">{(integrations.data || []).filter(i => i.connection).length} connected · {(integrations.data || []).filter(i => !i.connection && i.state === 'available').length} available · the rest need external approval. Nothing here blocks the CRM, ICP, or pipeline.</p>
      <Empty title="Optional by design" detail="Connect a provider now or skip this step entirely — setup completes either way." />
    </div>}
    {step === 5 && <div>
      <ul className="cx-checklist">
        <li data-done={done.company}>Company and offer — {done.company ? 'saved' : 'missing'}</li>
        <li data-done={done.icp}>ICP hypothesis — {(icps.data || []).length} profile(s)</li>
        <li data-done={done.accounts}>Accounts — {accounts.data?.total || 0} saved</li>
        <li data-done={done.pipeline}>Pipeline and rules — {(pipelines.data || []).length} pipeline(s), {(rules.data || []).length} rule(s)</li>
      </ul>
      <div className="modal-actions">
        <button className="button primary" disabled={busy !== null || !done.review}
          onClick={() => void write('Activating', () => commercialWrite(credentials, token).updateSession(active.id, { current_step: 'review', completed: true }), ['c-sessions'])}>Activate</button>
      </div>
      {!done.review && <p className="cx-note">Activation needs a company, an offer, an ICP, an account, a pipeline, and a rule.</p>}
      {active.completed ? <p className="cx-note">This setup is active. You can keep improving it from the workspace tabs.</p> : null}
    </div>}
    <div className="cx-wizard-bar">
      <button className="button secondary" disabled={step <= 0} onClick={() => go(step - 1)}>Back</button>
      <span className="cx-note">Step {step + 1} of {STEPS.length}</span>
      {step < STEPS.length - 1
        ? <button className="button primary" onClick={() => go(step + 1)}>Continue</button>
        : <button className="button secondary" onClick={leave}>Finish later</button>}
    </div>
    {busy && <p role="status" className="cx-note">{busy}…</p>}
  </div>
}

function stepKey(index: number): string {
  return ['company', 'icp', 'accounts', 'pipeline', 'integrations', 'review'][index] || 'company'
}

function stepFromKey(key: string): number {
  const map: Record<string, number> = { company: 0, discovery: 0, icp: 1, accounts: 2, import: 2, customers: 2, pipeline: 3, rules: 3, integrations: 4, review: 5 }
  return map[key] ?? 0
}

function CompanyStep({ company, form, set, details, setDetails, busy, onSave }: {
  company?: { name?: string }
  form: Record<string, string>; set: (k: string, v: string) => void
  details: boolean; setDetails: (v: boolean) => void
  busy: boolean; onSave: (patch: Record<string, string>, offer: Record<string, unknown> | null) => void
}) {
  const [saved, setSaved] = useState(false)
  const f = (k: string) => form[`co_${k}`] || ''
  const setF = (k: string, v: string) => { set(`co_${k}`, v); setSaved(false) }
  return <div className="cx-form">
    {company?.name && <p className="cx-note">Saved: {company.name}. Editing updates only the fields you change.</p>}
    <div className="cx-grid">
      <Field label="Company name" hint="e.g. Northwind Logistics"><input value={f('name')} onChange={e => setF('name', e.target.value)} placeholder="Northwind Logistics" /></Field>
      <Field label="Website" hint="e.g. northwind.example"><input value={f('website')} onChange={e => setF('website', e.target.value)} placeholder="northwind.example" /></Field>
    </div>
    <Field label="Main product or service" hint="One line on what you sell."><input value={f('offer')} onChange={e => setF('offer', e.target.value)} placeholder="Managed dispatch desk" /></Field>
    <Field label="Offer description" hint="Who it is for and the outcome."><input value={f('odesc')} onChange={e => setF('odesc', e.target.value)} placeholder="For logistics teams drowning in spreadsheets" /></Field>
    <button className="cx-link" type="button" onClick={() => setDetails(!details)} aria-expanded={details}>{details ? 'Hide commercial details' : 'More commercial details'}</button>
    {details && <div className="cx-grid">
      <Field label="Industry"><input value={f('industry')} onChange={e => setF('industry', e.target.value)} placeholder="Logistics" /></Field>
      <Field label="Operating market"><input value={f('market')} onChange={e => setF('market', e.target.value)} placeholder="North America" /></Field>
      <Field label="Target customer"><input value={f('customer')} onChange={e => setF('customer', e.target.value)} placeholder="Dispatch managers at 20–200 person firms" /></Field>
      <Field label="Pricing" hint="Model or typical value, when known."><input value={f('pricing')} onChange={e => setF('pricing', e.target.value)} placeholder="$2k/mo retainer" /></Field>
    </div>}
    <div className="modal-actions">
      <button className="button primary" disabled={busy || (!f('name').trim() && !f('website').trim() && !f('offer').trim())}
        onClick={() => {
          const patch: Record<string, string> = {}
          if (f('name').trim()) patch.name = f('name').trim()
          if (f('website').trim()) patch.website = f('website').trim()
          const offer = f('offer').trim() ? {
            name: f('offer').trim(), description: f('odesc').trim(),
            category: f('industry').trim(), target_market: f('market').trim(),
            pricing_model: f('pricing').trim(),
          } : null
          setSaved(true)
          onSave(patch, offer)
        }}>Save draft</button>
      {saved && <span className="cx-note">Saved — only filled fields were written.</span>}
    </div>
  </div>
}

function IcpStep({ templates, busy, count, isB, onResearchTrack, onSave }: {
  templates: Array<{ key: string; name: string; criteria: unknown[]; exclusions: unknown[]; note: string }>
  busy: boolean; count: number; isB: boolean
  onResearchTrack: () => void
  onSave: (v: Record<string, unknown>) => void
}) {
  const [name, setName] = useState('')
  const [industry, setIndustry] = useState('')
  const [template, setTemplate] = useState('')
  const tpl = templates.find(t => t.key === template)
  return <div className="cx-form">
    {isB && <p className="cx-note">Already operating: start from the template closest to your best customers, then correct it with evidence.</p>}
    <div className="cx-grid">
      <Field label="ICP name"><input value={name} onChange={e => setName(e.target.value)} placeholder="e.g. Logistics SMB" /></Field>
      <Field label="Industry it matches" hint="Fill this before validating — a template is never a verified truth."><input value={industry} onChange={e => setIndustry(e.target.value)} placeholder="e.g. logistics" /></Field>
    </div>
    <Field label="Start from a template (optional)">
      <select aria-label="ICP template" value={template} onChange={e => setTemplate(e.target.value)}>
        <option value="">Blank hypothesis</option>
        {templates.map(t => <option key={t.key} value={t.key}>{t.name}</option>)}
      </select></Field>
    {tpl && <p className="cx-note">{tpl.note}</p>}
    <p className="cx-note">{count} profile(s) saved. New profiles are provisional. Need research-backed strategy first? <button className="cx-link" onClick={onResearchTrack}>Continue in the guided research flow</button> — this session keeps everything.</p>
    <div className="modal-actions">
      <button className="button primary" disabled={busy || !name.trim()}
        onClick={() => {
          const criteria = tpl ? (tpl.criteria as Array<Record<string, unknown>>).map(c =>
            c.field === 'industry' && industry.trim() ? { ...c, value: industry.trim() } : c) : [
            { field: 'industry', operator: 'contains', value: industry.trim() || name.trim(), weight: 2 }]
          onSave({ name: name.trim(), criteria, exclusions: tpl ? tpl.exclusions : [] })
          setName(''); setIndustry('')
        }}>Save provisional ICP</button>
    </div>
  </div>
}
