import type { components } from './schema'
import { api, type Credentials } from './client'

export type ValidationPlanRecord = components['schemas']['ValidationPlanRecord']
export type ValidationPlan = components['schemas']['ValidationPlan']
export type CommercialHypothesis = components['schemas']['CommercialHypothesis']
export type ValidationStrategy = components['schemas']['ValidationStrategy']
export type EvidenceLedger = components['schemas']['EvidenceLedger']
export type PlanLimits = components['schemas']['PlanLimits']
export type GovernanceRecord = components['schemas']['GovernanceRecord']
export type CompanyContextView = components['schemas']['CompanyContextView']

/** Read the latest governance decision, or null when the plan is untouched. */
export const validationGovernance = (credentials: Credentials) =>
  api<GovernanceRecord>('/company/marketing/validation/workflow', credentials)

/**
 * Ask governance to validate the plan and, if allowed, create the workflow.
 * A blocked plan is returned with its reasons; no workflow is created.
 */
export const createGovernedWorkflow = (credentials: Credentials, token: string) =>
  api<GovernanceRecord>('/company/marketing/validation/workflow', credentials, { method: 'POST', body: '{}' }, token)

/** Record founder approval. Execution stays locked until this exists. */
export const approveGovernedWorkflow = (credentials: Credentials, token: string) =>
  api<GovernanceRecord>('/company/marketing/validation/workflow/approve', credentials, { method: 'POST', body: '{}' }, token)

/**
 * Run the approved workflow through the existing runner. The only authorized
 * action is the side-effect-free simulation: nothing is sent or published.
 */
export const runWorkflowSimulation = (credentials: Credentials, token: string, targets: string[] = []) =>
  api<GovernanceRecord>('/company/marketing/validation/workflow/run', credentials, {
    method: 'POST', body: JSON.stringify({ targets }),
  }, token)

/** Read the most recent plan, or null when none exists yet. */
export const validationPlan = (credentials: Credentials) =>
  api<ValidationPlanRecord>('/company/marketing/validation/plan', credentials)

/**
 * Ask Hermes for a plan through the market_validation_v1 prompt.
 * This only plans: it never sends, publishes, launches, or spends.
 */
export const generateValidationPlan = (credentials: Credentials, token: string) =>
  api<ValidationPlanRecord>('/company/marketing/validation/plan', credentials, { method: 'POST' }, token)