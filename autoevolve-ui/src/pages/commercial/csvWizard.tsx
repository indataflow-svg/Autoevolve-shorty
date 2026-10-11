/** Guided CSV import: file → preview → mapping → duplicates → confirm → results. */
import { useState } from 'react'
import { useQueryClient } from '@tanstack/react-query'
import type { Credentials } from '../../api/client'
import { commercialWrite, previewImport, type ImportPreview } from '../../api/commercial'
import { Dialog, Empty, Field, Stepper } from './shared'

const CANONICAL = ['company_name', 'domain', 'email', 'full_name', 'job_title', 'industry', 'company_size', 'region', 'phone', 'country', 'source']
const STEPS = ['Select file', 'Preview', 'Map columns', 'Review', 'Confirm', 'Results']

type Result = { totals: Record<string, number>; errors: Array<{ row: number; error: string }> }

export function CsvWizard({ credentials, token, onClose }: {
  credentials: Credentials; token: string; onClose: () => void
}) {
  const queryClient = useQueryClient()
  const [step, setStep] = useState(0)
  const [file, setFile] = useState<File | null>(null)
  const [preview, setPreview] = useState<ImportPreview | null>(null)
  const [mapping, setMapping] = useState<Record<string, string>>({})
  const [mode, setMode] = useState('create_only')
  const [skipRows, setSkipRows] = useState('')
  const [result, setResult] = useState<Result | null>(null)
  const [error, setError] = useState('')
  const [busy, setBusy] = useState(false)

  async function doPreview() {
    if (!file) { setError('Choose a .csv file first.'); return }
    setError(''); setBusy(true)
    try {
      const p = await previewImport(credentials, token, 'account', file)
      setPreview(p)
      setMapping(p.suggested_mapping)
      setStep(1)
    } catch (e) { setError(e instanceof Error ? e.message : 'Preview failed.') }
    finally { setBusy(false) }
  }

  async function doCommit() {
    if (!preview) return
    setError(''); setBusy(true)
    try {
      const skip_rows = skipRows.split(',').map(s => parseInt(s.trim(), 10)).filter(n => Number.isFinite(n))
      const out = await commercialWrite(credentials, token).commitImport(preview.import_id, { mapping, skip_rows, mode }) as Result
      setResult(out)
      await queryClient.invalidateQueries({ queryKey: ['c-accounts'] })
      await queryClient.invalidateQueries({ queryKey: ['c-imports'] })
      setStep(5)
    } catch (e) { setError(e instanceof Error ? e.message : 'Import failed.') }
    finally { setBusy(false) }
  }

  return <Dialog wide title="Import accounts from CSV" intro="Upload a .csv file (max 2 MB, 2,000 rows, UTF-8). Nothing is saved until you confirm." onClose={onClose}>
    <Stepper steps={STEPS} current={step} />
    {error && <p className="form-error" role="alert">{error}</p>}
    {step === 0 && <div className="cx-form">
      <Field label="CSV file" hint="Headers in the first row. Required: company name. Recognised: domain, email, contact name, title, industry, size, region, phone, country.">
        <input type="file" accept=".csv" aria-label="CSV file" onChange={e => setFile(e.target.files?.[0] || null)} />
      </Field>
      {file && <p className="cx-note">{file.name} · {(file.size / 1024).toFixed(1)} KB</p>}
      <div className="modal-actions"><button className="button secondary" onClick={onClose}>Cancel</button>
        <button className="button primary" disabled={busy || !file} onClick={() => void doPreview()}>{busy ? 'Reading…' : 'Preview records'}</button></div>
    </div>}
    {step === 1 && preview && <div>
      <p className="cx-note">{preview.totals.rows} rows · {preview.totals.exact_duplicates} exact duplicates · {preview.totals.ambiguous} need review · {preview.totals.to_create} to create</p>
      <table className="cx-table"><thead><tr>{preview.headers.map(h => <th key={h}>{h}</th>)}</tr></thead>
        <tbody>{preview.sample.map((row, i) => <tr key={i}>{preview.headers.map(h => <td key={h}>{row[h] || '—'}</td>)}</tr>)}</tbody></table>
      <div className="modal-actions"><button className="button secondary" onClick={() => setStep(0)}>Back</button>
        <button className="button primary" onClick={() => setStep(2)}>Map columns</button></div>
    </div>}
    {step === 2 && preview && <div className="cx-form">
      {preview.headers.map(h => <Field key={h} label={`“${h}” maps to`}>
        <select aria-label={`Map ${h}`} value={mapping[h] || ''} onChange={e => setMapping(m => ({ ...m, [h]: e.target.value }))}>
          <option value="">Ignore this column</option>
          {CANONICAL.map(c => <option key={c} value={c}>{c.replaceAll('_', ' ')}</option>)}
        </select></Field>)}
      {!Object.values(mapping).includes('company_name') && <p className="form-error" role="alert">Company name must be mapped — it is the only required field.</p>}
      <div className="modal-actions"><button className="button secondary" onClick={() => setStep(1)}>Back</button>
        <button className="button primary" disabled={!Object.values(mapping).includes('company_name')} onClick={() => setStep(3)}>Review duplicates</button></div>
    </div>}
    {step === 3 && preview && <div>
      {preview.ambiguous.length === 0
        ? <Empty title="Nothing ambiguous" detail="Every row is either new or an exact duplicate. Exact duplicates are skipped, never merged." />
        : <><p className="cx-note">These rows need a decision. Skipped rows are left out; nothing merges silently.</p>
          <ul className="cx-list">{preview.ambiguous.map(a => <li key={a.row}>Row {a.row}: {a.reason}</li>)}</ul></>}
      <div className="cx-form">
        <Field label="Duplicate handling">
          <select aria-label="Duplicate handling" value={mode} onChange={e => setMode(e.target.value)}>
            <option value="create_only">Skip existing records</option>
            <option value="upsert">Refresh existing records with incoming fields</option>
          </select></Field>
        <Field label="Skip rows" hint="Row numbers to leave out, e.g. 2, 5.">
          <input value={skipRows} onChange={e => setSkipRows(e.target.value)} placeholder="none" /></Field>
      </div>
      <div className="modal-actions"><button className="button secondary" onClick={() => setStep(2)}>Back</button>
        <button className="button primary" onClick={() => setStep(4)}>Continue to confirm</button></div>
    </div>}
    {step === 4 && preview && <div>
      <p className="cx-note">About to import {preview.totals.rows} rows: ~{preview.totals.to_create} new, {preview.totals.exact_duplicates} duplicates skipped. Safe to retry — committed imports replay without duplicating.</p>
      <div className="modal-actions"><button className="button secondary" onClick={() => setStep(3)}>Back</button>
        <button className="button primary" disabled={busy} onClick={() => void doCommit()}>{busy ? 'Importing…' : 'Confirm import'}</button></div>
    </div>}
    {step === 5 && result && <div>
      <p className="cx-note">Imported {result.totals.created ?? 0} · updated {result.totals.updated ?? 0} · skipped {result.totals.skipped ?? 0} · errors {result.totals.errors ?? 0}</p>
      {result.errors.length > 0 && <ul className="cx-list">{result.errors.slice(0, 20).map(e => <li key={e.row}>Row {e.row}: {e.error}</li>)}</ul>}
      <div className="modal-actions"><button className="button primary" onClick={onClose}>Done</button></div>
    </div>}
  </Dialog>
}
