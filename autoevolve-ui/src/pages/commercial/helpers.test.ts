import { describe, expect, it } from 'vitest'
import { groupByStage, integrationPresentation, stageLabel } from './helpers'

describe('pipeline board helpers', () => {
  it('groups opportunities by stage without inventing stages', () => {
    const groups = groupByStage([{ stage: 'prospect' }, { stage: 'won' }, { stage: 'prospect' }])
    expect(groups.get('prospect')?.length).toBe(2)
    expect(groups.get('won')?.length).toBe(1)
    expect(groups.has('lost')).toBe(false)
  })

  it('falls back to the raw key for unknown stages', () => {
    expect(stageLabel([{ key: 'prospect', label: 'Prospect' }], 'prospect')).toBe('Prospect')
    expect(stageLabel([], 'custom_stage')).toBe('custom_stage')
  })
})

describe('integration presentation', () => {
  it('offers Connect only when credentials exist', () => {
    const p = integrationPresentation({ provider: 'hunter', label: 'Hunter', state: 'available', configured: true })
    expect(p.group).toBe('Available')
    expect(p.action).toEqual({ tone: 'primary', label: 'Connect', action: 'connect' })
  })

  it('never presents a coming-soon provider as connectable', () => {
    const p = integrationPresentation({ provider: 'hubspot', label: 'HubSpot', state: 'coming_soon', blocker: 'OAuth app approval is not configured' })
    expect(p.group).toBe('Coming soon')
    expect(p.action.action).toBe('none')
  })

  it('routes unhealthy connections to action required with the stored reason', () => {
    const p = integrationPresentation({
      provider: 'hunter', label: 'Hunter',
      connection: { status: 'action_required', sync_status: 'failed', last_error_sanitized: 'key rejected' },
    })
    expect(p.group).toBe('Action required')
    expect(p.detail).toBe('key rejected')
  })

  it('keeps connected providers in Connected with a sync action', () => {
    const p = integrationPresentation({
      provider: 'resend', label: 'Resend',
      connection: { status: 'healthy', sync_status: 'idle' },
    })
    expect(p.group).toBe('Connected')
    expect(p.action.action).toBe('sync')
  })
})
