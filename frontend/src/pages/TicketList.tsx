import { useCallback, useEffect, useState, type FormEvent } from 'react'
import { Link, useNavigate, useSearchParams } from 'react-router'

import { ApiError, api, type TicketListItem, type TicketView } from '../api'
import { PriorityPill, SlaBadge, StatusPill, TriageChip } from '../components/Pills'

const TABS: { view: TicketView; label: string }[] = [
  { view: 'all', label: 'All' },
  { view: 'mine', label: 'Mine' },
  { view: 'unassigned', label: 'Unassigned' },
  { view: 'late', label: 'Late' },
  { view: 'waiting', label: 'Waiting on customer' },
  { view: 'triage', label: 'Needs triage' },
]

const REFRESH_MS = 30_000

export default function TicketList() {
  const navigate = useNavigate()
  const [params, setParams] = useSearchParams()
  const view = (TABS.find((t) => t.view === params.get('view'))?.view ?? 'all') as TicketView
  const [q, setQ] = useState(params.get('q') ?? '')
  const [tickets, setTickets] = useState<TicketListItem[] | null>(null)
  const [error, setError] = useState<string | null>(null)
  const [refreshedAt, setRefreshedAt] = useState<Date | null>(null)

  const load = useCallback(async () => {
    try {
      setTickets(await api.listTickets(view, params.get('q') ?? ''))
      setError(null)
      setRefreshedAt(new Date())
    } catch (err) {
      setError(err instanceof ApiError ? err.message : 'Could not load tickets')
    }
  }, [view, params])

  useEffect(() => {
    load()
    const timer = window.setInterval(load, REFRESH_MS)
    return () => window.clearInterval(timer)
  }, [load])

  function selectView(next: TicketView) {
    const p = new URLSearchParams(params)
    p.set('view', next)
    setTickets(null)
    setParams(p)
  }

  function search(e: FormEvent) {
    e.preventDefault()
    const p = new URLSearchParams(params)
    if (q.trim()) p.set('q', q.trim())
    else p.delete('q')
    setParams(p)
  }

  return (
    <div className="space-y-4">
      <div className="flex flex-wrap items-end justify-between gap-3">
        <nav className="flex flex-wrap gap-1" aria-label="Ticket views">
          {TABS.map((t) => (
            <button
              key={t.view}
              onClick={() => selectView(t.view)}
              aria-current={view === t.view ? 'page' : undefined}
              className={`rounded-md px-3 py-1.5 text-sm font-medium ${
                view === t.view
                  ? 'bg-slate-900 text-white'
                  : 'text-slate-600 hover:bg-slate-200'
              } ${t.view === 'late' && view !== t.view ? 'text-red-700' : ''}`}
            >
              {t.label}
            </button>
          ))}
        </nav>
        <form onSubmit={search} className="flex gap-2">
          <input
            value={q}
            onChange={(e) => setQ(e.target.value)}
            placeholder="Search number, subject, customer"
            className="w-64 max-w-full rounded-md border border-slate-300 px-3 py-1.5 text-sm"
          />
          <button className="rounded-md bg-white px-3 py-1.5 text-sm ring-1 ring-slate-300 hover:bg-slate-50">
            Search
          </button>
        </form>
      </div>

      {error && <p className="rounded bg-red-50 px-3 py-2 text-sm text-red-700">{error}</p>}

      <div className="overflow-x-auto rounded-lg bg-white ring-1 ring-slate-200">
        <table className="min-w-full text-left text-sm">
          <thead className="border-b border-slate-200 bg-slate-50 text-xs uppercase tracking-wide text-slate-500">
            <tr>
              <th className="px-4 py-2 font-medium">Ticket</th>
              <th className="px-4 py-2 font-medium">Customer</th>
              <th className="px-4 py-2 font-medium">Priority</th>
              <th className="px-4 py-2 font-medium">Status</th>
              <th className="px-4 py-2 font-medium">Assignee</th>
              <th className="px-4 py-2 font-medium">SLA</th>
            </tr>
          </thead>
          <tbody className="divide-y divide-slate-100">
            {tickets === null && (
              <tr>
                <td colSpan={6} className="px-4 py-8 text-center text-slate-400">
                  Loading…
                </td>
              </tr>
            )}
            {tickets?.length === 0 && (
              <tr>
                <td colSpan={6} className="px-4 py-8 text-center text-slate-400">
                  No tickets here.
                </td>
              </tr>
            )}
            {tickets?.map((t) => (
              <tr
                key={t.id}
                onClick={() => navigate(`/tickets/${t.id}`)}
                className="cursor-pointer hover:bg-sky-50"
              >
                <td className="px-4 py-2.5">
                  <Link to={`/tickets/${t.id}`} className="font-mono text-xs text-slate-500">
                    {t.number}
                  </Link>
                  <div className="flex flex-wrap items-center gap-2">
                    <span className="font-medium text-slate-900">{t.subject}</span>
                    {t.needs_triage && <TriageChip impact={t.customer_impact} />}
                  </div>
                </td>
                <td className="px-4 py-2.5 text-slate-700">{t.customer_name}</td>
                <td className="px-4 py-2.5">
                  <PriorityPill priority={t.priority} />
                </td>
                <td className="px-4 py-2.5">
                  <StatusPill status={t.status} />
                </td>
                <td className="px-4 py-2.5 text-slate-700">
                  {t.assignee_name ?? <span className="text-slate-400">Unassigned</span>}
                </td>
                <td className="px-4 py-2.5">
                  <SlaBadge sla={t.sla} />
                </td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
      {refreshedAt && (
        <p className="text-right text-xs text-slate-400">
          Updated {refreshedAt.toLocaleTimeString()} · refreshes every 30s
        </p>
      )}
    </div>
  )
}
