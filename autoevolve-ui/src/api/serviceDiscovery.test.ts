import { afterEach, describe, expect, it, vi } from 'vitest'
import { searchService } from './serviceDiscovery'

const credentials = { username: 'founder', password: 'secret' }

afterEach(() => vi.unstubAllGlobals())

describe('service discovery transport', () => {
  it('sends the service, contact count, and optional company name', async () => {
    const fetchMock = vi.fn().mockResolvedValue({ ok: true, json: async () => ({ runs: [] }) })
    vi.stubGlobal('fetch', fetchMock)
    await searchService(credentials, 'Appointment scheduling', 5, 'action-secret', 'Bright Dental Co')
    const [path, options] = fetchMock.mock.calls[0] as [string, RequestInit]
    expect(path).toBe('/company/setup/service-discovery/search')
    expect(options.method).toBe('POST')
    expect(JSON.parse(String(options.body))).toEqual({
      service: 'Appointment scheduling', desired_contacts: 5, company_name: 'Bright Dental Co',
    })
    expect(new Headers(options.headers).get('X-Founder-Action-Token')).toBe('action-secret')
  })

  it('omits the company name when the founder leaves it blank', async () => {
    const fetchMock = vi.fn().mockResolvedValue({ ok: true, json: async () => ({ runs: [] }) })
    vi.stubGlobal('fetch', fetchMock)
    await searchService(credentials, 'Appointment scheduling', 5, 'action-secret', '   ')
    const [, options] = fetchMock.mock.calls[0] as [string, RequestInit]
    expect(JSON.parse(String(options.body)).company_name).toBeNull()
  })
})