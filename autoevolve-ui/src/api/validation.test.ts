import { afterEach, describe, expect, it, vi } from 'vitest'
import {
  approveGovernedWorkflow, createGovernedWorkflow, generateValidationPlan,
  runWorkflowSimulation, validationGovernance, validationPlan,
} from './validation'
import { ApiError } from './client'

const credentials = { username: 'founder', password: 'secret' }

afterEach(() => vi.unstubAllGlobals())

describe('validation plan transport', () => {
  it('reads the stored plan with dashboard authentication', async () => {
    const fetchMock = vi.fn().mockResolvedValue({ ok: true, json: async () => ({ status: 'planned' }) })
    vi.stubGlobal('fetch', fetchMock)
    const record = await validationPlan(credentials)
    const [path, options] = fetchMock.mock.calls[0] as [string, RequestInit]
    expect(path).toBe('/company/automation/plan')
    expect(options.method).toBeUndefined()
    expect(new Headers(options.headers).get('Authorization')).toBe(`Basic ${btoa('founder:secret')}`)
    expect(record.status).toBe('planned')
  })

  it('generates a plan with the founder action token and no request body', async () => {
    const fetchMock = vi.fn().mockResolvedValue({ ok: true, json: async () => ({ status: 'planned' }) })
    vi.stubGlobal('fetch', fetchMock)
    await generateValidationPlan(credentials, 'action-secret')
    const [path, options] = fetchMock.mock.calls[0] as [string, RequestInit]
    expect(path).toBe('/company/automation/plan')
    expect(options.method).toBe('POST')
    expect(options.body).toBeUndefined()
    expect(new Headers(options.headers).get('X-Founder-Action-Token')).toBe('action-secret')
  })

  it('reports a refused generation instead of showing an empty plan', async () => {
    const fetchMock = vi.fn().mockResolvedValue({
      ok: false, status: 502, statusText: 'Bad Gateway',
      json: async () => ({ detail: 'Hermes did not return a valid validation plan: UnexpectedModelBehavior' }),
    })
    vi.stubGlobal('fetch', fetchMock)
    await expect(generateValidationPlan(credentials, 'action-secret')).rejects.toBeInstanceOf(ApiError)
  })

  it('surfaces "no plan yet" so the page can offer generation', async () => {
    const fetchMock = vi.fn().mockResolvedValue({
      ok: false, status: 404, statusText: 'Not Found',
      json: async () => ({ detail: 'no validation plan has been generated yet' }),
    })
    vi.stubGlobal('fetch', fetchMock)
    await expect(validationPlan(credentials)).rejects.toMatchObject({ status: 404 })
  })
})

describe('governance transport', () => {
  it('reads the latest decision without a write header', async () => {
    const fetchMock = vi.fn().mockResolvedValue({ ok: true, json: async () => ({ lifecycle: 'validated' }) })
    vi.stubGlobal('fetch', fetchMock)
    const record = await validationGovernance(credentials)
    const [path, options] = fetchMock.mock.calls[0] as [string, RequestInit]
    expect(path).toBe('/company/automation/governance')
    expect(options.method).toBeUndefined()
    expect(record.lifecycle).toBe('validated')
  })

  it('validates, approves, and runs with the founder action token', async () => {
    const fetchMock = vi.fn().mockResolvedValue({ ok: true, json: async () => ({ status: 'valid' }) })
    vi.stubGlobal('fetch', fetchMock)
    await createGovernedWorkflow(credentials, 'action-secret')
    await approveGovernedWorkflow(credentials, 'action-secret')
    await runWorkflowSimulation(credentials, 'action-secret', ['sim_prospect_1'])
    const paths = fetchMock.mock.calls.map(call => (call as [string, RequestInit])[0])
    expect(paths).toEqual([
      '/company/automation/governance',
      '/company/automation/governance/approve',
      '/company/automation/governance/run',
    ])
    for (const [, options] of fetchMock.mock.calls as Array<[string, RequestInit]>) {
      expect(options.method).toBe('POST')
      expect(new Headers(options.headers).get('X-Founder-Action-Token')).toBe('action-secret')
    }
    const [, runOptions] = fetchMock.mock.calls[2] as [string, RequestInit]
    expect(JSON.parse(String(runOptions.body))).toEqual({ targets: ['sim_prospect_1'] })
  })

  it('reports a governance refusal instead of showing a result', async () => {
    const fetchMock = vi.fn().mockResolvedValue({
      ok: false, status: 409, statusText: 'Conflict',
      json: async () => ({ detail: 'governance requires founder approval before execution' }),
    })
    vi.stubGlobal('fetch', fetchMock)
    await expect(runWorkflowSimulation(credentials, 'action-secret')).rejects.toBeInstanceOf(ApiError)
  })
})