import { useQuery } from '@tanstack/react-query'
import { Activity, ArrowRight, Building2, Compass, ContactRound, FileImage, Mail, Megaphone, ShieldAlert } from 'lucide-react'
import { Link } from 'react-router-dom'
import { homeView } from '../api/workflows'
import { useCredentials } from '../app/Auth'
import { AppShell } from '../components/Shell'
import { DataState, LoadingRows } from '../components/Primitives'
import { ShortDate, StatusText, WorkflowMetrics } from '../components/WorkflowTable'

const campaignStatuses = ['queued', 'running', 'needs_campaign_review', 'needs_voice_recording', 'variants_ready', 'selected', 'drafting', 'drafted', 'failed']

export function HomePage() {
  const credentials = useCredentials()
  const query = useQuery({ queryKey: ['home'], queryFn: () => homeView(credentials) })
  const data = query.data
  return <AppShell active="Home" query="" onQueryChange={() => undefined}><div className="page-layout"><main className="page-main"><div className="page-content home-page">
    <div className="page-heading"><div><h1>Home</h1><p>Work that needs attention{data?.active_org_name ? ` · Active organization: ${data.active_org_name}` : ''}</p></div><div className="heading-actions"><Link to="/research" className="button primary">Run research <ArrowRight size={16} /></Link></div></div>
    {query.isError && data && <div className="operational-error" role="alert">Refresh failed: {query.error.message} <button onClick={() => query.refetch()}>Retry</button></div>}
    {query.isPending ? <LoadingRows label="Loading home" /> : query.isError && !data ? <DataState title="Home could not be loaded" detail={query.error.message} retry={() => query.refetch()} /> : data && <>
      <WorkflowMetrics items={[{ label: 'Drafts to review', value: data.drafts_waiting_approval, icon: <Mail /> }, { label: 'Campaigns to review', value: data.campaigns_awaiting_review, icon: <Megaphone /> }, { label: 'Latest replies', value: data.latest_replies, icon: <Activity /> }, { label: 'Open incidents', value: data.open_provider_incidents, icon: <ShieldAlert /> }]} />
      <div className="home-alerts">
        {data.routing_error
          ? <div className="home-stage warning"><ShieldAlert size={18} /><span><strong>Starting state not recognised</strong><small>{data.routing_error}</small></span></div>
          : data.next_stage && <div className="home-stage"><Compass size={18} /><span><strong>{data.route_label}</strong><small>{data.route_summary}</small></span></div>}
        {data.onboarding_status !== 'activated' && <Link to="/onboarding" className="home-alert"><Building2 size={18} /><span><strong>Finish first-run setup</strong><small>Resume the saved company, strategy, and calibration steps</small></span><ArrowRight size={17} /></Link>}
        {data.drafts_waiting_approval > 0 && <Link to="/outreach?status=draft" className="home-alert"><Mail size={18} /><span><strong>{data.drafts_waiting_approval} drafts awaiting review</strong><small>Approve only after checking claims and recipient</small></span><ArrowRight size={17} /></Link>}
        {data.campaigns_awaiting_review > 0 && <Link to="/campaigns?status=needs_campaign_review" className="home-alert"><Megaphone size={18} /><span><strong>{data.campaigns_awaiting_review} campaigns awaiting review</strong><small>Review the generated campaign before advancing it</small></span><ArrowRight size={17} /></Link>}
        {data.latest_replies > 0 && <Link to="/replies?view=latest" className="home-alert"><Activity size={18} /><span><strong>{data.latest_replies} latest inbound replies</strong><small>Read the reply before drafting a response</small></span><ArrowRight size={17} /></Link>}
        {data.outreach_approved_total > 0 && <Link to="/outreach?status=approved" className="home-alert"><Mail size={18} /><span><strong>{data.outreach_approved_total} approved email drafts</strong><small>Review before sending</small></span><ArrowRight size={17} /></Link>}
        {data.outreach_unknown_total > 0 && <Link to="/outreach?status=send_unknown" className="home-alert warning"><ShieldAlert size={18} /><span><strong>{data.outreach_unknown_total} sends need reconciliation</strong><small>Do not retry until provider status is known</small></span><ArrowRight size={17} /></Link>}
        {data.open_provider_incidents > 0 && <Link to="/integrations?view=incidents" className="home-alert warning"><ShieldAlert size={18} /><span><strong>{data.open_provider_incidents} open service incidents</strong><small>Inspect saved incident records</small></span><ArrowRight size={17} /></Link>}
        {data.onboarding_status === 'activated' && !data.drafts_waiting_approval && !data.campaigns_awaiting_review && !data.latest_replies && !data.outreach_approved_total && !data.outreach_unknown_total && !data.open_provider_incidents && <p className="home-empty">No saved work currently needs review.</p>}
      </div>
      <div className="home-grid"><section className="home-panel"><div className="home-panel-heading"><h2>Recent contacts</h2><Link to="/contacts">View all <ArrowRight size={15} /></Link></div>{data.recent_contacts.length ? data.recent_contacts.map(contact => <Link key={contact.id} to={`/contacts?contact=${encodeURIComponent(contact.id || '')}`} className="home-record"><span className="home-record-icon"><ContactRound size={17} /></span><span><strong>{contact.full_name || 'Name not recorded'}</strong><small>{contact.company || 'Company not recorded'} · {contact.stage || 'Stage not recorded'}</small></span><ShortDate value={contact.updated_at} /></Link>) : <p className="home-empty">No contacts yet. Research can discover company candidates and leads.</p>}</section>
      <section className="home-panel"><div className="home-panel-heading"><h2>Recent campaigns</h2><Link to="/campaigns">View all <ArrowRight size={15} /></Link></div>{data.recent_campaigns.length ? data.recent_campaigns.map(campaign => <Link key={campaign.id} to={`/campaigns?campaign=${encodeURIComponent(campaign.id)}`} className="home-record"><span className="home-record-icon"><Megaphone size={17} /></span><span><strong>{campaign.topic}</strong><small>{campaign.org_name || 'Organization unavailable'} · {campaign.current_stage.replaceAll('_', ' ')}</small></span><StatusText value={campaign.status} known={campaignStatuses} tone={campaign.status === 'failed' ? 'red' : 'blue'} /></Link>) : <p className="home-empty">No campaigns yet. Create one after choosing an active organization.</p>}</section></div>
      <div className="home-shortcuts"><Link to="/companies"><Building2 size={18} /> Companies <ArrowRight size={15} /></Link><Link to="/outreach"><Mail size={18} /> Outreach <ArrowRight size={15} /></Link><Link to="/content"><FileImage size={18} /> Content <ArrowRight size={15} /></Link></div>
    </>}
  </div></main></div></AppShell>
}
