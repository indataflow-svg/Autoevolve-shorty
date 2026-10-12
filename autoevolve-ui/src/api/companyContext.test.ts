import { afterEach, describe, expect, it, vi } from 'vitest'
import { companyContext, mergeContextSections, replaceCompanyContext, MARKETING_STAGES } from './companyContext'
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

describe('mergeContextSections', () => {
  const base = {
    company: { name: 'Example Studio', description: 'Builds tools' },
    product: { description: 'An ops audit' },
    status: 'context_incomplete',
    missing: ['customer'],
    completeness_percent: 67,
    workflow_ready: false,
    updated_at: '2026-01-01',
    schema_version: 1,
  }

  it('lets touched fields win while preserving untouched sections', () => {
    const merged = mergeContextSections(base, { customer: { ideal_customer: 'Ops teams' } })
    expect(merged).toEqual({
      company: { name: 'Example Studio', description: 'Builds tools' },
      product: { description: 'An ops audit' },
      customer: { ideal_customer: 'Ops teams' },
    })
  })

  it('merges into an existing section without dropping sibling fields', () => {
    const merged = mergeContextSections(base, { company: { website: 'studio.test' } }) as unknown as Record<string, Record<string, string>>
    expect(merged.company).toEqual({ name: 'Example Studio', description: 'Builds tools', website: 'studio.test' })
  })

  it('never echoes computed read-model keys back as claims', () => {
    const merged = mergeContextSections(base, {}) as unknown as Record<string, unknown>
    for (const key of ['status', 'missing', 'completeness_percent', 'workflow_ready', 'updated_at', 'schema_version']) {
      expect(merged).not.toHaveProperty(key)
    }
  })

  it('creates sections that did not exist yet', () => {
    const merged = mergeContextSections({}, { state: { marketing_stage: 'starting_from_zero' } })
    expect(merged).toEqual({ state: { marketing_stage: 'starting_from_zero' } })
  })
})