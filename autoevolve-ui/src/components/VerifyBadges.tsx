import { useQuery } from '@tanstack/react-query'
import { useCredentials } from '../app/Auth'
import { verifyCompany } from '../api/companies'
import { StateBadge } from './Primitives'

/** Full verification facts for drawers. Same query as the badges. */
export function VerifyFacts({ domain, name }: { domain: string | null; name: string | null }) {
  const credentials = useCredentials()
  const verify = useQuery({
    queryKey: ['verify', domain, name],
    queryFn: () => verifyCompany(credentials, domain, name),
    staleTime: 60000, retry: false,
  })
  type Verification = {
    gleif: { legal_name: string | null; lei: string | null; country: string | null; status: string | null } | null
    web_presence: { captures: number | null; first_seen: string | null; last_seen: string | null; vintage: string | null } | null
    cached_profile: boolean
  }
  if (verify.isPending) return <p className="muted-copy">Checking registries…</p>
  const facts = verify.data as Verification | undefined
  if (!facts) return <p className="muted-copy">Verification unavailable.</p>
  return <dl className="company-fields">
    <div><dt>Registry</dt><dd>{facts.gleif ? `${facts.gleif.legal_name || 'Record found'}${facts.gleif.country ? ` · ${facts.gleif.country}` : ''}${facts.gleif.status ? ` · ${facts.gleif.status}` : ''}` : 'No registry record'}</dd></div>
    {facts.gleif?.lei && <div><dt>LEI</dt><dd>{facts.gleif.lei}</dd></div>}
    <div><dt>Web presence</dt><dd>{facts.web_presence ? `${facts.web_presence.captures ?? 0} captures${facts.web_presence.first_seen ? ` · since ${facts.web_presence.first_seen.slice(0, 4)}` : ''} (${facts.web_presence.vintage})` : 'No web record'}</dd></div>
    <div><dt>Enriched profile</dt><dd>{facts.cached_profile ? 'Saved' : 'Not resolved'}</dd></div>
  </dl>
}
export function VerifyBadges({ domain, name }: { domain: string | null; name: string | null }) {
  const credentials = useCredentials()
  const verify = useQuery({
    queryKey: ['verify', domain, name],
    queryFn: () => verifyCompany(credentials, domain, name),
    staleTime: 60000, retry: false,
  })
  type Verification = {
    gleif: { country: string | null } | null
    web_presence: { first_seen: string | null } | null
    cached_profile: boolean
  }
  const badge = verify.data as Verification | undefined
  const firstSeen = badge?.web_presence?.first_seen
  return <div className="verify-badges">
    {verify.isPending && <small>Checking registries…</small>}
    {badge && <>
      {badge.gleif
        ? <StateBadge tone="green">Registry{badge.gleif.country ? ` · ${badge.gleif.country}` : ''}</StateBadge>
        : <StateBadge tone="yellow">No registry record</StateBadge>}
      {badge.web_presence
        ? <StateBadge tone="green">Web{firstSeen ? ` since ${firstSeen.slice(0, 4)}` : ''}</StateBadge>
        : <StateBadge tone="neutral">No web record</StateBadge>}
      {badge.cached_profile && <StateBadge tone="blue">Enriched</StateBadge>}
    </>}
  </div>
}
