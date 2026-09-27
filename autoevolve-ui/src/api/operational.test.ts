import { afterEach, describe, expect, it, vi } from 'vitest'
import { api, ApiError } from './client'
import { integrationsView, settingsView, testProviderKeys } from './operational'

const credentials = { username: 'founder', password: 'secret' }
afterEach(() => vi.unstubAllGlobals())

describe('operational backend contract', () => {
  it('uses exact lower-case routes and snake_case payloads', async () => {
    const fetchMock = vi.fn().mockResolvedValue({ ok: true, json: async () => ({}) })
    vi.stubGlobal('fetch', fetchMock)
    await integrationsView(credentials)
    await settingsView(credentials)
    await testProviderKeys(credentials, { group: 'media', values: { PIXABAY_API_KEY: 'long-test-value' } }, 'action-token')
    expect(fetchMock.mock.calls.map(([path]) => path)).toEqual(['/company/ui/integrations', '/company/ui/settings', '/company/setup/keys/test'])
    const options = fetchMock.mock.calls[2][1] as RequestInit
    expect(JSON.parse(String(options.body))).toEqual({ group: 'media', values: { PIXABAY_API_KEY: 'long-test-value' } })
    expect(new Headers(options.headers).get('X-Founder-Action-Token')).toBe('action-token')
  })

  it.each([
    [400, 'invalid input', 'invalid input'],
    [403, 'founder action token is missing or invalid', 'not authorized'],
    [404, 'org not found', 'org not found'],
    [409, 'org already exists', 'org already exists'],
    [500, 'provider failed', 'Server or provider failure'],
  ])('preserves HTTP %s error semantics', async (status, detail, expected) => {
    vi.stubGlobal('fetch', vi.fn().mockResolvedValue({ ok: false, status, statusText: 'Error', headers: new Headers(), json: async () => ({ detail }) }))
    await expect(api('/exact/path', credentials)).rejects.toMatchObject({ status, path: '/exact/path', message: expect.stringContaining(expected) })
  })

  it('surfaces Pydantic and keyed provider validation failures', async () => {
    vi.stubGlobal('fetch', vi.fn().mockResolvedValueOnce({ ok: false, status: 422, headers: new Headers(), json: async () => ({ detail: [{ loc: ['body', 'name'], msg: 'Field required' }] }) }).mockResolvedValueOnce({ ok: false, status: 422, headers: new Headers(), json: async () => ({ detail: { PIXABAY_API_KEY: 'looks too short for a key' } }) }))
    await expect(api('/company/marketing/orgs', credentials)).rejects.toMatchObject({ issues: [{ field: 'name', message: 'Field required' }] })
    await expect(api('/company/setup/keys/test', credentials)).rejects.toMatchObject({ issues: [{ field: 'PIXABAY_API_KEY', message: 'looks too short for a key' }] })
  })

  it('honors Retry-After and records request IDs', async () => {
    vi.stubGlobal('fetch', vi.fn().mockResolvedValue({ ok: false, status: 429, headers: new Headers({ 'Retry-After': '12', 'X-Request-ID': 'req-123' }), json: async () => ({ detail: 'rate limited' }) }))
    try { await api('/company/ui/settings', credentials) } catch (error) {
      expect(error).toBeInstanceOf(ApiError)
      expect(error).toMatchObject({ status: 429, retryAfterSeconds: 12, requestId: 'req-123' })
    }
  })
})
