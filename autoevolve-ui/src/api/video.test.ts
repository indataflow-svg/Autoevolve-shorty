import { afterEach, describe, expect, it, vi } from 'vitest'
import { listJobs, listPlans, queuePlan } from './video'
import { ApiError } from './client'

const credentials = { username: 'founder', password: 'secret' }

afterEach(() => vi.unstubAllGlobals())

describe('video API transport', () => {
  it('queues a plan with the chosen render mode and the action token', async () => {
    const fetchMock = vi.fn().mockResolvedValue({
      ok: true,
      json: async () => ({ ok: true, queued: [], already_queued: false, counts: { total: 1 } }),
    })
    vi.stubGlobal('fetch', fetchMock)
    await queuePlan(credentials, 'splan_1', 'full', 'action-secret')
    const [path, options] = fetchMock.mock.calls[0] as [string, RequestInit]
    const url = new URL(path, 'http://test.local')
    expect(url.pathname).toBe('/company/video/plans/splan_1/queue')
    expect(url.searchParams.get('render_mode')).toBe('full')
    expect(options.method).toBe('POST')
    expect(new Headers(options.headers).get('X-Founder-Action-Token')).toBe('action-secret')
    expect(new Headers(options.headers).get('Authorization')).toBe(`Basic ${btoa('founder:secret')}`)
  })

  it('lists jobs scoped to the selected plan', async () => {
    const fetchMock = vi.fn().mockResolvedValue({ ok: true, json: async () => ({ jobs: [] }) })
    vi.stubGlobal('fetch', fetchMock)
    await listJobs(credentials, 'splan_1')
    const [path] = fetchMock.mock.calls[0] as [string, RequestInit]
    const url = new URL(path, 'http://test.local')
    expect(url.pathname).toBe('/company/video/jobs')
    expect(url.searchParams.get('shot_plan_id')).toBe('splan_1')
  })

  it('filters plans by spec and surfaces a denied queue as ApiError', async () => {
    const fetchMock = vi.fn().mockResolvedValue({ ok: true, json: async () => ({ plans: [] }) })
    vi.stubGlobal('fetch', fetchMock)
    await listPlans(credentials, 'vspec_1')
    const [path] = fetchMock.mock.calls[0] as [string, RequestInit]
    expect(new URL(path, 'http://test.local').searchParams.get('spec_id')).toBe('vspec_1')

    const denied = vi.fn().mockResolvedValue({
      ok: false, status: 403, statusText: 'Forbidden',
      json: async () => ({ detail: 'founder action token is missing or invalid' }),
    })
    vi.stubGlobal('fetch', denied)
    await expect(queuePlan(credentials, 'splan_1', 'shots', 'wrong')).rejects.toBeInstanceOf(ApiError)
  })
})
