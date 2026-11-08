import type { ComponentProps, ReactNode } from 'react'
import { ArrowRight, Check, LockKeyhole, Sparkles } from 'lucide-react'
import { Link } from 'react-router-dom'

import { marketingUrl } from './marketing'
import { usePlan } from './Auth'
import { AppShell } from '../components/Shell'
import { StateBadge } from '../components/Primitives'

type Active = ComponentProps<typeof AppShell>['active']

const previewRows = [
  { name: 'Amina Okafor', company: 'Northstar Logistics', state: 'Ready to review' },
  { name: 'Daniel Mwangi', company: 'Rift Dynamics', state: 'Draft prepared' },
  { name: 'Sofia Almeida', company: 'Greenwheels Africa', state: 'Replied' },
  { name: 'Peter Njoroge', company: 'Chloride Exide', state: 'Meeting requested' },
]

/** Route-level upgrade boundary: free accounts see a blurred preview, never a dead API page. */
export function LockedRoute({ active, title, description, children }: {
  active: Active
  title: string
  description: string
  children: ReactNode
}) {
  const plan = usePlan()
  if (plan !== 'free') return <>{children}</>
  return <AppShell active={active} query="" onQueryChange={() => undefined}>
    <div className="page-layout"><main className="page-main"><div className="page-content">
      <div className="page-heading"><div><h1>{title}</h1><p>{description}</p></div><StateBadge tone="yellow">Free plan</StateBadge></div>
      <div className="upgrade-stage">
        <div className="upgrade-preview" aria-hidden="true">
          <div className="upgrade-preview-metrics">
            {['Weekly signal', 'Qualified accounts', 'Drafts waiting', 'Reply rate'].map((label, index) => <div key={label}><span>{label}</span><strong>{[18, 12, 4, '7.4%'][index]}</strong><small>Sample preview</small></div>)}
          </div>
          <div className="upgrade-preview-table">
            <div className="upgrade-preview-row upgrade-preview-header"><span>Contact</span><span>Company</span><span>State</span></div>
            {previewRows.map(row => <div className="upgrade-preview-row" key={row.name}><span>{row.name}</span><span>{row.company}</span><span>{row.state}</span></div>)}
          </div>
        </div>
        <div className="upgrade-overlay">
          <div className="upgrade-card">
            <span className="upgrade-icon"><LockKeyhole size={23} /></span>
            <p className="upgrade-eyebrow"><Sparkles size={13} /> PAID WORKSPACE</p>
            <h2>{title} is part of the full AutoEvolve loop.</h2>
            <p>{description} Your free workspace keeps the daily evidence, plan, simulation, and one real publish.</p>
            <ul>
              <li><Check size={15} /> Real cold outreach and reply handling</li>
              <li><Check size={15} /> Deeper provider research and more loops</li>
              <li><Check size={15} /> More channels, organizations, and history</li>
            </ul>
            <a className="button primary" href={marketingUrl()} target="_blank" rel="noreferrer">Upgrade <ArrowRight size={16} /></a>
            <p className="upgrade-note">Opens the Book a demo form on the main site.</p>
            <Link className="upgrade-back" to="/home">Back to the free loop</Link>
          </div>
        </div>
      </div>
    </div></main></div>
  </AppShell>
}
