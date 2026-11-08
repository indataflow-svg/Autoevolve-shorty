import { useEffect, useRef, useState, type FormEvent, type ReactNode } from 'react'
import { useQuery, useQueryClient } from '@tanstack/react-query'
import {
  ArrowLeft, ArrowRight, Building2, Check, CheckCircle2, LockKeyhole,
  Package, Sparkles, Target, Users,
} from 'lucide-react'
import { Link } from 'react-router-dom'

import { companyContext, MARKETING_STAGES, type MarketingStage } from '../api/companyContext'
import { saveCompanyContextAnswers } from '../components/CompanyDataCards'
import { useAuthSession, useCredentials, usePlan } from '../app/Auth'
import { marketingUrl } from '../app/marketing'
import { AppShell } from '../components/Shell'
import { DataState } from '../components/Primitives'

const STEPS = [
  {
    label: 'Company', title: 'Company identity', icon: Building2,
    detail: 'The company a buyer would recognise, in your own words.',
  },
  {
    label: 'Offer', title: 'What you sell', icon: Package,
    detail: 'Describe the offer without turning it into a claim you cannot support.',
  },
  {
    label: 'Customer', title: 'Who buys and why', icon: Users,
    detail: 'Name the buyer and the problem they pay you to remove.',
  },
  {
    label: 'Objective', title: 'Your first objective', icon: Target,
    detail: 'Decide what this workspace should prove before it proposes a plan.',
  },
] as const

type FormState = {
  companyName: string
  website: string
  description: string
  productName: string
  productDescription: string
  idealCustomer: string
  problem: string
  objective: string
  marketingStage: MarketingStage
}

const EMPTY: FormState = {
  companyName: '', website: '', description: '',
  productName: '', productDescription: '',
  idealCustomer: '', problem: '', objective: '',
  marketingStage: 'starting_from_zero',
}

function value(context: unknown, section: string, key: string): string {
  const sections = context as Record<string, Record<string, unknown>> | undefined
  const answer = sections?.[section]?.[key]
  return typeof answer === 'string' ? answer : ''
}

function missing(context: unknown): string[] {
  const list = (context as { missing?: unknown } | undefined)?.missing
  return Array.isArray(list) ? list.filter((item): item is string => typeof item === 'string') : []
}

function firstIncompleteStep(context: unknown): number {
  const absent = missing(context)
  if (absent.includes('company')) return 0
  if (absent.includes('product')) return 1
  if (absent.includes('customer') || absent.includes('problem')) return 2
  if (absent.includes('objective') || absent.includes('marketing_stage')) return 3
  return 3
}

export function OnboardingPage() {
  const credentials = useCredentials()
  const session = useAuthSession()
  const plan = usePlan()
  const queryClient = useQueryClient()
  const query = useQuery({ queryKey: ['company-context'], queryFn: () => companyContext(credentials) })
  const [form, setForm] = useState<FormState>(EMPTY)
  const [step, setStep] = useState(0)
  const [completed, setCompleted] = useState(false)
  const [token, setToken] = useState('')
  const [pending, setPending] = useState(false)
  const [error, setError] = useState('')
  const seeded = useRef(false)

  useEffect(() => {
    const context = query.data?.context
    if (!context || seeded.current) return
    seeded.current = true
    setForm({
      companyName: value(context, 'company', 'name'),
      website: value(context, 'company', 'website'),
      description: value(context, 'company', 'description'),
      productName: value(context, 'product', 'name'),
      productDescription: value(context, 'product', 'description'),
      idealCustomer: value(context, 'customer', 'ideal_customer'),
      problem: value(context, 'market', 'problem'),
      objective: value(context, 'objective', 'primary_goal') || value(context, 'objective', 'desired_outcome'),
      marketingStage: (value(context, 'state', 'marketing_stage') || 'starting_from_zero') as MarketingStage,
    })
    setStep(firstIncompleteStep(context))
    setCompleted(Boolean(context.workflow_ready))
  }, [query.data])

  const setField = <K extends keyof FormState>(key: K, next: FormState[K]) => {
    setForm(current => ({ ...current, [key]: next }))
    if (error) setError('')
  }

  function validation(stepIndex: number): string | null {
    if (stepIndex === 0) {
      if (form.companyName.trim().length < 2) return 'Add the company name a buyer would recognise.'
      if (form.description.trim().length < 10) return 'Describe the company in at least 10 characters.'
      if (form.website.trim() && form.website.trim().length < 4) return 'Enter a usable website or leave it blank.'
    }
    if (stepIndex === 1) {
      if (form.productName.trim().length < 2) return 'Name the product or offer.'
      if (form.productDescription.trim().length < 10) return 'Describe what the offer does in at least 10 characters.'
    }
    if (stepIndex === 2) {
      if (form.idealCustomer.trim().length < 10) return 'Describe the buyer in at least 10 characters.'
      if (form.problem.trim().length < 10) return 'Describe the problem in at least 10 characters.'
    }
    if (stepIndex === 3) {
      if (form.objective.trim().length < 3) return 'State the outcome this workspace should prove.'
      if (!form.marketingStage) return 'Choose a starting state.'
    }
    if (!session && !token.trim()) return 'Enter the founder action token before saving.'
    return null
  }

  function touched(stepIndex: number): Record<string, Record<string, string>> {
    if (stepIndex === 0) return { company: { name: form.companyName.trim(), website: form.website.trim(), description: form.description.trim() } }
    if (stepIndex === 1) return { product: { name: form.productName.trim(), description: form.productDescription.trim() } }
    if (stepIndex === 2) return { customer: { ideal_customer: form.idealCustomer.trim() }, market: { problem: form.problem.trim() } }
    return { objective: { primary_goal: form.objective.trim() }, state: { marketing_stage: form.marketingStage } }
  }

  async function next(event: FormEvent<HTMLFormElement>) {
    event.preventDefault()
    const problem = validation(step)
    if (problem) { setError(problem); return }
    setError('')
    setPending(true)
    try {
      const updated = await saveCompanyContextAnswers(credentials, token, touched(step))
      queryClient.setQueryData(['company-context'], updated)
      if (step < STEPS.length - 1) {
        setStep(current => current + 1)
      } else if (updated.context.workflow_ready) {
        setCompleted(true)
      } else {
        setError(`Still unknown: ${(updated.context.missing || []).join(', ')}. Check the answers above.`)
      }
    } catch (reason) {
      setError(reason instanceof Error ? reason.message : 'Those answers were not saved.')
    } finally {
      setPending(false)
    }
  }

  if (query.isPending) return <OnboardingShell><div className="gs-card gs-loading">Reading your company setup…</div></OnboardingShell>
  if (query.isError && !query.data) return <OnboardingShell><DataState title="Setup could not be loaded" detail={query.error.message} retry={() => query.refetch()} /></OnboardingShell>

  const context = query.data?.context
  if (completed || context?.workflow_ready) {
    return <Handoff companyName={form.companyName || value(context, 'company', 'name')} plan={plan} />
  }

  const current = STEPS[step]
  const Icon = current.icon
  return <OnboardingShell>
    <div className="gs-page-head">
      <p className="gs-eyebrow"><Sparkles size={13} /> GET STARTED</p>
      <h1>Set the company context.</h1>
      <p>Four short cards. AutoEvolve will not invent an answer you leave blank.</p>
    </div>
    {!session && <label className="gs-token">Founder action token
      <input type="password" autoComplete="off" aria-label="Founder action token" value={token} onChange={event => setToken(event.target.value)} />
      <small>Required for operator changes; held only in this page.</small>
    </label>}
    <div className="gs-progress" aria-label={`Step ${step + 1} of ${STEPS.length}`}>
      <div className="gs-progress-bars">{STEPS.map((item, index) => <span key={item.label} data-state={index < step ? 'done' : index === step ? 'active' : 'todo'} />)}</div>
      <span>Step {step + 1} of {STEPS.length} · {current.label}</span>
    </div>
    <section className="gs-card">
      <div className="gs-card-head">
        <span className="gs-card-icon"><Icon size={20} /></span>
        <div><p className="gs-card-kicker">STEP {step + 1}</p><h2>{current.title}</h2><p>{current.detail}</p></div>
      </div>
      <form className="gs-form" onSubmit={next}>
        {step === 0 && <>
          <label className="gs-field"><span>Company name <em>Required</em></span><input autoFocus value={form.companyName} onChange={event => setField('companyName', event.target.value)} maxLength={120} placeholder="e.g. Northwind Logistics" /></label>
          <label className="gs-field"><span>Website <em>Optional</em></span><input value={form.website} onChange={event => setField('website', event.target.value)} maxLength={253} inputMode="url" placeholder="https://your-company.example" /><small>Web research uses this first when it is available.</small></label>
          <label className="gs-field"><span>What does your company do? <em>Required</em></span><textarea value={form.description} onChange={event => setField('description', event.target.value)} minLength={10} maxLength={3000} rows={4} placeholder="A dispatch desk for freight teams that replaces spreadsheet handoffs." /></label>
        </>}
        {step === 1 && <>
          <label className="gs-field"><span>Product or offer name <em>Required</em></span><input autoFocus value={form.productName} onChange={event => setField('productName', event.target.value)} maxLength={160} placeholder="e.g. Managed dispatch audit" /></label>
          <label className="gs-field"><span>What does the offer do? <em>Required</em></span><textarea value={form.productDescription} onChange={event => setField('productDescription', event.target.value)} minLength={10} maxLength={3000} rows={4} placeholder="A two-week audit that maps handoffs and fixes the first bottlenecks." /></label>
        </>}
        {step === 2 && <>
          <label className="gs-field"><span>Who is your ideal customer? <em>Required</em></span><textarea autoFocus value={form.idealCustomer} onChange={event => setField('idealCustomer', event.target.value)} minLength={10} maxLength={2000} rows={4} placeholder="Operations managers at 20–200 person freight companies." /></label>
          <label className="gs-field"><span>What problem do they pay to remove? <em>Required</em></span><textarea value={form.problem} onChange={event => setField('problem', event.target.value)} minLength={10} maxLength={2000} rows={4} placeholder="Loads are found late because every handoff lives in a spreadsheet." /></label>
        </>}
        {step === 3 && <>
          <label className="gs-field"><span>What should this workspace prove first? <em>Required</em></span><textarea autoFocus value={form.objective} onChange={event => setField('objective', event.target.value)} minLength={3} maxLength={300} rows={3} placeholder="e.g. five qualified discovery calls in two weeks" /></label>
          <label className="gs-field"><span>Where are you starting from? <em>Required</em></span><select value={form.marketingStage} onChange={event => setField('marketingStage', event.target.value as MarketingStage)}>{MARKETING_STAGES.map(option => <option key={option.value} value={option.value}>{option.label}</option>)}</select><small>This determines the first workflow route.</small></label>
        </>}
        {error && <div className="gs-error" role="alert">{error}</div>}
        <div className="gs-actions">
          <button type="button" className="button secondary" disabled={step === 0 || pending} onClick={() => { setError(''); setStep(value => Math.max(0, value - 1)) }}><ArrowLeft size={15} /> Back</button>
          <button className="button primary" disabled={pending}>{pending ? 'Saving…' : step === STEPS.length - 1 ? 'Finish setup' : 'Next'}<ArrowRight size={15} /></button>
        </div>
      </form>
    </section>
    <p className="gs-footnote">Answers are saved to this organization. Nothing is sent or published from this page.</p>
  </OnboardingShell>
}

function OnboardingShell({ children }: { children: ReactNode }) {
  return <AppShell active="Onboarding" query="" onQueryChange={() => undefined}>
    <div className="page-layout"><main className="page-main"><div className="page-content gs-page">{children}</div></main></div>
  </AppShell>
}

function Handoff({ companyName, plan }: { companyName: string; plan: 'free' | 'paid' }) {
  const free = plan === 'free'
  return <OnboardingShell>
    <div className="gs-handoff">
      <div className="gs-handoff-head">
        <p className="gs-eyebrow"><CheckCircle2 size={14} /> SETUP COMPLETE</p>
        <h1>{companyName || 'Your company'} is ready.</h1>
        <p>Choose the workspace you want to open next.</p>
      </div>
      <div className="gs-handoff-grid">
        <article className="gs-handoff-card gs-handoff-free">
          <span className="gs-handoff-icon"><CheckCircle2 size={22} /></span>
          <p className="gs-handoff-label">Included in free</p>
          <h2>Your daily loop</h2>
          <p>Turn today’s context into one plan, one simulation, and one real publish.</p>
          <ul><li><Check size={14} /> One plan and one run per day</li><li><Check size={14} /> One publish through your webhook</li><li><Check size={14} /> Thirty days of loop history</li></ul>
          <Link to="/workflows" className="button primary">Open Workflows <ArrowRight size={16} /></Link>
        </article>
        <article className={`gs-handoff-card ${free ? 'gs-handoff-locked' : 'gs-handoff-paid'}`}>
          {free && <div className="gs-handoff-preview" aria-hidden="true">
            <div><span>Qualified accounts</span><strong>12</strong></div><div><span>Pipeline</span><strong>4 stages</strong></div>
            <i /><i /><i />
          </div>}
          <div className="gs-handoff-lock">
            <span className="gs-handoff-icon">{free ? <LockKeyhole size={21} /> : <Sparkles size={21} />}</span>
            <p className="gs-handoff-label">{free ? 'Paid workspace' : 'Available in your workspace'}</p>
            <h2>Commercial outreach</h2>
            <p>Accounts, ICPs, pipeline, replies, meetings, and real cold outreach.</p>
            {free
              ? <a className="button secondary" href={marketingUrl()} target="_blank" rel="noreferrer">Upgrade <ArrowRight size={16} /></a>
              : <Link to="/commercial" className="button secondary">Open Commercial <ArrowRight size={16} /></Link>}
          </div>
        </article>
      </div>
    </div>
  </OnboardingShell>
}
