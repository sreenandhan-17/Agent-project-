import { useCallback, useEffect, useState, type FormEvent, type ReactNode } from 'react'
import { Link, useParams } from 'react-router'

import {
  ApiError,
  api,
  getSession,
  type Message,
  type Priority,
  type TicketDetail as Ticket,
  type TicketStatus,
  type TimelineEvent,
} from '../api'
import { PriorityPill, SlaBadge, StatusPill, TriageChip } from '../components/Pills'
import { PRIORITIES, STATUS_ACTION, formatIST } from '../format'

const REFRESH_MS = 30_000

export default function TicketDetail() {
  const id = Number(useParams().id)
  const me = getSession()?.agent
  const [ticket, setTicket] = useState<Ticket | null>(null)
  const [timeline, setTimeline] = useState<TimelineEvent[]>([])
  const [tab, setTab] = useState<'conversation' | 'timeline'>('conversation')
  const [notice, setNotice] = useState<{ kind: 'error' | 'ok'; text: string } | null>(null)
  const [busy, setBusy] = useState(false)

  const load = useCallback(async () => {
    try {
      const [t, events] = await Promise.all([api.getTicket(id), api.timeline(id)])
      setTicket(t)
      setTimeline(events)
    } catch (err) {
      setNotice({ kind: 'error', text: err instanceof ApiError ? err.message : 'Could not load ticket' })
    }
  }, [id])

  useEffect(() => {
    load()
    const timer = window.setInterval(load, REFRESH_MS)
    return () => window.clearInterval(timer)
  }, [load])

  /** Run an action, show its error (e.g. 409 "Already taken by X"), then reload either way. */
  async function act(action: () => Promise<unknown>, success?: string): Promise<boolean> {
    setBusy(true)
    setNotice(null)
    try {
      await action()
      if (success) setNotice({ kind: 'ok', text: success })
      return true
    } catch (err) {
      setNotice({ kind: 'error', text: err instanceof ApiError ? err.message : 'Something went wrong' })
      return false
    } finally {
      setBusy(false)
      await load()
    }
  }

  if (!ticket) {
    return (
      <div className="space-y-3">
        <BackLink />
        {notice ? <Notice notice={notice} /> : <p className="text-slate-400">Loading…</p>}
      </div>
    )
  }

  const isAssignee = me?.id === ticket.assignee_id
  const closedish = ticket.status === 'RESOLVED' || ticket.status === 'CLOSED'

  return (
    <div className="space-y-4">
      <BackLink />

      {/* Header */}
      <section className="space-y-3 rounded-lg bg-white p-4 ring-1 ring-slate-200">
        <div className="flex flex-wrap items-start justify-between gap-3">
          <div>
            <p className="font-mono text-xs text-slate-500">
              {ticket.number}
              {ticket.parent_ticket_number && <> · follow-up of {ticket.parent_ticket_number}</>}
            </p>
            <h1 className="text-xl font-semibold text-slate-900">{ticket.subject}</h1>
            <p className="text-sm text-slate-600">
              {ticket.customer.name}
              {ticket.customer.company && <> · {ticket.customer.company}</>} · {ticket.customer.email}
              {ticket.customer.phone && <> · {ticket.customer.phone}</>}
            </p>
          </div>
          <div className="flex flex-wrap items-center gap-2">
            <PriorityPill priority={ticket.priority} />
            <StatusPill status={ticket.status} />
            <SlaBadge sla={ticket.sla} />
            {ticket.needs_triage && <TriageChip impact={ticket.customer_impact} />}
          </div>
        </div>

        <dl className="grid gap-x-6 gap-y-1 text-sm sm:grid-cols-3">
          <Fact label="First reply">
            {ticket.first_response_at ? (
              <>
                sent {formatIST(ticket.first_response_at)}{' '}
                {ticket.first_response_due_at && ticket.first_response_at > ticket.first_response_due_at ? (
                  <span className="font-medium text-red-700">(late)</span>
                ) : (
                  <span className="text-emerald-700">(on time)</span>
                )}
              </>
            ) : (
              <>due {formatIST(ticket.first_response_due_at)}</>
            )}
          </Fact>
          <Fact label="Resolution due">{closedish ? '—' : formatIST(ticket.resolution_due_at)}</Fact>
          <Fact label="Created">{formatIST(ticket.created_at)}</Fact>
        </dl>

        <div className="flex flex-wrap items-center gap-3 border-t border-slate-100 pt-3">
          {/* Assignee / claim (INC-0291) */}
          <div className="text-sm">
            <span className="text-slate-500">Assignee: </span>
            {ticket.assignee_name ? (
              <span className="font-medium">{ticket.assignee_name}{isAssignee && ' (you)'}</span>
            ) : (
              <button
                disabled={busy}
                onClick={() => act(() => api.claim(ticket.id), 'Ticket is yours.')}
                className="rounded-md bg-sky-600 px-3 py-1 font-medium text-white hover:bg-sky-700 disabled:opacity-60"
              >
                Take ticket
              </button>
            )}
          </div>

          {/* Priority: any agent; this is also triage */}
          <label className="flex items-center gap-2 text-sm">
            <span className="text-slate-500">Priority</span>
            <select
              value={ticket.priority}
              disabled={busy}
              onChange={(e) => act(() => api.setPriority(ticket.id, e.target.value as Priority))}
              className="rounded-md border border-slate-300 px-2 py-1"
            >
              {PRIORITIES.map((p) => (
                <option key={p}>{p}</option>
              ))}
            </select>
          </label>
          {ticket.needs_triage && (
            <button
              disabled={busy}
              onClick={() => act(() => api.setPriority(ticket.id, ticket.priority), 'Priority confirmed.')}
              className="rounded-md bg-violet-100 px-3 py-1 text-sm font-medium text-violet-800 hover:bg-violet-200"
            >
              Confirm {ticket.priority}
            </button>
          )}

          {/* Status: only transitions this agent may make (server decides) */}
          {ticket.allowed_statuses.length > 0 && (
            <div className="flex flex-wrap items-center gap-2 text-sm">
              <span className="text-slate-500">Move to</span>
              {ticket.allowed_statuses.map((s: TicketStatus) => (
                <button
                  key={s}
                  disabled={busy}
                  onClick={() => act(() => api.setStatus(ticket.id, s))}
                  className="rounded-md bg-white px-3 py-1 ring-1 ring-slate-300 hover:bg-slate-50"
                >
                  {STATUS_ACTION[s]}
                </button>
              ))}
            </div>
          )}

          <button
            onClick={() => act(async () => openText(await api.exportTranscript(ticket.id)))}
            className="ml-auto text-sm text-sky-700 hover:underline"
            title="What the customer sees: public messages only"
          >
            Customer transcript
          </button>
        </div>
        {notice && <Notice notice={notice} />}
      </section>

      {/* Tabs */}
      <div className="flex gap-1 border-b border-slate-200">
        {(['conversation', 'timeline'] as const).map((t) => (
          <button
            key={t}
            onClick={() => setTab(t)}
            className={`-mb-px border-b-2 px-3 py-2 text-sm font-medium capitalize ${
              tab === t ? 'border-sky-600 text-sky-700' : 'border-transparent text-slate-500'
            }`}
          >
            {t} {t === 'timeline' && `(${timeline.length})`}
          </button>
        ))}
      </div>

      {tab === 'conversation' ? (
        <div className="grid gap-4 lg:grid-cols-[1fr_22rem]">
          <ol className="space-y-3">
            {ticket.messages.map((m) => (
              <MessageCard key={m.id} message={m} />
            ))}
          </ol>
          <div className="space-y-4">
            <Composer
              title="Reply to customer"
              hint={
                isAssignee
                  ? 'The customer will see this.'
                  : ticket.assignee_name
                    ? `Only ${ticket.assignee_name} (the assignee) can reply.`
                    : 'Take the ticket to reply.'
              }
              disabled={!isAssignee || busy}
              button="Send reply"
              className="bg-white ring-slate-200"
              onSubmit={(body) => act(() => api.reply(ticket.id, body), 'Reply sent.')}
            />
            <Composer
              title="Internal note"
              hint="Only agents can see this. Never sent to the customer."
              disabled={busy}
              button="Add note"
              className="bg-yellow-50 ring-yellow-300"
              onSubmit={(body) => act(() => api.note(ticket.id, body), 'Note added.')}
            />
          </div>
        </div>
      ) : (
        <Timeline events={timeline} />
      )}
    </div>
  )
}

function BackLink() {
  return (
    <Link to="/" className="text-sm text-sky-700 hover:underline">
      ← All tickets
    </Link>
  )
}

function Fact({ label, children }: { label: string; children: ReactNode }) {
  return (
    <div>
      <dt className="inline text-slate-500">{label}: </dt>
      <dd className="inline text-slate-800">{children}</dd>
    </div>
  )
}

function Notice({ notice }: { notice: { kind: 'error' | 'ok'; text: string } }) {
  return (
    <p
      role={notice.kind === 'error' ? 'alert' : 'status'}
      className={`rounded px-3 py-2 text-sm ${
        notice.kind === 'error' ? 'bg-red-50 text-red-700' : 'bg-emerald-50 text-emerald-800'
      }`}
    >
      {notice.text}
    </p>
  )
}

/** Message bodies are rendered as text (React escapes them); never as HTML. */
function MessageCard({ message: m }: { message: Message }) {
  const internal = m.visibility === 'INTERNAL'
  const fromCustomer = m.author_type === 'CUSTOMER'
  const style = internal
    ? 'bg-yellow-50 ring-yellow-300'
    : fromCustomer
      ? 'bg-white ring-slate-200'
      : 'bg-sky-50 ring-sky-200 sm:ml-12'
  return (
    <li className={`rounded-lg p-3 ring-1 ${style} ${fromCustomer ? 'sm:mr-12' : ''}`}>
      <div className="mb-1 flex flex-wrap items-center gap-2 text-xs text-slate-500">
        {internal && (
          <span className="rounded bg-yellow-200 px-1.5 py-0.5 font-semibold uppercase tracking-wide text-yellow-900">
            Internal note
          </span>
        )}
        <span className="font-medium text-slate-700">{m.author_name}</span>
        <span>{formatIST(m.created_at)}</span>
      </div>
      <p className="whitespace-pre-wrap break-words text-sm text-slate-800">{m.body}</p>
    </li>
  )
}

function Composer(props: {
  title: string
  hint: string
  button: string
  disabled: boolean
  className: string
  onSubmit: (body: string) => Promise<boolean>
}) {
  const [body, setBody] = useState('')

  async function submit(e: FormEvent) {
    e.preventDefault()
    if (!body.trim()) return
    if (await props.onSubmit(body.trim())) setBody('')
  }

  return (
    <form onSubmit={submit} className={`space-y-2 rounded-lg p-3 ring-1 ${props.className}`}>
      <h2 className="text-sm font-semibold text-slate-800">{props.title}</h2>
      <textarea
        value={body}
        onChange={(e) => setBody(e.target.value)}
        disabled={props.disabled}
        rows={4}
        className="w-full rounded-md border border-slate-300 bg-white px-2 py-1.5 text-sm disabled:bg-slate-100"
      />
      <div className="flex items-center justify-between gap-2">
        <p className="text-xs text-slate-500">{props.hint}</p>
        <button
          disabled={props.disabled || !body.trim()}
          className="rounded-md bg-slate-900 px-3 py-1.5 text-sm font-medium text-white disabled:opacity-40"
        >
          {props.button}
        </button>
      </div>
    </form>
  )
}

// --- Timeline (INC-0318) ------------------------------------------------------------------

function show(value: unknown): string {
  if (value === null || value === undefined) return '—'
  if (typeof value === 'object') return JSON.stringify(value)
  return String(value)
}

function describe(e: TimelineEvent): string {
  const o = e.old_value as Record<string, unknown> | null
  const n = e.new_value as Record<string, unknown> | null
  switch (e.action) {
    case 'STATUS_CHANGED':
      return `Status ${show(e.old_value)} → ${show(e.new_value)}`
    case 'PRIORITY_CHANGED':
      return `Priority ${show(o?.priority)} → ${show(n?.priority)} (resolution due ${formatIST(
        n?.resolution_due_at as string | null,
      )})`
    case 'TRIAGED':
      return `Priority ${show(n?.priority)} confirmed`
    case 'CLAIMED':
      return 'Took the ticket'
    case 'REPLY_SENT':
      return 'Replied to the customer'
    case 'NOTE_ADDED':
      return 'Added an internal note'
    case 'CUSTOMER_REPLIED':
      return 'Customer replied'
    case 'SLA_PAUSED':
      return 'SLA clock paused'
    case 'SLA_RESUMED':
      return `SLA clock resumed (paused ${show(n?.paused_minutes)} working min in total)`
    case 'TICKET_CREATED':
      return 'Ticket created'
    default:
      return `${e.action}${e.field ? ` ${e.field}` : ''}: ${show(e.old_value)} → ${show(e.new_value)}`
  }
}

function Timeline({ events }: { events: TimelineEvent[] }) {
  if (!events.length) return <p className="text-sm text-slate-400">No events yet.</p>
  return (
    <ol className="space-y-1 rounded-lg bg-white p-3 ring-1 ring-slate-200">
      {events.map((e) => (
        <li key={e.id} className="grid gap-x-3 text-sm sm:grid-cols-[12rem_10rem_1fr]">
          <span className="font-mono text-xs text-slate-500">{formatIST(e.created_at)}</span>
          <span className="font-medium text-slate-700">{e.actor_name}</span>
          <span className="text-slate-800">{describe(e)}</span>
        </li>
      ))}
      <li className="pt-2 text-xs text-slate-400">
        Append-only: these records can't be edited or deleted. Times are set by the server.
      </li>
    </ol>
  )
}

function openText(text: string) {
  const url = URL.createObjectURL(new Blob([text], { type: 'text/plain;charset=utf-8' }))
  window.open(url, '_blank', 'noopener')
  window.setTimeout(() => URL.revokeObjectURL(url), 60_000)
}
