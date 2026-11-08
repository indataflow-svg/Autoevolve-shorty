import { Link } from 'react-router-dom'
import { useQuery } from '@tanstack/react-query'
import type { Credentials } from '../../api/client'
import { commercialApi } from '../../api/commercial'
import { BenchmarkCard } from './wizard'

/** Score data in full, plus the process that sets it. */
export function ScoresTab({ credentials, onCompanyData }: {
  credentials: Credentials
  onCompanyData: () => void
}) {
  const api = commercialApi(credentials)
  const bench = useQuery({ queryKey: ['c-benchmarks', 100], queryFn: () => api.benchmarks(100) })
  const sent = bench.data?.recorded.sent ?? 0
  const pct = Math.min(100, Math.round((100 * sent) / 10))
  return <div className="cx-stack">
    <BenchmarkCard credentials={credentials} />
    <div className="cx-cards"><div className="cx-card">
      <h3>Set the scores</h3>
      <p className="cx-note">Scores sharpen as you record. Three moves raise them.</p>
      <div className="calibration-head">
        <p className="operational-note">{sent} of 10 sends recorded{bench.data?.market ? ` — ${bench.data.market.verdict} the world band` : ''}.</p>
      </div>
      <div className="onboarding-progressbar" role="progressbar" aria-valuenow={pct} aria-valuemin={0} aria-valuemax={100} aria-label="Sends recorded"><div style={{ width: `${pct}%` }} /></div>
      <div className="cx-card-actions">
        <Link className="button secondary" to="/outreach">Review outreach</Link>
        <button className="button secondary" onClick={onCompanyData}>Company data</button>
      </div>
      <p className="cx-note">Industry resolves itself from your validated ICP, else your top accounts — no form needed.</p>
    </div></div>
  </div>
}
