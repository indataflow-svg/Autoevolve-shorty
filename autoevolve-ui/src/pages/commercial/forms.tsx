/** Lead forms: hosted pages at /f/{slug} plus the shared external endpoint. */
import { useState, type FormEvent } from 'react'
import { useQuery, useQueryClient } from '@tanstack/react-query'
import { Copy, ExternalLink, Plus, X } from 'lucide-react'
import { useCredentials } from '../../app/Auth'
import { commercialApi, commercialWrite } from '../../api/commercial'
import { Empty, Section } from './shared'

type FormField = { key: string; label: string; type: string; required: boolean; options?: string[] }
type LeadForm = { slug: string; name: string; description: string | null; fields: FormField[]; active: boolean; hosted_path: string; external_endpoint: string }

const FIELD_TYPES = ['text', 'email', 'tel', 'url', 'textarea', 'select', 'checkbox', 'hidden'] as const

function CopyButton({ value, label, absolute = true }: { value: string; label: string; absolute?: boolean }) {
  const [copied, setCopied] = useState(false)
  // absolute: prepend the page origin (for our own paths). Full URLs (server-
  // computed endpoint, the secret) are copied exactly as given.
  const text = absolute ? `${window.location.origin}${value}` : value
  return <button className="button secondary" onClick={() => { void navigator.clipboard.writeText(text).then(() => { setCopied(true); setTimeout(() => setCopied(false), 1600) }) }}>
    {copied ? 'Copied' : <><Copy size={14} /> {label}</>}
  </button>
}

function CreateFormDialog({ close, created }: { close: () => void; created: () => Promise<void> }) {
  const credentials = useCredentials()
  const [slug, setSlug] = useState('')
  const [name, setName] = useState('')
  const [description, setDescription] = useState('')
  const [fields, setFields] = useState<FormField[]>([
    { key: 'full_name', label: 'Full name', type: 'text', required: true },
    { key: 'email', label: 'Work email', type: 'email', required: true },
    { key: 'company', label: 'Company', type: 'text', required: false },
    { key: 'message', label: 'What are you looking for?', type: 'textarea', required: false },
  ])
  const [token, setToken] = useState('')
  const [error, setError] = useState('')
  const [pending, setPending] = useState(false)

  function setField(index: number, patch: Partial<FormField>) {
    setFields(current => current.map((field, i) => (i === index ? { ...field, ...patch } : field)))
  }

  async function submit(event: FormEvent<HTMLFormElement>) {
    event.preventDefault(); setError('')
    const cleanSlug = slug.trim().toLowerCase()
    if (!/^[a-z0-9][a-z0-9-]*[a-z0-9]$|^[a-z0-9]$/.test(cleanSlug)) { setError('Slug must be lowercase letters, digits, and hyphens.'); return }
    if (!name.trim()) { setError('Give the form a name.'); return }
    if (!fields.length) { setError('Add at least one field.'); return }
    if (!token.trim()) { setError('Enter the founder action token.'); return }
    setPending(true)
    try {
      const w = commercialWrite(credentials, token)
      await w.createForm({ slug: cleanSlug, name: name.trim(), description: description.trim() || undefined, fields })
      await created()
      close()
    } catch (reason) { setError(reason instanceof Error ? reason.message : 'Form could not be created.') }
    finally { setPending(false) }
  }

  return <div className="modal-backdrop" role="presentation"><div className="modal" role="dialog" aria-modal="true" aria-label="Create form"><button className="modal-close icon-button" onClick={close} aria-label="Close create form"><X size={19} /></button><h2>Create form</h2><p>The form gets a public page at its slug. External tools can post to the shared endpoint with the same slug.</p><form onSubmit={submit}>
    <label>Name<input value={name} onChange={event => { setName(event.target.value); if (!slug) setSlug(event.target.value.toLowerCase().replace(/[^a-z0-9]+/g, '-').replace(/^-|-$/g, '')) }} placeholder="Book a demo" required /></label>
    <label>Slug<input value={slug} onChange={event => setSlug(event.target.value.toLowerCase())} placeholder="book-a-demo" required /></label>
    <label>Description (optional)<input value={description} onChange={event => setDescription(event.target.value)} maxLength={400} /></label>
    <div className="cx-field"><span>Fields</span>
      {fields.map((field, index) => <div key={index} className="cx-form-row">
        <input value={field.label} onChange={event => setField(index, { label: event.target.value })} placeholder="Label" aria-label={`Field ${index + 1} label`} />
        <input value={field.key} onChange={event => setField(index, { key: event.target.value.toLowerCase().replace(/[^a-z0-9_]/g, '_') })} placeholder="key" aria-label={`Field ${index + 1} key`} />
        <select value={field.type} onChange={event => setField(index, { type: event.target.value })} aria-label={`Field ${index + 1} type`}>{FIELD_TYPES.map(type => <option key={type} value={type}>{type}</option>)}</select>
        <label className="cx-form-required"><input type="checkbox" checked={field.required} onChange={event => setField(index, { required: event.target.checked })} /> req</label>
        <button type="button" className="icon-button" aria-label={`Remove field ${index + 1}`} onClick={() => setFields(current => current.filter((_, i) => i !== index))}><X size={15} /></button>
      </div>)}
      <button type="button" className="button secondary" onClick={() => setFields(current => [...current, { key: '', label: '', type: 'text', required: false }])}><Plus size={14} /> Add field</button>
      <small>Keys: name, email, company, phone, message map onto the contact record. Anything else is kept as a clean answer.</small>
    </div>
    <label>Founder action token<input type="password" autoComplete="off" value={token} onChange={event => setToken(event.target.value)} required /></label>
    {error && <p className="form-error" role="alert">{error}</p>}
    <div className="modal-actions"><button type="button" className="button secondary" onClick={close}>Cancel</button><button className="button primary" disabled={pending}>{pending ? 'Creating…' : 'Create form'}</button></div>
  </form></div></div>
}

export function FormsSection({ credentials, token }: { credentials: ReturnType<typeof useCredentials>; token: string }) {
  const queryClient = useQueryClient()
  const api = commercialApi(credentials)
  const [creating, setCreating] = useState(false)
  const [toggling, setToggling] = useState<string | null>(null)
  const [error, setError] = useState('')
  const list = useQuery({ queryKey: ['c-forms'], queryFn: api.forms })
  const config = useQuery({ queryKey: ['c-forms-config'], queryFn: api.formsConfig })

  async function toggle(form: LeadForm) {
    if (!token.trim()) { setError('Enter the founder action token at the top of the page first.'); return }
    setError(''); setToggling(form.slug)
    try {
      await api.updateForm(form.slug, { active: !form.active }, token)
      await queryClient.invalidateQueries({ queryKey: ['c-forms'] })
    } catch (reason) { setError(reason instanceof Error ? reason.message : 'Form could not be updated.') }
    finally { setToggling(null) }
  }

  const forms = list.data || []
  return <Section title="Lead forms" intro="A hosted page you can link anywhere, plus one endpoint any external form tool can post to. Submissions arrive in Replies as clean answers with the meeting action attached." action={<button className="button primary" onClick={() => setCreating(true)}><Plus size={15} /> Create form</button>}>
    {error && <p className="form-error" role="alert">{error}</p>}
    {config.data && <div className="cx-endpoint">
      <h3>Connect an external form tool</h3>
      <p className="cx-note">Paste the endpoint into your tool's POST/webhook target, then include the form's slug in the payload (see each form below). The secret is only required when this instance has one set.</p>
      <div className="cx-endpoint-row">
        <code>{config.data.endpoint_url}</code>
        <CopyButton value={config.data.endpoint_url} label="Copy endpoint URL" absolute={false} />
      </div>
      <div className="cx-endpoint-row">
        <span className="cx-endpoint-key">{config.data.secret_header}:</span>
        {config.data.secret_configured && config.data.secret
          ? <><code>{config.data.secret}</code><CopyButton value={config.data.secret} label="Copy secret" absolute={false} /></>
          : <span className="cx-note">not set — the endpoint accepts posts without a secret</span>}
      </div>
    </div>}
    {list.isPending ? <p className="cx-note">Loading forms…</p>
      : forms.length ? <ul className="cx-cards">{forms.map(form =>
        <li key={form.slug} className="cx-card">
          <div><strong>{form.name}</strong> <code>/f/{form.slug}</code> {!form.active && <span className="cx-note">· inactive</span>}</div>
          {form.description && <p>{form.description}</p>}
          <p className="cx-note">{form.fields.length} fields: {form.fields.map(field => field.label).join(', ')}</p>
          <div className="cx-card-actions">
            <CopyButton value={form.hosted_path} label="Copy page URL" />
            <a className="button secondary" href={form.hosted_path} target="_blank" rel="noreferrer"><ExternalLink size={14} /> Open page</a>
            <button className="button secondary" disabled={toggling !== null} onClick={() => void toggle(form)}>{toggling === form.slug ? 'Working…' : form.active ? 'Deactivate' : 'Activate'}</button>
          </div>
          <details open><summary>External POST payload</summary>
            <p>POST to the endpoint above with JSON <code>{`{"form": "${form.slug}", "answers": {"email": "...", ...}}`}</code>{' '}or form-encoded fields plus <code>form={form.slug}</code>.</p>
          </details>
        </li>)}</ul>
      : <Empty title="No forms yet" detail="Create a form to collect submissions that land in Replies." action={<button className="button primary" onClick={() => setCreating(true)}><Plus size={15} /> Create form</button>} />}
    {creating && <CreateFormDialog close={() => setCreating(false)} created={async () => { await queryClient.invalidateQueries({ queryKey: ['c-forms'] }) }} />}
  </Section>
}
