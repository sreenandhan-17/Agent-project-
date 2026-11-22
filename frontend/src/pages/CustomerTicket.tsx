import { useCallback, useEffect, useState, type FormEvent } from 'react'
import { Link, useParams } from 'react-router'

import { formatIST } from '../format'
import { PublicApiError, publicApi, type CustomerTicketView } from '../publicApi'
import PublicLayout from './PublicLayout'

// Customer wording: no internal jargon such as "triage" or SLA.
const STATUS: Record<CustomerTicketView['status'], { label: string; style: string }> = {
  NEW: { label: 'Received', style: 'bg-slate-100 text-slate-700' },
  OPEN: { label: 'In progress', style: 'bg-sky-100 text-sky-800' },
  REOPENED: { label: 'Reopened', style: 'bg-sky-100 text-sky-800' },
  WAITING_ON_CUSTOMER: { label: 'Waiting for your reply', style: 'bg-amber-100 text-amber-900' },
  RESOLVED: { label: 'Resolved', style: 'bg-emerald-100 text-emerald-800' },
  CLOSED: { label: 'Closed', style: 'bg-slate-100 text-slate-500' },
}

/** /t/:token: renders ONLY the CustomerTicketView the server returns (public messages). */
export default function CustomerTicket() {
  const token = useParams().token ?? ''
  const [ticket, setTicket] = useState<CustomerTicketView | null>(null)
  const [state, setState] = useState<'loading' | 'ok' | 'not-found' | 'error'>('loading')
  const [reply, setReply] = useState('')
  const [busy, setBusy] = useState(false)
  const [error, setError] = useState<string | null>(null)

  const load = useCallback(async () => {
    if (!token) {
      // /t/ or /t/a/b: no API call (an empty token would hit the list URL instead).
      setState('not-found')
      return
    }
    try {
      setTicket(await publicApi.view(token))
      setState('ok')
    } catch (err) {
      setState(err instanceof PublicApiError && err.status === 404 ? 'not-found' : 'error')
    }
  }, [token])

  useEffect(() => {
    load()
  }, [load])

  async function send(e: FormEvent) {
    e.preventDefault()
    if (!reply.trim()) return
    setBusy(true)
    setError(null)
    try {
      setTicket(await publicApi.reply(token, reply.trim()))
      setReply('')
    } catch (err) {
      setError(err instanceof PublicApiError ? err.message : 'Could not send. Please try again.')
    } finally {
      setBusy(false)
    }
  }

  if (state === 'not-found') {
    return (
      <PublicLayout>
        <div className="space-y-2 rounded-lg bg-white p-6 ring-1 ring-slate-200">
          <h1 className="text-lg font-semibold text-slate-900">We couldn't find that request</h1>
          <p className="text-sm text-slate-600">
            The link may be incomplete. Please use the full link from your email. If you need help with
            something new, you can{' '}
            <Link to="/new" className="text-sky-700 hover:underline">
              open a new request
            </Link>
            .
          </p>
        </div>
      </PublicLayout>
    )
  }
  if (state !== 'ok' || !ticket) {
    return (
      <PublicLayout>
        <p className="text-slate-500">
          {state === 'error' ? 'Something went wrong loading your request. Please refresh.' : 'Loading…'}
        </p>
      </PublicLayout>
    )
  }

  const status = STATUS[ticket.status]
  return (
    <PublicLayout>
      <div className="space-y-4">
        <section className="rounded-lg bg-white p-4 ring-1 ring-slate-200">
          <p className="font-mono text-xs text-slate-500">{ticket.number}</p>
          <div className="flex flex-wrap items-center justify-between gap-2">
            <h1 className="text-xl font-semibold text-slate-900">{ticket.subject}</h1>
            <span className={`rounded-full px-2.5 py-0.5 text-sm font-medium ${status.style}`}>{status.label}</span>
          </div>
          <p className="mt-1 text-xs text-slate-500">
            Opened {formatIST(ticket.created_at)} · Keep this page's link private: anyone with it can read and
            reply.
          </p>
        </section>

        <ol className="space-y-3">
          {ticket.messages.map((m) => (
            <li
              key={m.id}
              className={`rounded-lg p-3 ring-1 ${
                m.author === 'support' ? 'bg-sky-50 ring-sky-200 sm:mr-12' : 'bg-white ring-slate-200 sm:ml-12'
              }`}
            >
              <div className="mb-1 flex gap-2 text-xs text-slate-500">
                <span className="font-medium text-slate-700">{m.author === 'customer' ? 'You' : m.author_name}</span>
                <span>{formatIST(m.created_at)}</span>
              </div>
              <p className="whitespace-pre-wrap break-words text-sm text-slate-800">{m.body}</p>
            </li>
          ))}
        </ol>

        <form onSubmit={send} className="space-y-2 rounded-lg bg-white p-4 ring-1 ring-slate-200">
          <label className="block">
            <span className="text-sm font-semibold text-slate-800">Add a reply</span>
            <textarea
              rows={4}
              maxLength={10000}
              value={reply}
              onChange={(e) => setReply(e.target.value)}
              className="mt-1 w-full rounded-md border border-slate-300 px-3 py-2 text-sm"
            />
          </label>
          {error && <p role="alert" className="rounded bg-red-50 px-3 py-2 text-sm text-red-700">{error}</p>}
          <button
            disabled={busy || !reply.trim()}
            className="rounded-md bg-sky-600 px-4 py-2 text-sm font-medium text-white hover:bg-sky-700 disabled:opacity-50"
          >
            {busy ? 'Sending…' : 'Send reply'}
          </button>
        </form>
      </div>
    </PublicLayout>
  )
}
