import type { ReactNode } from 'react'
import { Link } from 'react-router-dom'
import { Activity, Bell, Building2, CalendarDays, ContactRound, FileText, Home, Megaphone, PlugZap, Search, Send, Settings2, Sparkles } from 'lucide-react'

const navigation = [
  { label: 'Get started', icon: Sparkles, href: '/onboarding' },
  { label: 'Home', icon: Home, href: '/home' },
  { label: 'Companies', icon: Building2, href: '/companies' },
  { label: 'Contacts', icon: ContactRound, href: '/contacts' },
  { label: 'Outreach', icon: Send, href: '/outreach' },
  { label: 'Replies', icon: Activity, href: '/replies' },
  { label: 'Meetings', icon: CalendarDays, href: '/meetings' },
  { label: 'Campaigns', icon: Megaphone, href: '/campaigns' },
  { label: 'Content', icon: FileText, href: '/content' },
  { label: 'Research', icon: Search, href: '/research' },
  { label: 'Integrations', icon: PlugZap, href: '/integrations' },
  { label: 'Settings', icon: Settings2, href: '/settings' },
]

export function AppShell({ children, query, onQueryChange, active }: { children: ReactNode; query: string; onQueryChange: (value: string) => void; active?: 'Onboarding' | 'Home' | 'Contacts' | 'Companies' | 'Research' | 'Outreach' | 'Replies' | 'Meetings' | 'Campaigns' | 'Content' | 'Integrations' | 'Settings' }) {
  return <div className="app-shell">
    <aside className="sidebar" aria-label="Main navigation">
      <div className="brand"><span className="brand-mark">A</span><span>Auto<span>Evolve</span></span></div>
      <nav className="nav-list">
        {navigation.map(({ label, icon: Icon, href }) => {
          const className = `nav-item ${(label === 'Get started' ? active === 'Onboarding' : label === active) ? 'active' : ''} core-page`
          const content = <><Icon size={19} />{label}</>
          return <Link key={label} to={href} className={className} aria-current={(label === 'Get started' ? active === 'Onboarding' : label === active) ? 'page' : undefined}>{content}</Link>
        })}
      </nav>
      <div className="sidebar-user"><span className="avatar">F</span><span>Founder<small>Admin</small></span></div>
    </aside>
    <div className="workspace">
      <header className="topbar">
        {!active || active === 'Settings' || active === 'Home' || active === 'Onboarding' ? <div className="global-search global-search-inactive"><Search size={18} /><span>Search contacts, companies, outreach, campaigns, and content from their pages</span></div> : <label className="global-search"><Search size={18} /><span className="sr-only">Search {active.toLowerCase()}</span><input value={query} onChange={event => onQueryChange(event.target.value)} placeholder={active === 'Contacts' ? 'Search contacts, companies, or roles…' : active === 'Integrations' ? 'Search integrations…' : active === 'Outreach' ? 'Search drafts, contacts, or subjects…' : active === 'Replies' ? 'Search replies…' : active === 'Meetings' ? 'Search meeting records…' : active === 'Campaigns' ? 'Search campaigns or objectives…' : active === 'Content' ? 'Search content…' : 'Search companies, industries, or countries…'} maxLength={200} /></label>}
        <div className="topbar-end"><Bell size={19} aria-label="Notifications" /><span className="avatar top-avatar" aria-label="Founder">F</span></div>
      </header>
      {children}
    </div>
  </div>
}
