import { ArrowRight, CheckCircle2, Clock3, FileText, Send, Sparkles } from 'lucide-react'

import { marketingUrl } from '../app/marketing'

const sampleLoops = [
  { when: 'Today · 09:12', title: 'Coffee roastery launch', detail: 'Evidence → plan → webhook publish', state: 'Published' },
  { when: 'Yesterday · 16:40', title: 'Operations checklist', detail: 'Plan approved and simulated once', state: 'Simulated' },
  { when: 'Oct 27 · 11:05', title: 'ICP evidence refresh', detail: 'Company context completed to 86%', state: 'Evidence' },
]

/** Clearly-labelled sample data for the free plan; it never masks real records. */
export function FreePlanPreview() {
  return <section className="free-usage" aria-labelledby="free-usage-title">
    <div className="free-usage-heading">
      <div>
        <p className="free-usage-eyebrow"><Sparkles size={13} /> FREE PLAN · SAMPLE USAGE</p>
        <h2 id="free-usage-title">One honest loop a day.</h2>
        <p>An example of the free account rhythm: one plan, one simulation, one real publish, then the next decision.</p>
      </div>
      <span className="free-usage-badge">Example data</span>
    </div>
    <div className="free-usage-grid">
      <div className="free-usage-stat"><FileText /><span>Plan</span><strong>1 <small>/ 1</small></strong><em>Resets 00:00 UTC</em></div>
      <div className="free-usage-stat"><CheckCircle2 /><span>Run</span><strong>1 <small>/ 1</small></strong><em>Simulation only</em></div>
      <div className="free-usage-stat"><Send /><span>Publish</span><strong>1 <small>/ 1</small></strong><em>Your webhook</em></div>
      <div className="free-usage-stat"><Clock3 /><span>History</span><strong>30 <small>days</small></strong><em>Loop records</em></div>
    </div>
    <div className="free-usage-history">
      {sampleLoops.map(loop => <div key={loop.title} className="free-usage-loop">
        <span>{loop.when}</span>
        <strong>{loop.title}</strong>
        <small>{loop.detail}</small>
        <em>{loop.state}</em>
      </div>)}
    </div>
    <div className="free-usage-footer">
      <small>This is illustrative sample data. Your signed-in workspace starts with its own records.</small>
      <a href={marketingUrl()} target="_blank" rel="noreferrer">Upgrade <ArrowRight size={14} /></a>
    </div>
  </section>
}
