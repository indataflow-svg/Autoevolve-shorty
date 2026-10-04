import { afterEach, describe, expect, it, vi } from 'vitest'
import { companyContext, replaceCompanyContext, MARKETING_STAGES } from './companyContext'
import { ApiError } from './client'

const credentials = { username: 'founder', password: 'secret' }

afterEach(() => vi.unstubAllGlobals())

describe('company context API transport', () => {
  it('reads the canonical context and its resolved route with dashboard authentication', async () => {
    const fetchMock = vi.fn().mockResolvedValue({
      ok: true,
      json: async () => ({ context: { status: 'context_incomplete' }, status: 'context_incomplete', next_stage: null }),
    })
    vi.stubGlobal('fetch', fetchMock)
    const view = await companyContext(credentials)
    const [path, options] = fetchMock.mock.calls[0] as [string, RequestInit]
    expect(path).toBe('/company/context')
    expect(options.method).toBeUndefined()
    expect(new Headers(options.headers).get('Authorization')).toBe(`Basic ${btoa('founder:secret')}`)
    expect(view.next_stage).toBeNull()
  })

  it('replaces the context with the founder action token', async () => {
    const fetchMock = vi.fn().mockResolvedValue({
      ok: true,
      json: async () => ({ status: 'context_complete', marketing_stage: 'starting_from_zero', next_stage: 'market_validation' }),
    })
    vi.stubGlobal('fetch', fetchMock)
    await replaceCompanyContext(credentials, { state: { marketing_stage: 'starting_from_zero' } }, 'action-secret')
    const [path, options] = fetchMock.mock.calls[0] as [string, RequestInit]
    expect(path).toBe('/company/context')
    expect(options.method).toBe('PUT')
    expect(new Headers(options.headers).get('X-Founder-Action-Token')).toBe('action-secret')
    expect(JSON.parse(String(options.body))).toEqual({ state: { marketing_stage: 'starting_from_zero' } })
  })

  it('surfaces a rejected write instead of saving silently', async () => {
    const fetchMock = vi.fn().mockResolvedValue({
      ok: false, status: 422, statusText: 'Unprocessable Content',
      json: async () => ({ detail: [{ loc: ['body', 'state', 'marketing_stage'], msg: 'unknown marketing stage' }] }),
    })
    vi.stubGlobal('fetch', fetchMock)
    await expect(replaceCompanyContext(credentials, {}, 'action-secret')).rejects.toBeInstanceOf(ApiError)
  })

  it('offers only the stage this phase supports', () => {
    expect(MARKETING_STAGES.map(option => option.value)).toEqual(['starting_from_zero'])
  })
})