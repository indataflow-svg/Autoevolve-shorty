import { useEffect, useState } from 'react'
import { useQuery, useQueryClient } from '@tanstack/react-query'
import { useCredentials } from '../app/Auth'
import { AppShell } from '../components/Shell'
import type { CAccount } from '../api/commercial'
import { companyContext, setupTrigger } from '../api/companyContext'
import { CompanyDataDialog, saveCompanyContextAnswers } from '../components/CompanyDataCards'
import { SetupWizard } from './commercial/wizard'
import { AccountsSection } from './commercial/accounts'
import { IcpSection } from './commercial/icp'
import { PipelineSection } from './commercial/pipeline'
import { IntegrationsSection } from './commercial/integrations'

const TABS = ['Setup', 'Accounts', 'ICPs & Qualification', 'Pipeline', 'Integrations'] as const
type Tab = typeof TABS[number]

export function CommercialPage() {
  const credentials = useCredentials()
  const queryClient = useQueryClient()
  const [token, setToken] = useState('')
  const [tab, setTab] = useState<Tab>('Setup')
  const [presetAccount, setPresetAccount] = useState<CAccount | null>(null)
  const [dialogOpen, setDialogOpen] = useState(false)
  const [dismissed, setDismissed] = useState(false)
  const [saveState, setSaveState] = useState<{ busy: boolean; savedTick: number; error: string }>(
    { busy: false, savedTick: 0, error: '' })

  function qualifyFromAccounts(account: CAccount) {
    setPresetAccount(account)
    setTab('ICPs & Qualification')
  }

  const ctxView = useQuery({ queryKey: ['company-context'], queryFn: () => companyContext(credentials) })
  const trigger = setupTrigger(ctxView.data ?? null)
  const needsCards = trigger === 'fresh' || trigger === 'blocked'
  // The dialog pops on arrival while data is fresh or under the floor.
  // Dismissing closes it for this visit only: the trigger re-arms on refetch.
  useEffect(() => {
    if (!dismissed && needsCards) setDialogOpen(true)
  }, [needsCards, dismissed])

  async function saveCards(touched: Record<string, Record<string, string>>) {
    if (!token.trim()) { setSaveState(s => ({ ...s, error: 'Enter the founder action token first.' })); return }
    setSaveState(s => ({ ...s, busy: true, error: '' }))
    try {
      const updated = await saveCompanyContextAnswers(credentials, token, touched)
      queryClient.setQueryData(['company-context'], updated)
      setSaveState(s => ({ ...s, savedTick: s.savedTick + 1 }))
    } catch (reason) {
      setSaveState(s => ({ ...s, error: reason instanceof Error ? reason.message : 'Those answers were not saved.' }))
    } finally {
      setSaveState(s => ({ ...s, busy: false }))
    }
  }

  function closeDialog() {
    setDialogOpen(false)
    setDismissed(true)
  }

  return <AppShell active="Commercial" query="" onQueryChange={() => undefined}>
    <div className="page-layout"><main className="page-main"><div className="page-content validation-page cx-page">
      <div className="page-heading"><div>
        <p className="eyebrow">Commercial workspace</p>
        <h1>Customers, pipeline, and proof</h1>
        <p className="lede">One workspace for setup, accounts, qualification, pipeline, and integrations — every number from the backend, every action confirmed before it counts.</p>
      </div></div>
      <label className="onboarding-token">Founder action token
        <input type="password" autoComplete="off" aria-label="Founder action token" value={token} onChange={e => setToken(e.target.value)} />
        <small>Required to save anything. Held only in this page's memory.</small></label>
      <nav className="cx-tabs" aria-label="Commercial sections">
        {TABS.map(t => <button key={t} aria-current={tab === t ? 'page' : undefined}
          className={tab === t ? 'active' : ''} onClick={() => setTab(t)}>{t}</button>)}
      </nav>
      <div className="validation-actions">
        <button className="button secondary" onClick={() => { setDismissed(false); setDialogOpen(true) }}>Company data</button>
        {ctxView.data && <span className="operational-note">{ctxView.data.context.completeness_percent ?? 0}% complete{trigger === 'ready' ? ' · ready' : trigger === 'unknown' ? '' : ' · needs attention'}</span>}
      </div>
      {saveState.error && <p className="form-error" role="alert">{saveState.error}</p>}
      {dialogOpen && ctxView.data && <CompanyDataDialog
        view={ctxView.data} busy={saveState.busy} savedTick={saveState.savedTick} band={trigger === 'unknown' ? 'incomplete' : trigger}
        onClose={closeDialog} onSave={touched => void saveCards(touched)} />}
      {tab === 'Setup' && <SetupWizard credentials={credentials} token={token} />}
      {tab === 'Accounts' && <AccountsSection credentials={credentials} token={token} onQualify={qualifyFromAccounts} />}
      {tab === 'ICPs & Qualification' && <IcpSection credentials={credentials} token={token}
        presetAccount={presetAccount} onPresetConsumed={() => setPresetAccount(null)} />}
      {tab === 'Pipeline' && <PipelineSection credentials={credentials} token={token} />}
      {tab === 'Integrations' && <IntegrationsSection credentials={credentials} token={token} />}
    </div></main></div>
  </AppShell>
}
