/** Shared building blocks for the commercial workspace. */
import { useState, type ReactNode } from 'react'

export function Section({ title, intro, action, children }: {
  title: string; intro?: string; action?: ReactNode; children: ReactNode
}) {
  return <section className="cx-section">
    <div className="cx-section-head">
      <div><h2>{title}</h2>{intro && <p>{intro}</p>}</div>
      {action && <div className="cx-section-action">{action}</div>}
    </div>
    {children}
  </section>
}

export function Field({ label, hint, children }: { label: string; hint?: string; children: ReactNode }) {
  return <label className="cx-field"><span>{label}</span>{children}{hint && <small>{hint}</small>}</label>
}

export function Empty({ title, detail, action }: { title: string; detail: string; action?: ReactNode }) {
  return <div className="cx-empty"><h3>{title}</h3><p>{detail}</p>{action}</div>
}

export function Stepper({ steps, current, onGo }: { steps: string[]; current: number; onGo?: (index: number) => void }) {
  return <ol className="cx-steps" aria-label="Progress">
    {steps.map((step, index) => <li key={step} aria-current={index === current ? 'step' : undefined}
      className={index === current ? 'active' : index < current ? 'done' : ''}>
      {onGo && index < current
        ? <button type="button" onClick={() => onGo(index)}><span>{index + 1}</span>{step}</button>
        : <><span>{index + 1}</span>{step}</>}
    </li>)}
  </ol>
}

export function Dialog({ title, intro, onClose, children, wide }: {
  title: string; intro?: string; onClose: () => void; children: ReactNode; wide?: boolean
}) {
  return <div className="modal-backdrop" onMouseDown={event => { if (event.target === event.currentTarget) onClose() }}>
    <div className={`modal${wide ? ' cx-wide' : ''}`} role="dialog" aria-modal="true" aria-label={title}>
      <button className="icon-button modal-close" aria-label="Close dialog" onClick={onClose}>✕</button>
      <h2>{title}</h2>{intro && <p>{intro}</p>}
      {children}
    </div>
  </div>
}

/**
 * Searchable single-select. The user sees human-readable names; the parent
 * keeps the canonical id. Nothing here invents an option: an empty result is
 * stated, never filled in.
 */
export function SearchPicker<T extends { id: string }>({ label, placeholder, selected, renderOption, onSearch, onPick }:
{
  label: string
  placeholder: string
  selected: T | null
  renderOption: (item: T) => string
  onSearch: (text: string) => Promise<T[]>
  onPick: (item: T | null) => void
}) {
  const [text, setText] = useState('')
  const [options, setOptions] = useState<T[]>([])
  const [open, setOpen] = useState(false)
  const [searching, setSearching] = useState(false)
  async function search(next: string) {
    setText(next)
    onPick(null)
    if (next.trim().length < 2) { setOptions([]); setOpen(false); return }
    setSearching(true)
    try { setOptions(await onSearch(next.trim())); setOpen(true) }
    catch { setOptions([]) }
    finally { setSearching(false) }
  }
  return <div className="cx-picker">
    <label>{label}
      <input value={selected ? renderOption(selected) : text} onChange={e => void search(e.target.value)}
        placeholder={placeholder} autoComplete="off" aria-expanded={open} role="combobox" />
    </label>
    {open && <ul role="listbox" aria-label={label}>{options.map(item =>
      <li key={item.id}><button type="button" onClick={() => { onPick(item); setOpen(false); setText('') }}>{renderOption(item)}</button></li>)}
      {options.length === 0 && !searching && <li className="cx-picker-none">No matches — keep typing or create it first.</li>}</ul>}
  </div>
}
