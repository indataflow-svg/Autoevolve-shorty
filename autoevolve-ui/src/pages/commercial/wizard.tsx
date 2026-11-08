/** One coherent guided setup. Two starting choices, one stepper, no duplicate buttons. */
import { useEffect, useState } from 'react'
import { useQuery, useQueryClient } from '@tanstack/react-query'
import { useNavigate, useSearchParams } from 'react-router-dom'
import type { Credentials } from '../../api/client'
import { commercialApi, commercialWrite } from '../../api/commercial'
import { companyContext, mergeContextSections, replaceCompanyContext } from '../../api/companyContext'
import { Empty, Field, Stepper } from './shared'
import { StateBadge } from '../../components/Primitives'
import { AnswerCards } from '../../components/CompanyDataCards'
import { CsvWizard } from './csvWizard'

const STORAGE_KEY = 'cx-setup-session'
const STEPS = ['Company & offer', 'ICP & market', 'Accounts & data', 'Pipeline & qualification', 'Integrations', 'Review']

export function SetupWizard({ credentials, token, onScores, onTab, onCompanyData }: {
  credentials: Credentials; token: string; onScores?: () => void
  onTab?: (tab: string) => void; onCompanyData?: () => void
}) {
  const queryClient = useQueryClient()
  const navigate = useNavigate()
  const api = commercialApi(credentials)
  const [error, setError] = useState('')
  const [busy, setBusy] = useState<string | null>(null)
  const [activeId, setActiveId] = useState<string | null>(() => localStorage.getItem(STORAGE_KEY))
  const [step, setStep] = useState(0)
  const [showCsv, setShowCsv] = useState(false)
  const [form, setForm] = useState<Record<string, string>>({})
  const set = (k: string, v: string) => setForm(s => ({ ...s, [k]: v }))
  const [params] = useSearchParams()
  const [showStarter, setShowStarter] = useState(() => params.get('fresh') === '1')
  const [ctxTick, setCtxTick] = useState(0)
  const [addingOffer, setAddingOffer] = useState(false)
  const [offerName, setOfferName] = useState('')
  const [offerBusy, setOfferBusy] = useState(false)

  async function saveOffer() {
    if (!offerName.trim()) return
    if (!token.trim()) { setError('Enter the founder action token at the top of the page first.'); return }
    setError(''); setOfferBusy(true)
    try {
      await commercialWrite(credentials, token).createOffer({ name: offerName.trim() })
      setOfferName(''); setAddingOffer(false)
      await queryClient.invalidateQueries({ queryKey: ['c-offers'] })
    } catch (e) { setError(e instanceof Error ? e.message : 'Offer was not saved.') }
    finally { setOfferBusy(false) }
  }

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
      setShowStarter(false)
      await queryClient.invalidateQueries({ queryKey: ['c-sessions'] })
    } catch (e) { setError(e instanceof Error ? e.message : 'Setup could not start.') }
    finally { setBusy(null) }
  }
  function resume(id: string) {
    localStorage.setItem(STORAGE_KEY, id)
    setActiveId(id)
    setShowStarter(false)
  }
  function leave() {
    localStorage.removeItem(STORAGE_KEY)
    setActiveId(null)
    setShowStarter(false)
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

  const company = (ctxView.data?.context as { company?: { name?: string; website?: string; description?: string } } | undefined)?.company
  const ctxPercent = ctxView.data?.context.completeness_percent ?? 0
  const done = {
    company: Boolean(company?.name) && (offers.data || []).length > 0,
    icp: (icps.data || []).length > 0,
    accounts: (accounts.data?.total || 0) > 0,
    pipeline: (pipelines.data || []).length > 0 && (rules.data || []).length > 0,
    integrations: true,
    review: Boolean(company?.name) && (offers.data || []).length > 0 && (icps.data || []).length > 0
      && (accounts.data?.total || 0) > 0 && (pipelines.data || []).length > 0 && (rules.data || []).length > 0,
  }
  const allSessions = sessions.data || []
  // Identity exists when any commercial fact is stored — company data started,
  // or any offer/ICP/account/pipeline/rule/session. Starter choices must not
  // reappear once this is true.
  const hasIdentity = Boolean(company?.name) || ctxPercent > 0
    || (offers.data || []).length > 0 || (icps.data || []).length > 0
    || (accounts.data?.total || 0) > 0 || (pipelines.data || []).length > 0
    || (rules.data || []).length > 0 || allSessions.length > 0

  if (!active) {
    const open = allSessions.filter(s => !s.completed)
    const lastDone = [...allSessions].reverse().find(s => s.completed)
    if (hasIdentity && !showStarter) {
      const offerNames = (offers.data || []).map(o => o.name).filter(Boolean)
      const icpNames = (icps.data || []).map(i => `${i.name}${i.status && i.status !== 'active' ? ` (${i.status})` : ''}`)
      const pipeNames = (pipelines.data || []).map(p => p.name)
      const ruleNames = (rules.data || []).map(r => r.name)
      const companyDone = Boolean(company?.name)
      const statusRows: Array<{
        label: string; detail: string; ok: boolean; action: string;
        onAction: () => void; info: string[]; quickAdd?: boolean;
      }> = [
        { label: 'Company identity', detail: companyDone ? `${company?.name}${company?.website ? ` · ${company.website}` : ''}` : `${ctxPercent}% complete`,
          ok: companyDone, action: 'Company data', onAction: () => onCompanyData?.(),
          info: [...(company?.description ? [company.description] : []),
                 ...(company?.website ? [`Website: ${company.website}`] : []),
                 ...(!companyDone ? ['Name missing — set it in Company data.'] : [])] },
        { label: 'Offers', detail: `${offerNames.length} offer(s)`, ok: offerNames.length > 0,
          action: 'Add offer', onAction: () => setAddingOffer(v => !v), quickAdd: true,
          info: offerNames.length ? offerNames.map(n => `Offer: ${n}`) : ['No offers yet — add the first below.'] },
        { label: 'ICP hypothesis', detail: `${icpNames.length} profile(s)`, ok: done.icp,
          action: 'Open ICPs', onAction: () => onTab?.('ICPs & Qualification'),
          info: icpNames.length ? icpNames.map(n => `Profile: ${n}`) : ['No profiles yet — start from a template in ICPs.'] },
        { label: 'Accounts', detail: `${accounts.data?.total || 0} saved`, ok: done.accounts,
          action: 'Open accounts', onAction: () => onTab?.('Accounts'),
          info: (accounts.data?.total || 0) > 0
            ? [`${accounts.data?.total} saved — manage, qualify, and suggest lookalikes in Accounts.`]
            : ['None saved — add one manually or import CSV in Accounts.'] },
        { label: 'Pipeline and rules', detail: `${pipeNames.length} pipeline(s), ${ruleNames.length} rule(s)`, ok: done.pipeline,
          action: 'Open pipeline', onAction: () => onTab?.('Pipeline'),
          info: [...pipeNames.map(n => `Pipeline: ${n}`), ...ruleNames.map(n => `Rule: ${n}`),
                 ...((pipeNames.length + ruleNames.length) === 0 ? ['Defaults appear automatically; add a rule in Pipeline.'] : [])] },
      ]
      const ready = ctxView.data?.context.workflow_ready
      return <div className="cx-stack">
        <div className="cx-cards">
          <div className="cx-card">
            <div className="cx-hero">
              <CompletenessRing percent={ctxPercent} />
              <div className="cx-hero-text">
                <h3>{company?.name || 'Company commercial identity'}</h3>
                {company?.description && <p>{company.description}</p>}
                <div className="cx-hero-meta">
                  {company?.website && <small>{company.website}</small>}
                  <StateBadge tone={ready ? 'green' : 'yellow'}>{ready ? 'ready' : 'needs attention'}</StateBadge>
                </div>
              </div>
            </div>
            <ul className="cx-status-rows">{statusRows.map(row => <li key={row.label}>
              <span><strong>{row.label}</strong><small>{row.detail}</small>
                <details className="cx-row-info"><summary>More info</summary>
                  <ul>{row.info.map((line, i) => <li key={i}>{line}</li>)}</ul>
                </details>
                {row.quickAdd && addingOffer && <div className="cx-row-add">
                  <input aria-label="New offer name" value={offerName}
                    onChange={e => setOfferName(e.target.value)} placeholder="e.g. Managed dispatch desk" maxLength={120} />
                  <button className="button primary cx-row-action" disabled={offerBusy || !offerName.trim()}
                    onClick={() => void saveOffer()}>{offerBusy ? 'Saving…' : 'Save offer'}</button>
                </div>}
              </span>
              <span className="cx-row-side">
                <StateBadge tone={row.ok ? 'green' : 'yellow'}>{row.ok ? 'done' : 'missing'}</StateBadge>
                <button className="button secondary cx-row-action" onClick={row.onAction}>{row.quickAdd && addingOffer ? 'Cancel' : row.action}</button>
              </span>
            </li>)}</ul>
            <div className="cx-card-actions">
              {open.length > 0 && <button className="button primary" onClick={() => resume(open[0].id)}>Resume path {open[0].path} — at {open[0].current_step}</button>}
              {open.length === 0 && lastDone && <button className="button primary" onClick={() => resume(lastDone.id)}>Review setup</button>}
              <button className="button secondary" onClick={() => setShowStarter(true)}>Setup new company commercial identity</button>
            </div>
            <PoolRow credentials={credentials} token={token} />
          </div>
        </div>
        {open.length > 1 && <div className="cx-resume"><h3>Other paused setups</h3>
          <ul>{open.slice(1).map(s => <li key={s.id}>
            <button className="button secondary" onClick={() => resume(s.id)}>Resume path {s.path} — at {s.current_step}</button>
          </li>)}</ul></div>}
        <ScoreKpis credentials={credentials} onScores={onScores} />
        <p className="cx-note">Starting a new identity keeps existing accounts, offers, and history — it opens a fresh guided setup you can leave and resume.</p>
        {error && <p className="form-error" role="alert">{error}</p>}
      </div>
    }
    return <div>
      {hasIdentity && <p className="cx-note"><button className="cx-link" onClick={() => setShowStarter(false)}>← Back to company identity</button></p>}
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
    {step === 0 && <CompanyStep view={ctxView.data} busy={busy !== null} savedTick={ctxTick}
      credentials={credentials} token={token} onSaved={() => {
        setCtxTick(tick => tick + 1)
        void queryClient.invalidateQueries({ queryKey: ['company-context'] })
        void queryClient.invalidateQueries({ queryKey: ['c-offers'] })
      }} />}
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

/** World-data predictions for the stored company data. Stat blocks first. */
export function BenchmarkCard({ credentials }: { credentials: Credentials }) {
  const [sends, setSends] = useState(100)
  const api = commercialApi(credentials)
  const bench = useQuery({ queryKey: ['c-benchmarks', sends], queryFn: () => api.benchmarks(sends) })
  const data = bench.data
  return <div className="cx-cards">
    <div className="cx-card">
      <h3>Predicted outcomes</h3>
      {bench.isPending && <p>Loading world benchmarks…</p>}
      {bench.isError && <p className="cx-note">Benchmarks are unavailable right now.</p>}
      {data && <>
        <p className="cx-note">{data.industry ? `For ${data.industry} (from ${data.industry_source}).` : 'General B2B band — no industry stored yet.'}</p>
        <div className="cx-stats">
          <div className="cx-stat"><span>Cold reply</span><strong>{data.cold.reply_low_pct}–{data.cold.reply_high_pct}%</strong></div>
          <div className="cx-stat"><span>Expected</span><strong>{data.expected.low}–{data.expected.high}</strong><small>replies / {data.expected.sends} sends</small></div>
          <div className="cx-stat"><span>Opt-in open</span><strong>{data.optin.open_low_pct}–{data.optin.open_high_pct}%</strong></div>
        </div>
        {data.market
          ? <p>Your {data.market.recorded_pct}% across {data.recorded.sent} sends — {data.market.verdict} the world band.</p>
          : <p className="cx-note">{data.recorded.sent} sends so far — 10+ position you against the market.</p>}
        <div className="cx-estimate">
          <Field label="Sends to estimate">
            <input type="number" min={1} max={100000} value={sends}
              onChange={e => setSends(Math.min(100000, Math.max(1, Math.floor(Number(e.target.value) || 1))))} />
          </Field>
        </div>
        <details className="cx-src"><summary>Sources & coverage</summary>
          {data.cold.sources.length + data.optin.sources.length} cited studies · {data.cold.vintage} · {data.cold.coverage}</details>
      </>}
    </div>
  </div>
}

/** Compact score KPIs for the Setup page. Full detail lives in Scores. */
function ScoreKpis({ credentials, onScores }: { credentials: Credentials; onScores?: () => void }) {
  const api = commercialApi(credentials)
  const bench = useQuery({ queryKey: ['c-benchmarks', 100], queryFn: () => api.benchmarks(100) })
  const data = bench.data
  if (bench.isPending || bench.isError || !data) return null
  return <div className="cx-cards"><div className="cx-card">
    <div className="cx-stats cx-stats-compact">
      <div className="cx-stat"><span>Cold reply</span><strong>{data.cold.reply_low_pct}–{data.cold.reply_high_pct}%</strong></div>
      <div className="cx-stat"><span>Expected</span><strong>{data.expected.low}–{data.expected.high}</strong><small>replies / 100 sends</small></div>
      <div className="cx-stat"><span>Opt-in open</span><strong>{data.optin.open_low_pct}–{data.optin.open_high_pct}%</strong></div>
    </div>
    <div className="cx-card-actions">
      <button className="button secondary" onClick={onScores}>See more</button>
      {data.market && <span className="operational-note">Your {data.market.recorded_pct}% — {data.market.verdict}</span>}
    </div>
  </div></div>
}

/** Pool preference lives with identity: a privacy decision, not a prediction. */
function PoolRow({ credentials, token }: { credentials: Credentials; token: string }) {
  const queryClient = useQueryClient()
  const [busy, setBusy] = useState(false)
  const [error, setError] = useState('')
  const api = commercialApi(credentials)
  const stats = useQuery({ queryKey: ['c-network-stats'], queryFn: api.networkStats })
  async function flip() {
    if (!token.trim()) { setError('Enter the founder action token at the top of the page first.'); return }
    const next = (stats.data?.contribution || 'opted_out') !== 'opted_in'
    setError(''); setBusy(true)
    try {
      await api.setContribution(next, token)
      await queryClient.invalidateQueries({ queryKey: ['c-network-stats'] })
    } catch (e) { setError(e instanceof Error ? e.message : 'Preference was not saved.') }
    finally { setBusy(false) }
  }
  const optedIn = stats.data?.contribution === 'opted_in'
  return <div className="cx-pool">
    <small>Anonymized pool: <strong>{stats.data ? (optedIn ? 'opted in' : 'opted out') : '…'}</strong> · counts only, kept on this server.</small>
    <button className="button secondary" disabled={busy || stats.isPending} onClick={() => void flip()}>
      {busy ? 'Saving…' : (optedIn ? 'Opt out' : 'Opt in')}</button>
    {error && <p className="form-error" role="alert">{error}</p>}
  </div>
}

function CompletenessRing({ percent }: { percent: number }) {
  const r = 26
  const circle = 2 * Math.PI * r
  const done = Math.min(100, Math.max(0, percent)) / 100
  return <svg className="cx-ring" width="72" height="72" viewBox="0 0 72 72" role="img" aria-label={`${percent}% complete`}>
    <circle cx="36" cy="36" r={r} fill="none" stroke="var(--border)" strokeWidth="7" />
    <circle cx="36" cy="36" r={r} fill="none" stroke={percent >= 80 ? 'var(--success)' : 'var(--primary)'} strokeWidth="7" strokeLinecap="round" strokeDasharray={`${circle * done} ${circle}`} transform="rotate(-90 36 36)" />
    <text x="36" y="36" textAnchor="middle" dominantBaseline="central" fill="var(--text)" fontSize="15" fontWeight="700">{percent}%</text>
  </svg>
}

function stepKey(index: number): string {  return ['company', 'icp', 'accounts', 'pipeline', 'integrations', 'review'][index] || 'company'
}

function stepFromKey(key: string): number {
  const map: Record<string, number> = { company: 0, discovery: 0, icp: 1, accounts: 2, import: 2, customers: 2, pipeline: 3, rules: 3, integrations: 4, review: 5 }
  return map[key] ?? 0
}

function CompanyStep({ view, busy, savedTick, credentials, token, onSaved }: {
  view: { context: unknown } | undefined
  busy: boolean
  savedTick: number
  credentials: Credentials
  token: string
  onSaved: () => void
}) {
  const [name, setName] = useState('')
  const [website, setWebsite] = useState('')
  const [offer, setOffer] = useState({ name: '', description: '', category: '', market: '', pricing: '' })
  const [details, setDetails] = useState(false)
  const [error, setError] = useState('')
  const [saving, setSaving] = useState<'context' | 'offer' | null>(null)
  const [savedWhat, setSavedWhat] = useState('')

  async function saveContext(touched: Record<string, Record<string, string>>) {
    if (!token.trim()) { setError('Enter the founder action token at the top of the page first.'); return }
    // Identity fields ride the same save so company data is written once.
    const withIdentity = { ...touched }
    const identity: Record<string, string> = {}
    if (name.trim()) identity.name = name.trim()
    if (website.trim()) identity.website = website.trim()
    if (Object.keys(identity).length) withIdentity.company = { ...withIdentity.company, ...identity }
    setError(''); setSaving('context')
    try {
      // Fresh fetch before the full-replacement PUT: the cached view may
      // predate saves made on other pages.
      const fresh = await companyContext(credentials)
      await replaceCompanyContext(credentials, mergeContextSections(
        fresh.context as unknown as Record<string, unknown>, withIdentity), token)
      setName(''); setWebsite('')
      setSavedWhat('Company data saved — only filled fields were written.')
      onSaved()
    } catch (e) { setError(e instanceof Error ? e.message : 'Company data was not saved.') }
    finally { setSaving(null) }
  }

  async function saveOffer() {
    if (!offer.name.trim()) { setError('Give the offer a name.'); return }
    if (!token.trim()) { setError('Enter the founder action token at the top of the page first.'); return }
    setError(''); setSaving('offer')
    try {
      await commercialWrite(credentials, token).createOffer({
        name: offer.name.trim(), description: offer.description.trim(),
        category: offer.category.trim(), target_market: offer.market.trim(),
        pricing_model: offer.pricing.trim(),
      })
      setOffer({ name: '', description: '', category: '', market: '', pricing: '' })
      setSavedWhat('Offer saved.')
      onSaved()
    } catch (e) { setError(e instanceof Error ? e.message : 'Offer was not saved.') }
    finally { setSaving(null) }
  }

  const setO = (k: keyof typeof offer, v: string) => { setOffer(o => ({ ...o, [k]: v })); setSavedWhat('') }
  return <div>
    <div className="cx-form">
      <div className="cx-grid">
        <Field label="Company name" hint="e.g. Northwind Logistics"><input value={name} onChange={e => { setName(e.target.value); setSavedWhat('') }} placeholder="Northwind Logistics" /></Field>
        <Field label="Website" hint="e.g. northwind.example"><input value={website} onChange={e => { setWebsite(e.target.value); setSavedWhat('') }} placeholder="northwind.example" /></Field>
      </div>
    </div>
    {view
      ? <AnswerCards view={view as never} busy={busy || saving !== null} savedTick={savedTick} saveLabel="Save company data" onSave={touched => void saveContext(touched)} />
      : <p className="cx-note">Loading company data…</p>}
    <div className="cx-form">
      <Field label="Offer name" hint="A separate offer record; saved on its own."><input value={offer.name} onChange={e => setO('name', e.target.value)} placeholder="Managed dispatch desk" /></Field>
      <Field label="Offer description" hint="Who it is for and the outcome."><input value={offer.description} onChange={e => setO('description', e.target.value)} placeholder="For logistics teams drowning in spreadsheets" /></Field>
      <button className="cx-link" type="button" onClick={() => setDetails(d => !d)} aria-expanded={details}>{details ? 'Hide offer details' : 'More offer details'}</button>
      {details && <div className="cx-grid">
        <Field label="Category"><input value={offer.category} onChange={e => setO('category', e.target.value)} placeholder="Logistics" /></Field>
        <Field label="Target market"><input value={offer.market} onChange={e => setO('market', e.target.value)} placeholder="North America" /></Field>
        <Field label="Pricing" hint="Model or typical value, when known."><input value={offer.pricing} onChange={e => setO('pricing', e.target.value)} placeholder="$2k/mo retainer" /></Field>
      </div>}
      <div className="modal-actions">
        <button className="button secondary" disabled={busy || saving !== null || !offer.name.trim()} onClick={() => void saveOffer()}>{saving === 'offer' ? 'Saving…' : 'Save offer'}</button>
        {savedWhat && <span className="cx-note">{savedWhat}</span>}
      </div>
    </div>
    {error && <p className="form-error" role="alert">{error}</p>}
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
