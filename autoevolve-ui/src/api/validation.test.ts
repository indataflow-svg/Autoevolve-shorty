import { afterEach, describe, expect, it, vi } from 'vitest'
import { generateValidationPlan, validationPlan } from './validation'
import { ApiError } from './client'

const credentials = { username: 'founder', password: 'secret' }

afterEach(() => vi.unstubAllGlobals())

describe('validation plan transport', () => {
  it('reads the stored plan with dashboard authentication', async () => {
    const fetchMock = vi.fn().mockResolvedValue({ ok: true, json: async () => ({ status: 'planned' }) })
    vi.stubGlobal('fetch', fetchMock)
    const record = await validationPlan(credentials)
    const [path, options] = fetchMock.mock.calls[0] as [string, RequestInit]
    expect(path).toBe('/company/marketing/validation/plan')
    expect(options.method).toBeUndefined()
    expect(new Headers(options.headers).get('Authorization')).toBe(`Basic ${btoa('founder:secret')}`)
    expect(record.status).toBe('planned')
  })

  it('generates a plan with the founder action token and no request body', async () => {
    const fetchMock = vi.fn().mockResolvedValue({ ok: true, json: async () => ({ status: 'planned' }) })
    vi.stubGlobal('fetch', fetchMock)
    await generateValidationPlan(credentials, 'action-secret')
    const [path, options] = fetchMock.mock.calls[0] as [string, RequestInit]
    expect(path).toBe('/company/marketing/validation/plan')
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