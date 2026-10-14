import type { components } from './schema'
import { api, type Credentials } from './client'

export type ValidationPlanRecord = components['schemas']['ValidationPlanRecord']
export type ValidationPlan = components['schemas']['ValidationPlan']
export type CommercialHypothesis = components['schemas']['CommercialHypothesis']
export type ValidationStrategy = components['schemas']['ValidationStrategy']
export type EvidenceLedger = components['schemas']['EvidenceLedger']
export type PlanLimits = components['schemas']['PlanLimits']
export type GovernanceRecord = components['schemas']['GovernanceRecord']
export type AutomationWorkflowView = components['schemas']['AutomationWorkflowView']
export type CompanyContextView = components['schemas']['CompanyContextView']

/** Read the latest governance decision, or null when the plan is untouched. */
export const validationGovernance = (credentials: Credentials) =>
  api<GovernanceRecord>('/company/automation/governance', credentials)

/**
 * Ask governance to validate the plan and, if allowed, create the workflow.
 * A blocked plan is returned with its reasons; no workflow is created.
 */
export const createGovernedWorkflow = (credentials: Credentials, token: string) =>
  api<GovernanceRecord>('/company/automation/governance', credentials, { method: 'POST', body: '{}' }, token)

/** Record founder approval. Execution stays locked until this exists. */
export const approveGovernedWorkflow = (credentials: Credentials, token: string) =>
  api<GovernanceRecord>('/company/automation/governance/approve', credentials, { method: 'POST', body: '{}' }, token)

/**
 * Run the approved workflow through the existing runner. Authorized actions
 * simulate, draft, research, or send founder-approved drafts; every run
 * re-checks the approved limits first. `targets` are lead ids for research
 * and draft ids for sends — identifiers the founder chose, never people.
 */
export const runWorkflowSimulation = (credentials: Credentials, token: string, targets: string[] = []) =>
  api<GovernanceRecord>('/company/automation/governance/run', credentials, {
    method: 'POST', body: JSON.stringify({ targets }),
  }, token)

/** Read the most recent plan, or null when none exists yet. */
export const validationPlan = (credentials: Credentials) =>
  api<ValidationPlanRecord>('/company/automation/plan', credentials)

/**
 * Ask Hermes for a plan through the market_validation_v1 prompt.
 * This only plans: it never sends, publishes, launches, or spends.
 * Optional founder hints are requests Hermes may decline with reasons;
 * ungovernable methods and unsupported channels are refused with a 422.
 */
export const generateValidationPlan = (
  credentials: Credentials, token: string, hints?: { method_hint?: string; channel_hint?: string },
) =>
  api<ValidationPlanRecord>('/company/automation/plan', credentials,
    { method: 'POST', body: JSON.stringify(hints ?? {}) }, token)

/** All governed workflows with their engine state, newest first. */
export const automationWorkflows = (credentials: Credentials) =>
  api<AutomationWorkflowView[]>('/company/automation/workflows', credentials)

export type WorkflowSuggestion = {
  rank: number; method: string; title: string; rationale: string
  evidence_refs: string[]; scheduled_for: string; due_now: boolean; duration_days: number
  expected_range: { low: number; high: number; unit: string; basis: string }
  channel: string | null
}

export type WorkflowSuggestions = {
  recommendations: WorkflowSuggestion[]
  evidence_summary: Record<string, number>
  caps: Record<string, number>
}

export type CampaignSuggestion = {
  video_prompt: { lines: Array<{ slot: string; text: string; source: string }>; omitted: Array<{ slot: string; missing_field: string; note: string }> }
  campaign: { path: string; rationale: string; evidence_refs: string[] }
  provider: { channel: string | null; via: string; rationale: string; reply_rate: number | null; rate_basis: string }
}

/** Rank the next runs from evidence. Advisory: plans, governs, runs nothing. */
export const suggestWorkflows = (credentials: Credentials) =>
  api<WorkflowSuggestions>('/company/automation/suggest', credentials, { method: 'POST', body: '{}' })

/** Propose video lines, campaign path, and provider from evidence. Advisory only. */
export const suggestCampaign = (credentials: Credentials) =>
  api<CampaignSuggestion>('/company/automation/suggest-campaign', credentials, { method: 'POST', body: '{}' })
