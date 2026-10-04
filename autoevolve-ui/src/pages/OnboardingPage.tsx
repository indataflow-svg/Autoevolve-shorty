import { useEffect, useMemo, useState, type FormEvent, type ReactNode } from 'react'
import { useQuery, useQueryClient } from '@tanstack/react-query'
import { ArrowRight, CheckCircle2, RefreshCw, ShieldCheck } from 'lucide-react'
import { Link, useNavigate } from 'react-router-dom'
import { companyDetail } from '../api/companies'
import { companyContext, MARKETING_STAGES, type MarketingStage } from '../api/companyContext'
import {
  activateProgram, confirmCompany, confirmStrategy, createFirstDraft, decideRefinement,
  onboardingView, recordCalibration, researchOwnCompany, resolveBuyer, searchFirstCompanies, suggestStrategy,
  startCompany, type CompanyConfirm, type OnboardingView, type StrategyInput,
} from '../api/onboarding'
import { useCredentials } from '../app/Auth'
import { AppShell } from '../components/Shell'
import { DataState, LoadingRows, StateBadge } from '../components/Primitives'

type Program = NonNullable<OnboardingView['program']>
type Candidate = OnboardingView['sample'][number]
type Run = (label: string, action: () => Promise<OnboardingView>) => Promise<void>
const lines = (value: string) => value.split(/\n|,/).map(item => item.trim()).filter(Boolean)
const asLines = (value: string[] | undefined) => (value || []).join('\n')
const fact = (record: Record<string, unknown> | null | undefined, key: string) => typeof record?.[key] === 'string' ? String(record[key]) : ''
const strategyEditKey = (id: string) => `onboarding-strategy-edit:${id}`
function storedStrategy(id: string): StrategyInput | null {
  try {
    const raw = sessionStorage.getItem(strategyEditKey(id))
    return raw ? JSON.parse(raw) as StrategyInput : null
  } catch { return null }
}

function Section({ title, detail, children }: { title: string; detail: string; children: ReactNode }) {
  return <section className="onboarding-panel"><div className="onboarding-panel-head"><h2>{title}</h2><p>{detail}</p></div>{children}</section>
}

function CompanyStartForm({ program, run, token }: { program: Program | null; run: Run; token: string }) {
  const credentials = useCredentials()
  const [name, setName] = useState(program?.company.name || '')
  const [website, setWebsite] = useState(program?.company.website || '')
  const [objective, setObjective] = useState(program?.company.objective || '')
  const [market, setMarket] = useState(program?.company.market || '')
  function submit(event: FormEvent<HTMLFormElement>) { event.preventDefault(); void run('save company', () => startCompany(credentials, { name, website, objective, market }, token)) }
  return <Section title="1. Your company" detail="These are your own company facts, separate from prospect companies."><form className="onboarding-form" onSubmit={submit}>
    <label>Company name<input value={name} onChange={event => setName(event.target.value)} minLength={2} maxLength={120} required /></label>
    <label>Website<input type="url" value={website} onChange={event => setWebsite(event.target.value)} placeholder="https://your-company.example" required /></label>
    <label>Objective<textarea value={objective} onChange={event => setObjective(event.target.value)} minLength={3} maxLength={300} required /></label>
    <label>Primary market<input value={market} onChange={event => setMarket(event.target.value)} minLength={2} maxLength={120} required /></label>
    <button className="button primary">Save and continue <ArrowRight size={16} /></button>
  </form></Section>
}

type ConfirmExtras = Pick<CompanyConfirm,
  'geography' | 'product_name' | 'product_description' | 'product_category' | 'ideal_customer'
  | 'company_sizes' | 'customer_geography' | 'buyer_roles' | 'segment' | 'problem' | 'urgency'
  | 'alternatives' | 'existing_customers' | 'existing_demand' | 'previous_marketing' | 'testimonials'
  | 'traction' | 'other_evidence' | 'pricing' | 'business_model' | 'channels' | 'assets' | 'team'
  | 'budget' | 'geographic_constraints' | 'brand_constraints' | 'budget_constraints'
  | 'regulatory_constraints' | 'operational_constraints' | 'desired_outcome'>

const emptyExtras: ConfirmExtras = {
  geography: '', product_name: '', product_description: '', product_category: '', ideal_customer: '',
  company_sizes: [], customer_geography: [], buyer_roles: [], segment: '', problem: '', urgency: '',
  alternatives: [], existing_customers: [], existing_demand: [], previous_marketing: [], testimonials: [],
  traction: [], other_evidence: [], pricing: '', business_model: '', channels: [], assets: [], team: [],
  budget: '', geographic_constraints: [], brand_constraints: [], budget_constraints: [],
  regulatory_constraints: [], operational_constraints: [], desired_outcome: '',
}
const listKeys = ['company_sizes', 'customer_geography', 'buyer_roles', 'alternatives', 'existing_customers', 'existing_demand', 'previous_marketing', 'testimonials', 'traction', 'other_evidence', 'channels', 'assets', 'team', 'geographic_constraints', 'brand_constraints', 'budget_constraints', 'regulatory_constraints', 'operational_constraints'] as const
type ListKey = (typeof listKeys)[number]

function savedExtras(program: Program): ConfirmExtras {
  const confirmed = program.company_context as Partial<ConfirmExtras> | null | undefined
  if (!confirmed) return emptyExtras
  return { ...emptyExtras, ...Object.fromEntries(
    Object.entries(confirmed).map(([key, value]) => [key, value ?? (listKeys.includes(key as ListKey) ? [] : '')]),
  ) as Partial<ConfirmExtras> }
}

function CompanyConfirmForm({ program, run, token, onEditCompany }: { program: Program; run: Run; token: string; onEditCompany: () => void }) {
  const credentials = useCredentials()
  const research = program.company_research as Record<string, unknown> | null
  const sources = Array.isArray(research?.sources) ? research.sources.filter((item): item is { field: string; url: string } => !!item && typeof item === 'object' && typeof item.url === 'string' && typeof item.field === 'string') : []
  const signals = research?.signals && typeof research.signals === 'object' ? research.signals as Record<string, unknown> : null
  const [name, setName] = useState(program.company_context?.name || fact(research, 'name') || program.company.name)
  const website = program.company.website
  const [description, setDescription] = useState(program.company_context?.description || fact(research, 'description'))
  const [industry, setIndustry] = useState(program.company_context?.industry || fact(research, 'industry'))
  const [positioning, setPositioning] = useState(program.company_context?.positioning || fact(signals, 'summary_line'))
  const [offerSummary, setOfferSummary] = useState(program.company_context?.offer_summary || (Array.isArray(research?.specialties) ? research.specialties.filter((item): item is string => typeof item === 'string').join(', ') : ''))
  // Optional answers. Anything left blank is stored as unknown, never guessed.
  const [extras, setExtras] = useState<ConfirmExtras>(() => savedExtras(program))
  const [stage, setStage] = useState<MarketingStage>(program.company_context?.marketing_stage || 'starting_from_zero')
  const setExtra = <K extends keyof ConfirmExtras>(key: K, value: ConfirmExtras[K]) => setExtras(current => ({ ...current, [key]: value }))
  function submit(event: FormEvent<HTMLFormElement>) {
    event.preventDefault()
    void run('confirm company', () => confirmCompany(credentials, {
      name, website, description, industry, positioning, offer_summary: offerSummary,
      marketing_stage: stage, ...extras,
    } satisfies CompanyConfirm, token))
  }
  const text = (label: string, key: keyof ConfirmExtras, hint?: string) => <label>{label}<input value={String(extras[key] ?? '')} onChange={event => setExtra(key, event.target.value as never)} placeholder={hint} /></label>
  const area = (label: string, key: keyof ConfirmExtras, hint?: string) => <label>{label}<textarea value={String(extras[key] ?? '')} onChange={event => setExtra(key, event.target.value as never)} placeholder={hint} /></label>
  const perLine = (label: string, key: ListKey, hint?: string) => <label>{label} · one per line<textarea value={asLines(extras[key] as string[])} onChange={event => setExtra(key, lines(event.target.value) as never)} placeholder={hint} /></label>
  return <Section title="2. Research and confirm your company" detail="Research checks your website first, then configured data providers. Check and edit every fact before it becomes strategy context.">
    <div className="onboarding-inline-actions"><button className="button secondary" onClick={() => void run('research company', () => researchOwnCompany(credentials, token))}><RefreshCw size={15} />{research ? 'Refresh company research' : 'Research website'}</button><button className="button secondary" onClick={onEditCompany}>Change company or website</button><span>{research ? `Source: ${program.research_provider?.replaceAll('+', ' + ')}` : 'No inferred facts saved. You may enter verified facts manually.'}</span></div>
    {sources.length > 0 && <p className="operational-note">Website evidence: {sources.map((source, index) => <span key={`${source.url}-${index}`}>{index > 0 ? ', ' : ''}<a href={source.url} target="_blank" rel="noopener noreferrer">{source.field}</a></span>)}</p>}
    {program.research_error && <p className="operational-error" role="alert">Company research: {program.research_error}</p>}
    <form className="onboarding-form" onSubmit={submit}>
      <label>Confirmed name<input value={name} onChange={event => setName(event.target.value)} minLength={2} maxLength={120} required /></label>
      <label>Website researched<input type="url" value={website} readOnly /></label>
      <label>Description<textarea value={description} onChange={event => setDescription(event.target.value)} minLength={10} maxLength={3000} required /></label>
      <label>Industry<input value={industry} onChange={event => setIndustry(event.target.value)} minLength={2} maxLength={120} required /></label>
      <label>Positioning<textarea value={positioning} onChange={event => setPositioning(event.target.value)} minLength={5} maxLength={1000} required /></label>
      <label>Offer summary<textarea value={offerSummary} onChange={event => setOfferSummary(event.target.value)} minLength={5} maxLength={1000} required /></label>
      <fieldset className="onboarding-choice"><legend>Where are you starting from?</legend>{MARKETING_STAGES.map(option => <label key={option.value}><input type="radio" name="marketing-stage" checked={stage === option.value} onChange={() => setStage(option.value)} />{option.label}</label>)}</fieldset>
      <p className="operational-note">Your primary goal from step 1 is already saved: <strong>{program.company.objective}</strong>. Anything you leave blank stays unknown.</p>
      <details className="onboarding-extra"><summary>More about your business <small>optional · leave anything blank you do not know yet</small></summary>
        <fieldset className="onboarding-questions"><legend>What are you selling?</legend>{text('Product or service', 'product_name', 'e.g. Managed operations audit')}{area('What it does', 'product_description')}{text('Category', 'product_category', 'e.g. Operations software')}</fieldset>
        <fieldset className="onboarding-questions"><legend>Who is it for?</legend>{area('Ideal customer', 'ideal_customer', 'Who you sell to, in plain words')}{perLine('Company sizes', 'company_sizes')}{perLine('Customer geography', 'customer_geography')}{perLine('Likely buyer', 'buyer_roles', 'e.g. Operations Director')}</fieldset>
        <fieldset className="onboarding-questions"><legend>What problem does it solve?</legend>{area('Problem', 'problem', 'The pain you remove')}{area('Why it matters', 'urgency')}{perLine('Alternatives or competitors', 'alternatives', 'Only if you know them')}</fieldset>
        <fieldset className="onboarding-questions"><legend>What do you already have?</legend>{perLine('Customers', 'existing_customers')}{perLine('Demand', 'existing_demand', 'Inbound interest, waitlist, pilots')}{perLine('Previous marketing or sales', 'previous_marketing')}{perLine('Testimonials', 'testimonials')}{perLine('Traction', 'traction', 'Revenue, growth, usage numbers')}{perLine('Other evidence', 'other_evidence')}</fieldset>
        <fieldset className="onboarding-questions"><legend>How do you charge?</legend>{text('Pricing', 'pricing', 'e.g. $2k per month')}{text('Business model', 'business_model', 'e.g. subscription, project')}</fieldset>
        <fieldset className="onboarding-questions"><legend>What can you use?</legend>{perLine('Channels', 'channels', 'e.g. Email, LinkedIn')}{perLine('Marketing assets', 'assets')}{perLine('Team', 'team')}{text('Budget', 'budget', 'If relevant')}</fieldset>
        <fieldset className="onboarding-questions"><legend>Limits to respect</legend>{perLine('Geographic limits', 'geographic_constraints')}{perLine('Brand limits', 'brand_constraints')}{perLine('Budget limits', 'budget_constraints')}{perLine('Regulatory limits', 'regulatory_constraints')}{perLine('Operational limits', 'operational_constraints')}</fieldset>
        <fieldset className="onboarding-questions"><legend>Business and goal</legend>{text('Company geography', 'geography')}{text('Target market', 'segment')}{area('Desired outcome', 'desired_outcome', 'e.g. first customers, qualified leads, booked meetings')}</fieldset>
      </details>
      <button className="button primary">Confirm company context <ArrowRight size={16} /></button>
    </form>
  </Section>
}

function StrategyForm({ program, run, token }: { program: Program; run: Run; token: string }) {
  const credentials = useCredentials()
  const saved = storedStrategy(program.id) || program.strategy_draft!
  const [name, setName] = useState(saved.name)
  const [objective, setObjective] = useState(saved.objective)
  const [metric, setMetric] = useState(saved.success_metric)
  const [offers, setOffers] = useState(asLines(saved?.offers))
  const [industry, setIndustry] = useState(saved.icp.industry)
  const [icp, setIcp] = useState(saved.icp.description)
  const [sizes, setSizes] = useState(asLines(saved?.icp.company_sizes))
  const [buyers, setBuyers] = useState(asLines(saved?.buyer_titles))
  const [markets, setMarkets] = useState(asLines(saved?.markets))
  const [signals, setSignals] = useState(asLines(saved?.positive_signals))
  const [exclusions, setExclusions] = useState(asLines(saved?.exclusions))
  const [tone, setTone] = useState(saved.tone)
  const [claims, setClaims] = useState(asLines(saved?.approved_claims))
  const [forbidden, setForbidden] = useState(asLines(saved?.prohibited_claims))
  const [channels, setChannels] = useState<Array<'email' | 'linkedin' | 'social'>>(saved.channels)
  const value = useMemo<StrategyInput>(() => ({ name, objective, success_metric: metric, offers: lines(offers), icp: { industry, description: icp, company_sizes: lines(sizes) }, buyer_titles: lines(buyers), markets: lines(markets), positive_signals: lines(signals), exclusions: lines(exclusions), tone, approved_claims: lines(claims), prohibited_claims: lines(forbidden), channels }), [name, objective, metric, offers, industry, icp, sizes, buyers, markets, signals, exclusions, tone, claims, forbidden, channels])
  useEffect(() => {
    sessionStorage.setItem(strategyEditKey(program.id), JSON.stringify(value))
  }, [program.id, value])
  function submit(event: FormEvent<HTMLFormElement>) {
    event.preventDefault()
    void run('save strategy', () => confirmStrategy(credentials, value, token))
  }
  return <Section title="3. Define your first program" detail="AI drafted every field from your confirmed company context. Review and edit the targeting suggestions and claims before saving."><form className="onboarding-form" onSubmit={submit}>
    <div className="onboarding-grid"><label>Program name<input value={name} onChange={event => setName(event.target.value)} required /></label><label>Success metric<input value={metric} onChange={event => setMetric(event.target.value)} placeholder="e.g. qualified replies per month" minLength={3} required /></label></div>
    <label>Objective<textarea value={objective} onChange={event => setObjective(event.target.value)} minLength={3} required /></label>
    <label>Offers · one per line<textarea value={offers} onChange={event => setOffers(event.target.value)} required /></label>
    <div className="onboarding-grid"><label>ICP industry<input value={industry} onChange={event => setIndustry(event.target.value)} minLength={2} required /></label><label>Company sizes · one per line<textarea value={sizes} onChange={event => setSizes(event.target.value)} /></label></div>
    <label>Ideal customer profile<textarea value={icp} onChange={event => setIcp(event.target.value)} minLength={10} required /></label>
    <div className="onboarding-grid"><label>Buyer titles · one per line<textarea value={buyers} onChange={event => setBuyers(event.target.value)} required /></label><label>Markets · one per line<textarea value={markets} onChange={event => setMarkets(event.target.value)} required /></label></div>
    <label>Positive signals · one per line<textarea value={signals} onChange={event => setSignals(event.target.value)} required /></label>
    <label>Exclusions · one per line<textarea value={exclusions} onChange={event => setExclusions(event.target.value)} /></label>
    <label>Tone<input value={tone} onChange={event => setTone(event.target.value)} minLength={3} required /></label>
    <div className="onboarding-grid"><label>Approved claims · one per line<textarea value={claims} onChange={event => setClaims(event.target.value)} /></label><label>Forbidden claims · one per line<textarea value={forbidden} onChange={event => setForbidden(event.target.value)} /></label></div>
    <fieldset className="onboarding-channels"><legend>Channels</legend>{(['email', 'linkedin', 'social'] as const).map(channel => <label key={channel}><input type="checkbox" checked={channels.includes(channel)} disabled={channel === 'email'} onChange={event => setChannels(event.target.checked ? [...channels, channel] : channels.filter(item => item !== channel))} />{channel}{channel === 'linkedin' && ' (manual)'}</label>)}</fieldset>
    <p className="operational-note"><ShieldCheck size={15} /> Email send, follow-up send, and publishing require approval. LinkedIn stays manual. Research uses small batches and resolves one buyer per company.</p>
    <button className="button primary">Save strategy <ArrowRight size={16} /></button>
  </form></Section>
}

const reasons = ['wrong_industry', 'too_small', 'too_large', 'wrong_geography', 'wrong_buyer', 'weak_signal', 'existing_customer', 'other'] as const

function CalibrationRow({ candidate, run, token }: { candidate: Candidate; run: Run; token: string }) {
  const credentials = useCredentials()
  const [rating, setRating] = useState<'good' | 'maybe' | 'bad'>(candidate.feedback?.rating || 'maybe')
  const [reason, setReason] = useState<(typeof reasons)[number] | ''>(candidate.feedback?.reason || '')
  return <div className="onboarding-candidate"><div><strong>{candidate.name}</strong><small>{candidate.domain || 'No domain'} · {candidate.country || 'Country unavailable'} · {candidate.industry || 'Industry unavailable'}</small><small>Research band: {candidate.confidence_band} · lead score {candidate.lead_score}. This is not a verified ICP fit score.</small></div><div className="onboarding-candidate-actions"><select aria-label={`Rating for ${candidate.name}`} value={rating} onChange={event => setRating(event.target.value as typeof rating)}><option value="good">Good</option><option value="maybe">Maybe</option><option value="bad">Bad</option></select>{rating === 'bad' && <select aria-label={`Reason for ${candidate.name}`} value={reason} onChange={event => setReason(event.target.value as typeof reason)}><option value="">No reason</option>{reasons.map(value => <option key={value} value={value}>{value.replaceAll('_', ' ')}</option>)}</select>}<button className="button secondary" onClick={() => void run('save calibration', () => recordCalibration(credentials, { feedback: [{ lead_id: candidate.lead_id, rating, reason: rating === 'bad' ? reason || null : null }] }, token))}>Save rating</button>{candidate.feedback && <CheckCircle2 size={17} color="var(--success)" aria-label="Saved" />}</div></div>
}

function BuyerRow({ candidate, run, token }: { candidate: Candidate; run: Run; token: string }) {
  const credentials = useCredentials()
  const contacts = useQuery({ queryKey: ['company', candidate.company_id], queryFn: () => companyDetail(credentials, candidate.company_id), enabled: !candidate.buyer_lead_id })
  const [provider, setProvider] = useState<'hunter' | 'apollo'>('hunter')
  const [existing, setExisting] = useState('')
  return <div className="onboarding-candidate"><div><strong>{candidate.name}</strong><small>{candidate.domain || 'Domain unavailable'}</small>{candidate.buyer_lead_id && <small>Buyer saved: <Link to={`/contacts?contact=${encodeURIComponent(candidate.buyer_lead_id)}`}>{candidate.buyer_lead_id}</Link></small>}</div>{!candidate.buyer_lead_id && <div className="onboarding-candidate-actions"><select aria-label={`Provider for ${candidate.name}`} value={provider} onChange={event => setProvider(event.target.value as typeof provider)}><option value="hunter">Hunter</option><option value="apollo">Apollo</option></select><button className="button primary" onClick={() => void run('resolve buyer', () => resolveBuyer(credentials, { candidate_lead_id: candidate.lead_id, provider, existing_contact_id: null }, token))}>Resolve one buyer</button>{contacts.data?.contacts.length ? <><select aria-label={`Existing contact for ${candidate.name}`} value={existing} onChange={event => setExisting(event.target.value)}><option value="">Choose saved contact</option>{contacts.data.contacts.filter(item => item.email).map(item => <option key={item.id} value={item.id}>{item.full_name || item.email} · {item.job_title || 'Role unavailable'}</option>)}</select><button className="button secondary" disabled={!existing} onClick={() => void run('select buyer', () => resolveBuyer(credentials, { candidate_lead_id: candidate.lead_id, provider, existing_contact_id: existing }, token))}>Use contact</button></> : null}{contacts.isError && <small role="alert">Saved contacts unavailable: {contacts.error.message}</small>}</div>}</div>
}

export function OnboardingPage() {
  const credentials = useCredentials()
  const navigate = useNavigate()
  const queryClient = useQueryClient()
  const query = useQuery({ queryKey: ['onboarding'], queryFn: () => onboardingView(credentials) })
  const context = useQuery({ queryKey: ['company-context'], queryFn: () => companyContext(credentials) })
  const [token, setToken] = useState('')
  const [editingCompany, setEditingCompany] = useState(false)
  const [pending, setPending] = useState('')
  const [error, setError] = useState('')
  const view = query.data
  const program = view?.program || null
  const companyContext_ = context.data
  const step = view?.next_step || 'company'
  async function run(label: string, action: () => Promise<OnboardingView>) {
    if (!token.trim()) { setError('Enter the founder action token before saving this step.'); return }
    setError(''); setPending(label)
    try {
      const confirmed = await action()
      queryClient.setQueryData(['onboarding'], confirmed)
      if (label === 'save company') setEditingCompany(false)
      if (label === 'confirm company') {
        sessionStorage.removeItem(strategyEditKey(confirmed.program!.id))
        setPending('generating AI strategy')
        const drafted = await suggestStrategy(credentials, token)
        queryClient.setQueryData(['onboarding'], drafted)
      }
      if (label === 'save strategy') sessionStorage.removeItem(strategyEditKey(confirmed.program!.id))
      if (label === 'confirm company') await queryClient.invalidateQueries({ queryKey: ['company-context'] })
      await queryClient.invalidateQueries({ queryKey: ['onboarding'] })
      if (label === 'activate') {
        await queryClient.invalidateQueries({ queryKey: ['home'] })
        navigate('/home')
      }
    } catch (reason) { setError(reason instanceof Error ? reason.message : 'Action failed. Saved progress remains available.') }
    finally { setPending('') }
  }
  const good = view?.sample.filter(item => item.feedback?.rating === 'good') || []
  return <AppShell active="Onboarding" query="" onQueryChange={() => undefined}><div className="page-layout"><main className="page-main"><div className="page-content onboarding-page">
    <div className="page-heading"><div><h1>First-run setup</h1><p>Build a calibrated first prospect set on the same records used by Contacts and Outreach.</p></div><div className="heading-actions"><Link to="/services" className="button primary">Start with a service <ArrowRight size={16} /></Link><Link to="/home" className="button secondary">Home</Link></div></div>
    {query.isError && view && <div className="operational-error" role="alert">Refresh failed: {query.error.message} <button onClick={() => query.refetch()}>Retry</button></div>}
    {query.isPending ? <LoadingRows label="Loading onboarding" /> : query.isError && !view ? <DataState title="Setup could not be loaded" detail={query.error.message} retry={() => query.refetch()} /> : view && <>
      <div className="onboarding-progress"><span>Program: <strong>{program?.strategy?.name || program?.company.name || 'Not started'}</strong></span><StateBadge tone={step === 'home' ? 'green' : 'blue'}>{program?.status || 'not_started'}</StateBadge><span>Next: {step.replaceAll('_', ' ')}</span></div>
      {program && companyContext_ && <p className="operational-note">Company context: <StateBadge tone={companyContext_.status === 'context_complete' ? 'green' : 'yellow'}>{companyContext_.status === 'context_complete' ? 'context complete' : 'context incomplete'}</StateBadge>{(companyContext_.context?.missing?.length ?? 0) > 0 && <> Still unknown: {(companyContext_.context?.missing || []).join(', ').replaceAll('_', ' ')}.</>} Answers stay as given; nothing is inferred.</p>}
      {step !== 'home' && <label className="onboarding-token">Founder action token<input type="password" autoComplete="off" aria-label="Founder action token" value={token} onChange={event => setToken(event.target.value)} /><small>Required by the existing action gate; held only in this page's memory.</small></label>}
      {pending && <p role="status" className="operational-note">{pending}… Waiting for backend confirmation.</p>}
      {error && <p className="form-error" role="alert">{error}</p>}
      {(step === 'company' || editingCompany) && <CompanyStartForm program={program} run={run} token={token} />}
      {!editingCompany && (step === 'research_company' || step === 'confirm_company') && program && <CompanyConfirmForm key={program.research_provider || 'manual'} program={program} run={run} token={token} onEditCompany={() => setEditingCompany(true)} />}
      {step === 'strategy' && program && (program.strategy_draft
        ? <StrategyForm program={program} run={run} token={token} />
        : <Section title="3. Define your first program" detail="Generate an AI draft from your confirmed company context, then review and edit every field before saving."><button className="button primary" disabled={!!pending} onClick={() => void run('generate AI strategy', () => suggestStrategy(credentials, token))}>Generate AI draft <ArrowRight size={16} /></button></Section>)}
      {step === 'search' && program && <Section title="4. Find your first companies" detail="Research writes real company candidates into the existing sales lead store. Provider warnings remain visible."><p>Industry: <strong>{program.strategy?.icp.industry}</strong> · Market: <strong>{program.strategy?.markets[0]}</strong> · Up to {program.provider_limits?.sample_size || 10} companies in the calibration sample.</p>{program.research_warnings?.map(warning => <p className="operational-error" key={warning}>{warning}</p>)}<button className="button primary" disabled={!!pending} onClick={() => void run('search companies', () => searchFirstCompanies(credentials, token))}>Run company search <ArrowRight size={16} /></button>{view.sample.length === 0 && program.calibration_status === 'not_started' && <p className="operational-note">A successful search with zero companies leaves this step open. Refine the market or retry.</p>}</Section>}
      {step === 'calibrate' && <Section title="5. Calibrate on real companies" detail="Review each saved company. Ratings save individually so you can stop and resume without losing prior feedback."><p className="operational-note">{view.sample.filter(item => item.feedback).length} of {view.sample.length} classified. Bands are based on the existing lead score, not a verified fit model.</p><div className="onboarding-list">{view.sample.map(item => <CalibrationRow key={item.lead_id} candidate={item} run={run} token={token} />)}</div></Section>}
      {step === 'refinement' && program && <Section title="6. Review the suggested refinement" detail="Feedback proposes changes; nothing is applied without your choice."><div className="onboarding-proposal"><h3>Proposed exclusions</h3>{program.proposed_refinement?.exclusions?.length ? <ul>{program.proposed_refinement.exclusions.map(item => <li key={item}>{item}</li>)}</ul> : <p>No concrete exclusion can be inferred from the saved rejection reasons.</p>}{program.proposed_refinement?.notes?.map(note => <p key={note}>{note}</p>)}</div>{good.length === 0 && <p className="operational-note">No company was rated good. After deciding on this proposal, run another search before resolving buyers.</p>}<div className="onboarding-inline-actions"><button className="button primary" onClick={() => void run('approve refinement', () => decideRefinement(credentials, true, token))}>Approve proposal</button><button className="button secondary" onClick={() => void run('reject refinement', () => decideRefinement(credentials, false, token))}>Keep current strategy</button></div></Section>}
      {step === 'buyers' && <Section title="7. Resolve one buyer per approved company" detail="Only good companies are eligible. Existing saved contacts can be used; provider lookup is explicit and bounded to one."><div className="onboarding-list">{good.map(item => <BuyerRow key={item.lead_id} candidate={item} run={run} token={token} />)}</div></Section>}
      {step === 'drafts' && <Section title="8. Create first outreach drafts" detail="These are saved drafts only. Review and approve them in Outreach before any send."><div className="onboarding-list">{good.map(item => <div className="onboarding-candidate" key={item.lead_id}><div><strong>{item.name}</strong><small>Buyer: {item.buyer_lead_id}</small></div>{item.draft_id ? <Link className="button secondary" to={`/outreach?draft=${encodeURIComponent(item.draft_id)}`}>Review draft <ArrowRight size={15} /></Link> : <button className="button primary" onClick={() => void run('create draft', () => createFirstDraft(credentials, { candidate_lead_id: item.lead_id }, token))}>Generate draft</button>}</div>)}</div></Section>}
      {step === 'activate' && <Section title="9. Activate the program" detail="The calibrated prospect set and first drafts are saved. Activation does not send or publish anything."><p>{good.length} approved {good.length === 1 ? 'company' : 'companies'} · {good.filter(item => item.buyer_lead_id).length} buyers · {good.filter(item => item.draft_id).length} drafts.</p><button className="button primary" onClick={() => void run('activate', () => activateProgram(credentials, token))}>Activate and open Home <ArrowRight size={16} /></button></Section>}
      {step === 'home' && <Section title="Program active" detail="Your setup and calibration survive refresh and sign-in."><Link className="button primary" to="/home">Open Home <ArrowRight size={16} /></Link></Section>}
    </>}
  </div></main></div></AppShell>
}
