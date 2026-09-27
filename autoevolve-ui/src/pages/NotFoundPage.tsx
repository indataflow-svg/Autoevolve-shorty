import { Link } from 'react-router-dom'
import { AppShell } from '../components/Shell'

export function NotFoundPage() {
  return <AppShell query="" onQueryChange={() => undefined}>
    <div className="page-layout"><main className="page-main"><div className="page-content">
      <div className="page-heading"><div><h1>Page not found</h1><p>This address does not match an AutoEvolve page.</p></div></div>
      <Link to="/home" className="button primary">Go to Home</Link>
    </div></main></div>
  </AppShell>
}
