import { useEffect, useState } from 'react'
import { AlertCircle, Building2, Flag, Package, Rocket, Users, type LucideIcon } from 'lucide-react'
import { StateBadge } from './Primitives'
import {
  MARKETING_STAGES, companyContext, mergeContextSections, replaceCompanyContext,
  type CompanyContextView,
} from '../api/companyContext'
import type { Credentials } from '../api/client'

/**
 * Shared question copy for company facts. One voice for both editors:
 * the Commercial cards and the onboarding confirm form ask the same
 * questions with the same examples. The mapping to canonical sections
 * lives in core.company_context._ONBOARDING_SECTIONS; this map only
 * owns the words. `section`/`key` locate the stored answer.
 */
export const CANONICAL_QUESTIONS: Record<string, {
  question: string
  example: string
  help: string
  section: string
  key: string
}> = {
  description: { question: 'What is your company?', example: 'e.g. Northwind Logistics, a dispatch desk for freight teams', help: 'What the company is, in a sentence.', section: 'company', key: 'description' },
  industry: { question: 'Which industry do you sell into?', example: 'e.g. logistics', help: "The buyers' industry, not yours.", section: 'customer', key: 'industry' },
  positioning: { question: 'What do you promise buyers?', example: 'e.g. a dispatch desk that ends spreadsheet handoffs', help: 'The value in one line.', section: 'product', key: 'value_proposition' },
  offer_summary: { question: 'What is the offer?', example: 'e.g. managed dispatch setup plus a monthly handoff review', help: 'What they buy.', section: 'offer', key: 'description' },
  ideal_customer: { question: 'Who buys this?', example: 'e.g. dispatch managers at 20–200 person logistics firms', help: 'Who buys this, and why them.', section: 'customer', key: 'ideal_customer' },
  problem: { question: 'What problem do they pay to remove?', example: 'e.g. missed loads found late in spreadsheet handoffs', help: 'The problem they pay to remove.', section: 'market', key: 'problem' },
}

export function QuestionField({ label, value, placeholder, help, rows, disabled, showLabel, minLength, maxLength, required, onChange }: {
  label: string
  value: string
  placeholder?: string
  help?: string
  rows?: number
  disabled?: boolean
  showLabel?: boolean
  minLength?: number
  maxLength?: number
  required?: boolean
  onChange: (value: string) => void
}) {
  return <label>{showLabel === false ? null : label}<textarea aria-label={label} value={value} disabled={disabled}
    placeholder={placeholder} rows={rows || 3} minLength={minLength} maxLength={maxLength} required={required}
    onChange={event => onChange(event.target.value)} />{help && <small>{help}</small>}</label>
}

export const ANSWERS: Record<string, {
  label: string
  question: string
  example: string
  help: string
  section: string
  key: string
  icon: LucideIcon
  options?: Array<{ value: string; label: string }>
}> = {
  company: { label: 'Company', ...CANONICAL_QUESTIONS.description, section: 'company', key: 'description', icon: Building2 },
  product: { label: 'Product', question: 'What do you sell?', example: 'e.g. managed dispatch setup plus a monthly handoff review', help: 'What you sell.', section: 'product', key: 'description', icon: Package },
  customer: { label: 'Customer', ...CANONICAL_QUESTIONS.ideal_customer, section: 'customer', key: 'ideal_customer', icon: Users },
  problem: { label: 'Problem', ...CANONICAL_QUESTIONS.problem, section: 'market', key: 'problem', icon: AlertCircle },
  objective: { label: 'Objective', question: 'What outcome are you driving toward?', example: 'e.g. 5 booked discovery calls in 2 weeks', help: 'The outcome you are driving toward.', section: 'objective', key: 'primary_goal', icon: Flag },
  marketing_stage: {
    label: 'Starting state', question: 'Where are you starting from?', example: '', help: 'Whether the company already has a marketing motion. A validation plan is only planned from "starting from zero".',
    section: 'state',
    key: 'marketing_stage',
    icon: Rocket,
    options: MARKETING_STAGES,
  },
}

/**
 * Save founder-touched sections against a freshly fetched context.
 * The PUT is a full replacement, so merging over a stale render would
 * silently discard saves made elsewhere — hence the refetch first.
 */
export async function saveCompanyContextAnswers(
  credentials: Credentials, token: string, touched: Record<string, Record<string, string>>,
): Promise<CompanyContextView> {
  const fresh = await companyContext(credentials)
  return replaceCompanyContext(
    credentials, mergeContextSections(fresh.context as unknown as Record<string, unknown>, touched), token)
}

export function AnswerCards({ view, busy, savedTick, saveLabel, showAll, onSave }: {
  view: CompanyContextView
  busy: boolean
  savedTick: number
  saveLabel: string
  /** Full access: every group editable with stored values, not just the missing ones. */
  showAll?: boolean
  onSave: (touched: Record<string, Record<string, string>>) => void
}) {
  const [draft, setDraft] = useState<Record<string, string>>({})
  // A confirmed save refreshes the view from the server; the draft has served
  // its purpose and must not linger over the fresh values.
  useEffect(() => { setDraft({}) }, [savedTick])
  const sections = view.context as unknown as Record<string, Record<string, string> | undefined>
  const missing = (view.context.missing || []).filter(key => key in ANSWERS)
  const keys = showAll ? Object.keys(ANSWERS) : missing
  const stored = (key: string) => {
    const field = ANSWERS[key]
    return (sections[field.section] || {})[field.key] || ''
  }
  const current = (key: string) => {
    if (key in draft) return draft[key]
    // The stage is a fixed choice this phase, so it is never left blank.
    return key === 'marketing_stage' ? (stored(key) || MARKETING_STAGES[0].value) : stored(key)
  }
  const save = () => {
    // Only the single edited field per section travels up. The caller merges
    // over a freshly fetched context, so a stale render can never smuggle old
    // sibling values over saves made elsewhere.
    const touched: Record<string, Record<string, string>> = {}
    for (const key of keys) {
      const field = ANSWERS[key]
      const value = current(key).trim()
      if (!value) continue
      touched[field.section] = { ...touched[field.section], [field.key]: value }
    }
    onSave(touched)
  }
  if (keys.length === 0) return <p className="operational-note">Every required group is answered.</p>
  return <>
    <div className="answer-cards">
      {keys.map(key => {
        const field = ANSWERS[key]
        const Icon = field.icon
        const filled = stored(key).trim().length > 0
        return <div className="answer-card" key={key}>
          <div className="answer-card-head"><Icon size={18} /><h3>{field.question}</h3>{filled && <StateBadge tone="green">answered</StateBadge>}</div>
          <p className="answer-card-key">({field.section}.{field.key})</p>
          {field.options
            ? <select aria-label={field.question} value={current(key)} disabled={busy} onChange={event => setDraft(current => ({ ...current, [key]: event.target.value }))}>
              {field.options.map(option => <option key={option.value} value={option.value}>{option.label}</option>)}
            </select>
            : <QuestionField label={field.question} value={current(key)} disabled={busy}
              placeholder={field.example} help={field.help} showLabel={false}
              onChange={value => setDraft(current => ({ ...current, [key]: value }))} />}
        </div>
      })}
    </div>
    <div className="validation-actions">
      <button className="button primary" disabled={busy} onClick={save}>{saveLabel}</button>
      <span className="operational-note">{keys.filter(k => current(k).trim()).length} of 6 answered.</span>
    </div>
  </>
}

export function CompanyDataDialog({ view, busy, savedTick, band, onClose, onSave }: {
  view: CompanyContextView
  busy: boolean
  savedTick: number
  band: 'fresh' | 'blocked' | 'incomplete' | 'ready'
  onClose: () => void
  onSave: (touched: Record<string, Record<string, string>>) => void
}) {
  return <div className="modal-backdrop" onMouseDown={event => { if (event.target === event.currentTarget) onClose() }}>
    <div className="modal cx-wide" role="dialog" aria-modal="true" aria-label="Company data">
      <button className="icon-button modal-close" aria-label="Close dialog" onClick={onClose}>✕</button>
      <h2>{band === 'fresh' ? 'Set up your company data' : 'Company data'}</h2>
      <p>{band === 'fresh'
        ? 'Six quick cards — plain questions, one example each. Nothing here is final; everything stays editable.'
        : band === 'blocked'
          ? 'Workflow actions need at least 40% company data. Fill the cards below to unblock them.'
          : 'Every group, editable. Saving merges only what you change over the latest stored values.'}</p>
      <AnswerCards view={view} busy={busy} savedTick={savedTick} saveLabel="Save answers" showAll onSave={onSave} />
      <div className="modal-actions"><button className="button secondary" onClick={onClose}>{band === 'ready' || band === 'incomplete' ? 'Close' : 'Continue without completing'}</button></div>
    </div>
  </div>
}
