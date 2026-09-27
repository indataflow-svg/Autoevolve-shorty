import type { ReactNode } from 'react'
import { AlertCircle, ArrowDownRight, Ban, Building2, ContactRound, FileCheck2, MailCheck, Search, Send, UsersRound, X } from 'lucide-react'

export function MetricCard({ label, value, kind }: { label: string; value: number | undefined; kind: 'total' | 'ready' | 'verified' | 'suppressed' | 'companies' | 'candidates' | 'profiled' | 'contacts' }) {
  const icons = { total: ContactRound, ready: Send, verified: MailCheck, suppressed: Ban, companies: Building2, candidates: Search, profiled: FileCheck2, contacts: UsersRound }
  const Icon = icons[kind]
  return <div className={`metric-card ${kind}`}><span className="metric-icon"><Icon size={23} /></span><span className="metric-copy"><span className="metric-label">{label}</span><strong>{value === undefined ? <span className="skeleton metric-skeleton" /> : value.toLocaleString()}</strong></span></div>
}

export function StateBadge({ children, tone = 'neutral' }: { children: ReactNode; tone?: 'neutral' | 'green' | 'yellow' | 'red' | 'blue' }) {
  return <span className={`state-badge ${tone}`}>{children}</span>
}

export function DataState({ title, detail, retry }: { title: string; detail: string; retry?: () => void }) {
  return <div className="data-state"><AlertCircle size={25} /><h3>{title}</h3><p>{detail}</p>{retry && <button className="button secondary" onClick={retry}>Try again</button>}</div>
}

export function LoadingRows({ label = 'Loading contacts' }: { label?: string }) {
  return <div className="loading-rows" aria-label={label}>{Array.from({ length: 7 }, (_, index) => <div className="loading-row" key={index}><span className="skeleton short" /><span className="skeleton medium" /><span className="skeleton medium" /><span className="skeleton short" /><span className="skeleton medium" /></div>)}</div>
}

export function RightDrawer({ title, onClose, children, className = '' }: { title: string; onClose: () => void; children: ReactNode; className?: string }) {
  return <aside className={`right-drawer ${className}`} aria-label={title}>
    <button className="drawer-close icon-button" onClick={onClose} aria-label={`Close ${title.toLowerCase()}`}><X size={20} /></button>
    {children}
  </aside>
}

export function EmptyIcon() { return <ArrowDownRight size={26} /> }
