import type { ReactNode } from 'react'
import { flexRender, getCoreRowModel, useReactTable, type ColumnDef } from '@tanstack/react-table'
import { StateBadge } from './Primitives'

export function WorkflowTable<T extends { id: string }>({ items, columns, selected, onSelect }: {
  items: T[]; columns: ColumnDef<T, unknown>[]; selected: string | null; onSelect: (id: string) => void
}) {
  const table = useReactTable({ data: items, columns, getCoreRowModel: getCoreRowModel() })
  return <div className="table-scroll"><table className="workflow-table"><thead>{table.getHeaderGroups().map(group => <tr key={group.id}>{group.headers.map(header => <th key={header.id}>{flexRender(header.column.columnDef.header, header.getContext())}</th>)}</tr>)}</thead><tbody>{table.getRowModel().rows.map(row => <tr key={row.id} className={selected === row.original.id ? 'selected' : ''} tabIndex={0} aria-selected={selected === row.original.id} onClick={() => onSelect(row.original.id)} onKeyDown={event => { if (event.key === 'Enter' || event.key === ' ') { event.preventDefault(); onSelect(row.original.id) } }}>{row.getVisibleCells().map(cell => <td key={cell.id}>{flexRender(cell.column.columnDef.cell, cell.getContext())}</td>)}</tr>)}</tbody></table></div>
}

export function WorkflowMetrics({ items }: { items: { label: string; value: number | undefined; icon: ReactNode; detail?: string }[] }) {
  return <div className="operational-metrics workflow-metrics">{items.map(item => <div key={item.label}><span className="workflow-metric-icon">{item.icon}</span><span>{item.label}<strong>{item.value === undefined ? '—' : item.value.toLocaleString()}</strong>{item.detail && <small>{item.detail}</small>}</span></div>)}</div>
}

export function StatusText({ value, known, tone }: { value: string; known: readonly string[]; tone?: 'green' | 'yellow' | 'red' | 'blue' | 'neutral' }) {
  return <StateBadge tone={known.includes(value) ? tone || 'neutral' : 'red'}>{known.includes(value) ? value.replaceAll('_', ' ') : `Unknown status: ${value}`}</StateBadge>
}

export function ShortDate({ value }: { value: string | null | undefined }) {
  if (!value) return <span className="muted-copy">Not recorded</span>
  const date = new Date(value)
  if (Number.isNaN(date.getTime())) return <span className="muted-copy">Unknown date</span>
  return <time dateTime={value}>{new Intl.DateTimeFormat(undefined, { month: 'short', day: 'numeric', year: 'numeric' }).format(date)}</time>
}
