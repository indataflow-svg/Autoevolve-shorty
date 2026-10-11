/** Pure presentation helpers for the commercial workspace. No I/O, no invented data. */

export type StageDef = { key: string; label?: string; allowed_next?: string[] }

export function groupByStage<T extends { stage: string }>(items: T[]): Map<string, T[]> {
  const groups = new Map<string, T[]>()
  for (const item of items) {
    const list = groups.get(item.stage) || []
    list.push(item)
    groups.set(item.stage, list)
  }
  return groups
}

export function stageLabel(stages: StageDef[], key: string): string {
  return stages.find(s => s.key === key)?.label || key
}

export type IntegrationView = {
  provider: string
  label: string
  state?: string
  configured?: boolean
  blocker?: string
  connection?: { status: string; sync_status: string; last_error_sanitized?: string } | null
}

export type IntegrationAction = { tone: 'primary' | 'secondary'; label: string; action: 'connect' | 'sync' | 'disconnect' | 'none' }

/** Translate a backend connection state into one user action and plain words. */
export function integrationPresentation(item: IntegrationView): {
  group: 'Available' | 'Connected' | 'Action required' | 'Coming soon'
  message: string
  action: IntegrationAction
  detail?: string
} {
  const conn = item.connection
  if (!conn) {
    if (item.state === 'coming_soon' || item.state === 'unavailable' && item.blocker && /approval/i.test(item.blocker)) {
      return {
        group: 'Coming soon',
        message: item.blocker || 'External approval is still required before this can connect.',
        action: { tone: 'secondary', label: 'View requirements', action: 'none' },
      }
    }
    if (item.state === 'available' || item.configured) {
      return {
        group: 'Available',
        message: 'Credentials are configured. Connecting validates against the provider.',
        action: { tone: 'primary', label: 'Connect', action: 'connect' },
      }
    }
    return {
      group: 'Coming soon',
      message: item.blocker || 'Credentials are not configured yet.',
      action: { tone: 'secondary', label: 'View requirements', action: 'none' },
    }
  }
  if (conn.status === 'healthy' || conn.status === 'connected') {
    return {
      group: 'Connected',
      message: conn.sync_status === 'failed' ? 'Connected, but the last sync failed.' : 'Connected and healthy.',
      action: { tone: 'secondary', label: 'Sync now', action: 'sync' },
      detail: conn.last_error_sanitized || undefined,
    }
  }
  if (conn.status === 'disconnected') {
    return {
      group: 'Available',
      message: 'Disconnected. Reconnect to resume.',
      action: { tone: 'primary', label: 'Reconnect', action: 'connect' },
    }
  }
  return {
    group: 'Action required',
    message: 'The connection needs attention before it can be used.',
    action: { tone: 'primary', label: 'Resolve', action: 'connect' },
    detail: conn.last_error_sanitized || undefined,
  }
}
