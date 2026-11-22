import type { CustomerImpact, Priority, Sla, TicketStatus } from '../api'
import { IMPACT_LABEL, STATUS_LABEL, formatIST, formatWorking } from '../format'

const SLA_STYLE = {
  red: 'bg-red-100 text-red-800 ring-red-300',
  amber: 'bg-amber-100 text-amber-900 ring-amber-300',
  green: 'bg-emerald-100 text-emerald-800 ring-emerald-300',
  paused: 'bg-slate-100 text-slate-600 ring-slate-300',
  done: 'bg-white text-slate-400 ring-slate-200',
} as const

function slaLabel(sla: Sla): string {
  switch (sla.state) {
    case 'paused':
      return 'Paused'
    case 'done':
      return 'Done'
    case 'red':
      return sla.remaining_minutes ? `Late ${formatWorking(sla.remaining_minutes)}` : 'Late'
    default:
      return sla.remaining_minutes == null ? 'On track' : `${formatWorking(sla.remaining_minutes)} left`
  }
}

function slaTooltip(sla: Sla): string {
  if (sla.state === 'done') return 'Resolved or closed: no SLA clock'
  const what = sla.target === 'first_response' ? 'First reply' : 'Resolution'
  if (sla.state === 'paused') return `${what} clock paused while waiting on the customer`
  const left =
    sla.remaining_minutes == null
      ? ''
      : sla.remaining_minutes <= 0
        ? ` · overdue by ${formatWorking(sla.remaining_minutes)} working time`
        : ` · ${formatWorking(sla.remaining_minutes)} working time left`
  return `${what} due ${formatIST(sla.due_at)}${left}`
}

export function SlaBadge({ sla }: { sla: Sla }) {
  return (
    <span
      title={slaTooltip(sla)}
      className={`inline-flex items-center gap-1 whitespace-nowrap rounded-full px-2 py-0.5 text-xs font-medium ring-1 ring-inset ${SLA_STYLE[sla.state]}`}
    >
      {sla.target === 'first_response' && sla.state !== 'done' && (
        <span className="opacity-70">reply</span>
      )}
      {slaLabel(sla)}
    </span>
  )
}

const PRIORITY_STYLE: Record<Priority, string> = {
  URGENT: 'bg-red-600 text-white',
  MEDIUM: 'bg-sky-100 text-sky-800',
  LOW: 'bg-slate-100 text-slate-600',
}

export function PriorityPill({ priority }: { priority: Priority }) {
  return (
    <span className={`rounded px-1.5 py-0.5 text-xs font-semibold ${PRIORITY_STYLE[priority]}`}>
      {priority}
    </span>
  )
}

export function StatusPill({ status }: { status: TicketStatus }) {
  return <span className="whitespace-nowrap text-sm text-slate-700">{STATUS_LABEL[status]}</span>
}

export function TriageChip({ impact }: { impact: CustomerImpact | null }) {
  return (
    <span
      title="Customer ticket: priority not yet confirmed by an agent"
      className="whitespace-nowrap rounded bg-violet-100 px-1.5 py-0.5 text-xs font-medium text-violet-800"
    >
      Needs triage{impact ? ` · ${IMPACT_LABEL[impact]}` : ''}
    </span>
  )
}
