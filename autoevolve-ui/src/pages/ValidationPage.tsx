import { useState } from 'react'
import { useQuery, useQueryClient } from '@tanstack/react-query'
import { ArrowRight, Compass, FileText, ShieldCheck } from 'lucide-react'
import { Link } from 'react-router-dom'
import { companyContext } from '../api/companyContext'
import {
  approveGovernedWorkflow, createGovernedWorkflow, generateValidationPlan, runWorkflowSimulation,
  validationGovernance, validationPlan, type GovernanceRecord, type ValidationPlanRecord,
} from '../api/validation'
import { ApiError } from '../api/client'
import { useCredentials } from '../app/Auth'
import { AppShell } from '../components/Shell'
import { DataState, LoadingRows, StateBadge } from '../components/Primitives'

function Facts({ title, items, tone }: { title: string; items: string[] | undefined; tone: 'green' | 'yellow' | 'blue' }) {
  const entries = items || []
  if (entries.length === 0) return null
  return <div className="validation-facts"><h3><StateBadge tone={tone}>{title}</StateBadge></h3><ul>{entries.map(item => <li key={item}>{item}</li>)}</ul></div>
}

function PlanView({ record }: { record: ValidationPlanRecord }) {
  const { plan, provenance, grounding, created_at: createdAt, status } = record
  const limits = plan.limits || { max_spend_usd: null, max_outreach_contacts: null, channel: null, duration_days: null, requires_approval: true }
  return <div className="validation-plan">
    <div className="onboarding-progress"><span>Plan <strong>{record.id}</strong></span><StateBadge tone={status === 'planned' ? 'blue' : 'neutral'}>{status}</StateBadge><span>{plan.workflow_template} · {provenance.prompt_version}</span></div>
    <section className="onboarding-panel"><div className="onboarding-panel-head"><h2>Hypothesis</h2><p>The single claim this experiment tests.</p></div>
      <dl className="validation-grid">
        <div><dt>Customer</dt><dd>{plan.hypothesis.customer}</dd></div>
        <div><dt>Problem</dt><dd>{plan.hypothesis.problem}</dd></div>
        <div><dt>Trigger</dt><dd>{plan.hypothesis.trigger}</dd></div>
        <div><dt>Offer</dt><dd>{plan.hypothesis.offer}</dd></div>
        <div><dt>Reason to believe</dt><dd>{plan.hypothesis.reason_to_believe}</dd></div>
        <div><dt>Desired action</dt><dd>{plan.hypothesis.desired_action}</dd></div>
      </dl>
    </section>
    <section className="onboarding-panel"><div className="onboarding-panel-head"><h2>Validation experiment</h2><p>The smallest test that can produce the validation event.</p></div>
      <dl className="validation-grid">
        <div><dt>Method</dt><dd>{plan.validation.method}</dd></div>
        <div><dt>Channel</dt><dd>{plan.validation.channel}</dd></div>
        <div><dt>Call to action</dt><dd>{plan.validation.call_to_action}</dd></div>
        <div><dt>Validation event</dt><dd>{plan.validation.validation_event}</dd></div>
        <div><dt>Success threshold</dt><dd>{plan.validation.success_threshold}</dd></div>
        <div><dt>Time window</dt><dd>{plan.validation.time_window}</dd></div>
      </dl>
      <div className="validation-text"><h3>Message</h3><p>{plan.validation.message}</p><h3>Offer</h3><p>{plan.validation.offer}</p></div>
      <dl className="validation-grid"><div><dt>Alternatives today</dt><dd>{plan.market.alternatives}</dd></div><div><dt>Next action</dt><dd>{plan.next_action}</dd></div></dl>
      <p className="operational-note"><ShieldCheck size={15} /> Proposed limits: {limits.max_spend_usd === null || limits.max_spend_usd === undefined ? 'spend not set' : `${limits.max_spend_usd} USD`} · {limits.max_outreach_contacts ?? 'outreach volume not set'} contacts · {limits.duration_days ?? 'duration not set'} days · approval {limits.requires_approval ? 'required' : 'not required'}. Limits are not enforced yet.</p>
    </section>
    <section className="onboarding-panel"><div className="onboarding-panel-head"><h2>Evidence</h2><p>Facts come from the founder; anything else is an assumption or an open question.</p></div>
      <Facts title="Known facts" tone="green" items={plan.evidence.known_facts} />
      <Facts title="Assumptions" tone="yellow" items={plan.evidence.assumptions} />
      <Facts title="Unknowns" tone="blue" items={plan.evidence.unknowns} />
      {(grounding?.moved_to_assumptions?.length ?? 0) > 0 && <p className="operational-note">{(grounding?.moved_to_assumptions?.length ?? 0)} claimed fact(s) could not be traced to the confirmed company context and were moved to assumptions.</p>}
    </section>
    <section className="onboarding-panel"><div className="onboarding-panel-head"><h2>Reasoning</h2><p>Why this method and message were chosen.</p></div><p className="validation-reasoning">{plan.reasoning}</p></section>
    <p className="operational-note">Generated {createdAt} by {provenance.generated_by} through {provenance.model_provider} (route {provenance.model_route}, model {provenance.model_name}). Nothing has been executed: this plan is a proposal awaiting review.</p>
  </div>
}

function GovernancePanel({ record, busy, error, onAction }: {
  record: GovernanceRecord
  busy: string
  error: string
  onAction: (action: 'validate' | 'approve' | 'run') => void
}) {
  const steps = (record.execution?.steps || []) as Array<{ output?: Record<string, unknown> }>
  const simulated = steps[0]?.output
  return <section className="onboarding-panel"><div className="onboarding-panel-head"><h2>Governance</h2><p>AutoEvolve decides whether the plan may run. Hermes never executes anything itself.</p></div>
    <ol className="validation-lifecycle">{[
      { key: 'plan', label: 'Validation Plan', reached: true },
      { key: 'validated', label: record.status === 'blocked' ? 'Blocked' : 'Validated', reached: true },
      { key: 'workflow_created', label: 'Workflow Created', reached: Boolean(record.workflow_id) },
      { key: 'approved', label: 'Approved', reached: Boolean(record.approved_at) },
      { key: 'executed', label: 'Executed', reached: Boolean(record.executed_at) },
    ].map(step => <li key={step.key} className={step.reached ? 'reached' : ''}><StateBadge tone={step.reached ? (step.key === 'plan' ? 'blue' : 'green') : 'neutral'}>{step.label}</StateBadge></li>)}</ol>
    <div className="validation-actions">
      <button className="button secondary" disabled={busy !== ''} onClick={() => onAction('validate')}>Validate Plan</button>
      <button className="button secondary" disabled={busy !== '' || !record.workflow_id || Boolean(record.approved_at)} onClick={() => onAction('approve')}>Approve</button>
      <button className="button primary" disabled={busy !== '' || !record.approved_at} onClick={() => onAction('run')}>Run Simulation</button>
    </div>
    {busy && <p role="status" className="operational-note">{busy}…</p>}
    {error && <p className="form-error" role="alert">{error}</p>}
    {record.status === 'blocked' && <div className="validation-reasons"><h3><StateBadge tone="red">Blocked</StateBadge></h3><ul>{(record.reasons || []).map(reason => <li key={reason}>{reason}</li>)}</ul><p className="operational-note">No workflow was created and nothing can run until the plan changes.</p></div>}
    {record.status === 'valid' && (record.warnings?.length ?? 0) > 0 && <div className="validation-reasons"><h3><StateBadge tone="yellow">Warnings</StateBadge></h3><ul>{(record.warnings || []).map(warning => <li key={warning}>{warning}</li>)}</ul></div>}
    {record.workflow_id && <p className="operational-note">Workflow <strong>{record.workflow_id}</strong> · action {(record.resolved_actions || []).map(item => item.action).join(', ') || 'none'} · approval {record.approved_at ? 'recorded' : 'required'}</p>}
    {simulated && <dl className="validation-grid">
      <div><dt>Simulation</dt><dd>{String(simulated.status)} · {String(simulated.action)}</dd></div>
      <div><dt>Targets / sent</dt><dd>{String(simulated.targets)} / {String(simulated.sent)}</dd></div>
      <div><dt>Validation events</dt><dd>{String(simulated.validation_events)}</dd></div>
      <div><dt>External side effects</dt><dd>{simulated.external_side_effects === false ? 'none' : 'unexpected'}</dd></div>
    </dl>}
  </section>
}

export function ValidationPage() {
  const credentials = useCredentials()
  const queryClient = useQueryClient()
  const query = useQuery({ queryKey: ['validation-plan'], queryFn: () => validationPlan(credentials), retry: false })
  const routing = useQuery({ queryKey: ['company-context'], queryFn: () => companyContext(credentials), retry: false })
  const governance = useQuery({ queryKey: ['validation-governance'], queryFn: () => validationGovernance(credentials), retry: false })
  const [token, setToken] = useState('')
  const [pending, setPending] = useState('')
  const [error, setError] = useState('')
  const [showPlan, setShowPlan] = useState(false)
  const record = query.data
  const decision = governance.data
  // A 404 means "not there yet", which is a normal state on this page.
  const noPlanYet = !record && (query.isError ? (query.error as ApiError).status === 404 : query.isSuccess)
  const noDecisionYet = !decision && (governance.isError ? (governance.error as ApiError).status === 404 : governance.isSuccess)
  const failed = query.isError && !noPlanYet
  const stage = (value: string | null | undefined) => (value || '—').replaceAll('_', ' ')
  async function generate() {
    if (!token.trim()) { setError('Enter the founder action token before generating a plan.'); return }
    setError(''); setPending('Hermes is preparing a validation plan')
    try {
      const created = await generateValidationPlan(credentials, token)
      queryClient.setQueryData(['validation-plan'], created)
      setShowPlan(true)
    } catch (reason) {
      setError(reason instanceof Error ? reason.message : 'Plan generation failed. No plan was stored.')
    } finally { setPending('') }
  }
  async function govern(action: 'validate' | 'approve' | 'run') {
    if (!token.trim()) { setError('Enter the founder action token before changing execution state.'); return }
    setError('')
    setPending(action === 'validate' ? 'Governance is validating the plan' : action === 'approve' ? 'Recording approval' : 'Running the simulated workflow')
    try {
      const updated = action === 'validate' ? await createGovernedWorkflow(credentials, token)
        : action === 'approve' ? await approveGovernedWorkflow(credentials, token)
          : await runWorkflowSimulation(credentials, token)
      queryClient.setQueryData(['validation-governance'], updated)
    } catch (reason) {
      setError(reason instanceof Error ? reason.message : 'That action was refused. Nothing ran.')
    } finally { setPending('') }
  }
  return <AppShell active="Market Validation" query="" onQueryChange={() => undefined}><div className="page-layout"><main className="page-main"><div className="page-content validation-page">
    <div className="page-heading"><div><h1>Market Validation</h1><p>Find the fastest credible way to test whether this business can generate real demand.</p></div><div className="heading-actions"><Link to="/home" className="button secondary">Home</Link></div></div>
    <div className="onboarding-progress"><span>Route: <strong>{stage(routing.data?.marketing_stage)} → {stage(routing.data?.next_stage)}</strong></span><StateBadge tone={record ? 'blue' : 'neutral'}>{record ? 'plan ready' : 'no plan yet'}</StateBadge><span>{record ? `Status: ${record.status}` : 'Planning only — nothing is executed'}</span></div>
    {query.isPending ? <LoadingRows label="Loading validation plan" /> : failed
      ? <DataState title="Validation plan could not be loaded" detail={query.error.message} retry={() => query.refetch()} />
      : <>
        <label className="onboarding-token">Founder action token<input type="password" autoComplete="off" aria-label="Founder action token" value={token} onChange={event => setToken(event.target.value)} /><small>Required by the existing action gate; held only in this page's memory.</small></label>
        {pending.startsWith('Hermes') && <p role="status" className="operational-note">Hermes is preparing a validation plan through the model gateway…</p>}
        {error && <p className="form-error" role="alert">{error}</p>}
        {record && <div className="validation-actions"><StateBadge tone="green">Validation Plan Ready</StateBadge><button className="button secondary" onClick={() => setShowPlan(current => !current)}>{showPlan ? 'Hide plan' : 'View Plan'}</button><button className="button primary" disabled={pending !== ''} onClick={() => void generate()}>Generate Validation Plan</button></div>}
        {!record && <div className="validation-actions"><button className="button primary" disabled={pending !== ''} onClick={() => void generate()}>Generate Validation Plan <ArrowRight size={16} /></button></div>}
        {record && !showPlan && <p className="operational-note"><Compass size={15} /> A plan is stored and reviewable. Nothing has been sent, published, or spent.</p>}
        {record && showPlan && <PlanView record={record} />}
        {decision && <GovernancePanel record={decision} busy={pending.startsWith('Governance') || pending === 'Recording approval' || pending === 'Running the simulated workflow' ? pending : ''} error={error} onAction={action => void govern(action)} />}
        {noDecisionYet && record && <section className="onboarding-panel"><div className="onboarding-panel-head"><h2>Governance</h2><p>Validating the plan checks its channel, limits, constraints, and approval requirement before any workflow exists.</p></div><div className="validation-actions"><button className="button secondary" disabled={pending !== ''} onClick={() => void govern('validate')}>Validate Plan</button></div></section>}
        {noPlanYet && <section className="onboarding-panel"><div className="onboarding-panel-head"><h2>What happens here</h2><p>AutoEvolve reads the confirmed company context and asks Hermes for the smallest credible validation experiment.</p></div><p className="operational-note"><FileText size={15} /> The result is a reviewable plan: hypothesis, market, validation experiment, evidence, and limits. Sending, publishing, and spending are not part of this stage.</p></section>}
      </>}
  </div></main></div></AppShell>
}