import { afterEach, describe, expect, it, vi } from 'vitest'
import { commercialApi } from './commercial'

const credentials = { username: 'founder', password: 'secret' }

afterEach(() => vi.unstubAllGlobals())

describe('commercial transport', () => {
  it('lists offers with dashboard authentication', async () => {
    const fetchMock = vi.fn().mockResolvedValue({ ok: true, json: async () => [] })
    vi.stubGlobal('fetch', fetchMock)
    await commercialApi(credentials).offers()
    const [path, options] = fetchMock.mock.calls[0] as [string, RequestInit]
    expect(path).toBe('/company/commercial/offers')
    expect(new Headers(options.headers).get('Authorization')).toBe(`Basic ${btoa('founder:secret')}`)
  })

  it('lists the integration catalog with real states', async () => {
    const fetchMock = vi.fn().mockResolvedValue({ ok: true, json: async () => [] })
    vi.stubGlobal('fetch', fetchMock)
    await commercialApi(credentials).integrations()
    const [path] = fetchMock.mock.calls[0] as [string, RequestInit]
    expect(path).toBe('/company/commercial/integrations')
  })
})
