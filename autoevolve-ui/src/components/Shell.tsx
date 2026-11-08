import { useState } from 'react'
import type { ReactNode } from 'react'
import { useAuthSession, usePlan } from '../app/Auth'
import { marketingUrl } from '../app/marketing'
import { Link } from 'react-router-dom'
import { Activity, ArrowUpRight, Bell, Building2, CalendarDays, Compass, ContactRound, FileText, Home, LockKeyhole, Menu, PlugZap, Search, Send, Settings2, Sparkles, Target, X } from 'lucide-react'

const lockedForFree = new Set(['Outreach', 'Replies', 'Meetings', 'Research'])

const navigation = [
  { label: 'Get started', icon: Sparkles, href: '/onboarding' },
  { label: 'Home', icon: Home, href: '/home' },
  { label: 'Workflows', icon: Compass, href: '/workflows' },
  { label: 'Companies', icon: Building2, href: '/companies' },
  { label: 'Contacts', icon: ContactRound, href: '/contacts' },
  { label: 'Outreach', icon: Send, href: '/outreach' },
  { label: 'Replies', icon: Activity, href: '/replies' },
  { label: 'Meetings', icon: CalendarDays, href: '/meetings' },
  { label: 'Content', icon: FileText, href: '/content' },
  { label: 'Research', icon: Search, href: '/research' },
  { label: 'Integrations', icon: PlugZap, href: '/integrations' },
  { label: 'Commercial', icon: Target, href: '/commercial' },
  { label: 'Settings', icon: Settings2, href: '/settings' },
]

export function AppShell({ children, query, onQueryChange, active }: { children: ReactNode; query: string; onQueryChange: (value: string) => void; active?: 'Onboarding' | 'Home' | 'Workflows' | 'Contacts' | 'Companies' | 'Research' | 'Outreach' | 'Replies' | 'Meetings' | 'Content' | 'Integrations' | 'Commercial' | 'Settings' }) {
  const [menuOpen, setMenuOpen] = useState(false)
  const session = useAuthSession()
  const plan = usePlan()
  const visibleNavigation = session ? navigation.filter(item => item.label !== 'Integrations') : navigation
  const closeMenu = () => setMenuOpen(false)
  return <div className="app-shell">
    <aside className="sidebar" aria-label="Main navigation">
      <div className="brand"><span className="brand-mark">A</span><span>Auto<span>Evolve</span></span></div>
      <button
        type="button"
        className="mobile-menu-button"
        aria-label={menuOpen ? 'Close navigation menu' : 'Open navigation menu'}
        aria-expanded={menuOpen}
        aria-controls="app-nav"
        onClick={() => setMenuOpen(value => !value)}
      >{menuOpen ? <X size={22} /> : <Menu size={22} />}</button>
      <nav id="app-nav" className={`nav-list${menuOpen ? ' open' : ''}`}>
        {visibleNavigation.map(({ label, icon: Icon, href }) => {
          const locked = plan === 'free' && lockedForFree.has(label)
          const className = `nav-item ${(label === 'Get started' ? active === 'Onboarding' : label === active) ? 'active' : ''}${locked ? ' locked' : ''} core-page`
          const content = <><Icon size={19} />{label}{locked && <LockKeyhole size={13} className="nav-lock" aria-label="Paid feature" />}</>
          return <Link key={label} to={href} className={className} onClick={closeMenu} aria-current={(label === 'Get started' ? active === 'Onboarding' : label === active) ? 'page' : undefined} title={locked ? 'Paid workspace feature — upgrade to unlock' : undefined}>{content}</Link>
        })}
      </nav>
      <div className="sidebar-user"><span className="avatar">F</span><span>Founder<small>{plan === 'free' ? 'Free plan' : 'Admin'}</small></span></div>
      {plan === 'free' && <a className="sidebar-upgrade" href={marketingUrl()} target="_blank" rel="noreferrer">Upgrade <ArrowUpRight size={13} /></a>}
    </aside>
    {menuOpen && <div className="mobile-nav-backdrop" onClick={closeMenu} aria-hidden="true" />}
    <div className="workspace">
      <header className="topbar">
        {!active || active === 'Settings' || active === 'Home' || active === 'Onboarding' || active === 'Workflows' ? <div className="global-search global-search-inactive"><Search size={18} /><span>Search contacts, companies, outreach, replies, and content from their pages</span></div> : <label className="global-search"><Search size={18} /><span className="sr-only">Search {active.toLowerCase()}</span><input value={query} onChange={event => onQueryChange(event.target.value)} placeholder={active === 'Contacts' ? 'Search contacts, companies, or roles…' : active === 'Integrations' ? 'Search integrations…' : active === 'Outreach' ? 'Search drafts, contacts, or subjects…' : active === 'Replies' ? 'Search replies…' : active === 'Meetings' ? 'Search meeting records…' : active === 'Content' ? 'Search content…' : 'Search companies, industries, or countries…'} maxLength={200} /></label>}
        <div className="topbar-end"><Bell size={19} aria-label="Notifications" /><span className="avatar top-avatar" aria-label="Founder">F</span></div>
      </header>
      {children}
    </div>
  </div>
}
