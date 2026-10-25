import { afterEach, describe, expect, it, vi } from 'vitest'
import { syncResendInbox } from './workflows'

const credentials = { username: 'founder', password: 'secret' }
afterEach(() => vi.unstubAllGlobals())

describe('inbox sync contract', () => {
  it('posts the limit and recipient filter with the founder token', async () => {
    const fetchMock = vi.fn().mockResolvedValue({ ok: true, json: async () => ({}) })
    vi.stubGlobal('fetch', fetchMock)
    await syncResendInbox(credentials, { limit: 25, to: 'sales@hello.indataflow.com' }, 'founder-token')
    expect(fetchMock.mock.calls[0][0]).toBe('/company/sales/inbox/sync')
    const options = fetchMock.mock.calls[0][1] as RequestInit
    expect(options.method).toBe('POST')
    expect(JSON.parse(String(options.body))).toEqual({ limit: 25, to: 'sales@hello.indataflow.com' })
    expect(new Headers(options.headers).get('X-Founder-Action-Token')).toBe('founder-token')
  })
})
