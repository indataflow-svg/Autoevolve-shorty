import { afterEach, describe, expect, it, vi } from 'vitest'
import { bufferSetupAccounts, connectBuffer, discoverBuffer } from './operational'

const credentials = { username: 'founder', password: 'secret' }
afterEach(() => vi.unstubAllGlobals())

function mockFetch() {
  const fetchMock = vi.fn().mockResolvedValue({ ok: true, json: async () => ({}) })
  vi.stubGlobal('fetch', fetchMock)
  return fetchMock
}

describe('guided Buffer setup contract', () => {
  it('reads masked accounts without sending a token', async () => {
    const fetchMock = mockFetch()
    await bufferSetupAccounts(credentials)
    expect(fetchMock.mock.calls[0][0]).toBe('/company/setup/buffer/accounts')
    expect((fetchMock.mock.calls[0][1] as RequestInit).method).toBeUndefined()
  })

  it('discovers channels with the founder token and snake_case body', async () => {
    const fetchMock = mockFetch()
    await discoverBuffer(credentials, { account: 'acme', api_key: 'token-12345678' }, 'founder-token')
    expect(fetchMock.mock.calls[0][0]).toBe('/company/setup/buffer/discover')
    const options = fetchMock.mock.calls[0][1] as RequestInit
    expect(options.method).toBe('POST')
    expect(JSON.parse(String(options.body))).toEqual({ account: 'acme', api_key: 'token-12345678' })
    expect(new Headers(options.headers).get('X-Founder-Action-Token')).toBe('founder-token')
  })

  it('connects the selected channel ids and sends null for an unbound platform', async () => {
    const fetchMock = mockFetch()
    await connectBuffer(credentials, {
      account: 'acme',
      api_key: null,
      organization_id: 'org_1',
      instagram_channel_id: 'ch_ig',
      x_channel_id: null,
    }, 'founder-token')
    expect(fetchMock.mock.calls[0][0]).toBe('/company/setup/buffer/connect')
    const options = fetchMock.mock.calls[0][1] as RequestInit
    expect(JSON.parse(String(options.body))).toEqual({
      account: 'acme',
      api_key: null,
      organization_id: 'org_1',
      instagram_channel_id: 'ch_ig',
      x_channel_id: null,
    })
    expect(new Headers(options.headers).get('X-Founder-Action-Token')).toBe('founder-token')
  })
})
