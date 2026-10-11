/** Integration catalog grouped by what the user can do — not by implementation. */
import { useState } from 'react'
import { useQuery, useQueryClient } from '@tanstack/react-query'
import type { Credentials } from '../../api/client'
import { commercialApi, commercialWrite } from '../../api/commercial'
import { StateBadge } from '../../components/Primitives'
import { Empty, Section } from './shared'
import { integrationPresentation } from './helpers'

const GROUPS = ['Available', 'Connected', 'Action required', 'Coming soon'] as const

export function IntegrationsSection({ credentials, token }: { credentials: Credentials; token: string }) {
  const queryClient = useQueryClient()
  const api = commercialApi(credentials)
  const [error, setError] = useState('')
  const [busy, setBusy] = useState<string | null>(null)
  const list = useQuery({ queryKey: ['c-integrations'], queryFn: api.integrations })

  async function act(provider: string, action: 'connect' | 'sync' | 'disconnect', label: string) {
    if (!token.trim()) { setError('Enter the founder action token at the top of the page first.'); return }
    setError(''); setBusy(provider)
    try {
      const w = commercialWrite(credentials, token)
      if (action === 'connect') await w.connect(provider, {})
      else if (action === 'sync') await w.sync(provider)
      else await w.disconnect(provider)
      await queryClient.invalidateQueries({ queryKey: ['c-integrations'] })
    } catch (e) { setError(e instanceof Error ? e.message : `${label} failed.`) }
    finally { setBusy(null) }
  }

  const items = (list.data || []).map(integrationPresentation).map((p, i) => ({ ...p, item: (list.data || [])[i] }))
  return <Section title="Integrations" intro="States come from the backend and provider checks. A connection is never marked successful because a button was clicked.">
    {error && <p className="form-error" role="alert">{error}</p>}
    {list.isPending ? <p className="cx-note">Loading integrations…</p>
      : GROUPS.map(g => {
        const rows = items.filter(r => r.group === g)
        if (rows.length === 0) return null
        return <div key={g}><h3 className="cx-group">{g} ({rows.length})</h3>
          <ul className="cx-cards">{rows.map(r =>
            <li key={r.item.provider} className="cx-card">
              <div><strong>{r.item.label}</strong>
                {r.item.connection && <span> · <StateBadge tone={r.item.connection.status === 'healthy' ? 'green' : 'yellow'}>{r.item.connection.status.replaceAll('_', ' ')}</StateBadge>
                  <small>sync: {r.item.connection.sync_status.replaceAll('_', ' ')}</small></span>}</div>
              <p>{r.message}</p>
              {r.detail && <details><summary>Technical detail</summary><p>{r.detail}</p></details>}
              <div className="cx-card-actions">
                {r.action.action !== 'none' && <button
                  className={`button ${r.action.tone === 'primary' ? 'primary' : 'secondary'}`}
                  disabled={busy !== null}
                  onClick={() => void act(r.item.provider, r.action.action as 'connect' | 'sync', r.action.label)}>
                  {busy === r.item.provider ? 'Working…' : r.action.label}</button>}
                {r.group === 'Connected' && <button className="button secondary" disabled={busy !== null}
                  onClick={() => { if (window.confirm(`Disconnect ${r.item.label}? Local history is kept.`)) void act(r.item.provider, 'disconnect', 'Disconnect') }}>Disconnect</button>}
              </div>
            </li>)}</ul></div>
      })}
    {items.length === 0 && !list.isPending && <Empty title="No providers listed" detail="The catalog could not be loaded." />}
  </Section>
}
