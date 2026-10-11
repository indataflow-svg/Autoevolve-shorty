import { useState } from 'react'
import { useCredentials } from '../app/Auth'
import { AppShell } from '../components/Shell'
import type { CAccount } from '../api/commercial'
import { SetupWizard } from './commercial/wizard'
import { AccountsSection } from './commercial/accounts'
import { IcpSection } from './commercial/icp'
import { PipelineSection } from './commercial/pipeline'
import { IntegrationsSection } from './commercial/integrations'

const TABS = ['Setup', 'Accounts', 'ICPs & Qualification', 'Pipeline', 'Integrations'] as const
type Tab = typeof TABS[number]

export function CommercialPage() {
  const credentials = useCredentials()
  const [token, setToken] = useState('')
  const [tab, setTab] = useState<Tab>('Setup')
  const [presetAccount, setPresetAccount] = useState<CAccount | null>(null)

  function qualifyFromAccounts(account: CAccount) {
    setPresetAccount(account)
    setTab('ICPs & Qualification')
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
      {tab === 'Setup' && <SetupWizard credentials={credentials} token={token} />}
      {tab === 'Accounts' && <AccountsSection credentials={credentials} token={token} onQualify={qualifyFromAccounts} />}
      {tab === 'ICPs & Qualification' && <IcpSection credentials={credentials} token={token}
        presetAccount={presetAccount} onPresetConsumed={() => setPresetAccount(null)} />}
      {tab === 'Pipeline' && <PipelineSection credentials={credentials} token={token} />}
      {tab === 'Integrations' && <IntegrationsSection credentials={credentials} token={token} />}
    </div></main></div>
  </AppShell>
}
