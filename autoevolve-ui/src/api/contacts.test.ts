import { afterEach, describe, expect, it, vi } from 'vitest'
import { contactsPage, draftOutreach } from './contacts'
import { ApiError } from './client'

const credentials = { username: 'founder', password: 'secret' }

afterEach(() => vi.unstubAllGlobals())

describe('contacts API transport', () => {
  it('encodes URL filters and authenticates the complete page request', async () => {
    const fetchMock = vi.fn().mockResolvedValue({ ok: true, json: async () => ({ items: [] }) })
    vi.stubGlobal('fetch', fetchMock)
    await contactsPage(credentials, { page: 3, q: 'Rift & Sons', stage: 'qualified', sort: 'score' })
    const [path, options] = fetchMock.mock.calls[0] as [string, RequestInit]
    const url = new URL(path, 'http://test.local')
    expect(url.searchParams.get('page')).toBe('3')
    expect(url.searchParams.get('q')).toBe('Rift & Sons')
    expect(url.searchParams.get('stage')).toBe('qualified')
    expect(url.searchParams.get('sort')).toBe('score')
    expect(new Headers(options.headers).get('Authorization')).toBe(`Basic ${btoa('founder:secret')}`)
    expect(new Headers(options.headers).get('X-Requested-With')).toBe('XMLHttpRequest')
  })

  it('sends the founder action token and rejects a denied draft', async () => {
    const fetchMock = vi.fn().mockResolvedValue({ ok: false, status: 403, statusText: 'Forbidden', json: async () => ({ detail: 'founder action token is missing or invalid' }) })
    vi.stubGlobal('fetch', fetchMock)
    await expect(draftOutreach(credentials, 'lead_1', 'wrong')).rejects.toBeInstanceOf(ApiError)
    const [, options] = fetchMock.mock.calls[0] as [string, RequestInit]
    expect(options.method).toBe('POST')
    expect(new Headers(options.headers).get('X-Founder-Action-Token')).toBe('wrong')
  })
})
