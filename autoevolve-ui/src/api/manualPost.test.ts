import { afterEach, describe, expect, it, vi } from 'vitest'
import { previewManualPost } from './workflows'

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
