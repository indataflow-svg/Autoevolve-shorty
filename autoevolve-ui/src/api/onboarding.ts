import type { components } from './schema'
import { api, type Credentials } from './client'

export type OnboardingView = components['schemas']['OnboardingView']
export type CompanyStart = components['schemas']['CompanyStart']
export type CompanyContext = components['schemas']['CompanyContext']
export type StrategyInput = components['schemas']['StrategyInput']
export type CalibrationInput = components['schemas']['CalibrationInput']
export type BuyerRequest = components['schemas']['BuyerRequest']
export type DraftRequest = components['schemas']['DraftRequest']

const write = (credentials: Credentials, path: string, token: string, body?: unknown) => api<OnboardingView>(
  `/company/setup/onboarding${path}`, credentials,
  { method: 'POST', ...(body === undefined ? {} : { body: JSON.stringify(body) }) }, token,
)

export const onboardingView = (credentials: Credentials) => api<OnboardingView>('/company/ui/onboarding', credentials)
export const startCompany = (credentials: Credentials, value: CompanyStart, token: string) => write(credentials, '/company', token, value)
export const researchOwnCompany = (credentials: Credentials, token: string) => write(credentials, '/research-company', token)
export const confirmCompany = (credentials: Credentials, value: CompanyContext, token: string) => write(credentials, '/company/confirm', token, value)
export const suggestStrategy = (credentials: Credentials, token: string) => write(credentials, '/strategy/draft', token)
export const confirmStrategy = (credentials: Credentials, value: StrategyInput, token: string) => write(credentials, '/strategy', token, value)
export const searchFirstCompanies = (credentials: Credentials, token: string) => write(credentials, '/search', token)
export const recordCalibration = (credentials: Credentials, value: CalibrationInput, token: string) => write(credentials, '/calibration', token, value)
export const decideRefinement = (credentials: Credentials, approved: boolean, token: string) => write(credentials, '/refinement', token, { approved })
export const resolveBuyer = (credentials: Credentials, value: BuyerRequest, token: string) => write(credentials, '/buyer', token, value)
export const createFirstDraft = (credentials: Credentials, value: DraftRequest, token: string) => write(credentials, '/draft', token, value)
export const activateProgram = (credentials: Credentials, token: string) => write(credentials, '/activate', token)
