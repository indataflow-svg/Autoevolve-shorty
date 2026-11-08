import { afterEach, describe, expect, it, vi } from 'vitest'
import { confirmBufferSend, createManualPost, previewManualPost } from './workflows'

const credentials = { username: 'founder', password: 'secret' }
afterEach(() => vi.unstubAllGlobals())

describe('manual post preview contract', () => {
  it('posts snake_case fields to the preview route', async () => {
    const fetchMock = vi.fn().mockResolvedValue({ ok: true, json: async () => ({}) })
    vi.stubGlobal('fetch', fetchMock)
    await previewManualPost(credentials, {
      platform: 'instagram',
      postType: 'carousel',
      destinationUrl: 'https://example.com/apply',
      linkLabel: 'ops audit',
      filenames: ['slide-1.png', 'slide-2.png'],
    })
    expect(fetchMock.mock.calls[0][0]).toBe('/company/marketing/manual-posts/preview')
    const options = fetchMock.mock.calls[0][1] as RequestInit
    expect(options.method).toBe('POST')
    expect(JSON.parse(String(options.body))).toEqual({
      platform: 'instagram',
      post_type: 'carousel',
      destination_url: 'https://example.com/apply',
      link_label: 'ops audit',
      filenames: ['slide-1.png', 'slide-2.png'],
    })
  })

  it('sends null for blank optional inputs so the backend applies its defaults', async () => {
    const fetchMock = vi.fn().mockResolvedValue({ ok: true, json: async () => ({}) })
    vi.stubGlobal('fetch', fetchMock)
    await previewManualPost(credentials, {
      platform: 'x',
      postType: 'video',
      destinationUrl: '',
      linkLabel: '',
      filenames: [],
    })
    const options = fetchMock.mock.calls[0][1] as RequestInit
    expect(JSON.parse(String(options.body))).toEqual({
      platform: 'x',
      post_type: 'video',
      destination_url: null,
      link_label: null,
      filenames: [],
    })
  })
})

describe('manual post create contract', () => {
  it('sends the selected publisher and account with the form fields', async () => {
    const fetchMock = vi.fn().mockResolvedValue({ ok: true, json: async () => ({}) })
    vi.stubGlobal('fetch', fetchMock)
    await createManualPost(credentials, {
      platform: 'linkedin',
      postType: 'carousel',
      destinationUrl: '',
      linkLabel: '',
      assets: [],
      publisher: 'buffer',
      bufferAccount: 'acme',
    })
    expect(fetchMock.mock.calls[0][0]).toBe('/company/marketing/manual-posts')
    const options = fetchMock.mock.calls[0][1] as RequestInit
    expect(options.body).toBeInstanceOf(FormData)
    const body = options.body as FormData
    expect(body.get('platform')).toBe('linkedin')
    expect(body.get('buffer_account')).toBe('acme')
  })

  it('posts to the confirm route with the founder token', async () => {
    const fetchMock = vi.fn().mockResolvedValue({ ok: true, json: async () => ({}) })
    vi.stubGlobal('fetch', fetchMock)
    await confirmBufferSend(credentials, 'post-1', 'founder-token')
    expect(fetchMock.mock.calls[0][0]).toBe('/company/marketing/manual-posts/post-1/buffer-confirm')
    const options = fetchMock.mock.calls[0][1] as RequestInit
    expect(options.method).toBe('POST')
    expect(new Headers(options.headers).get('X-Founder-Action-Token')).toBe('founder-token')
  })
})
