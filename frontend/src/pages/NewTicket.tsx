import { useState, type FormEvent } from 'react'
import { useNavigate } from 'react-router'

import { PublicApiError, publicApi, type CustomerImpact, type NewTicketForm } from '../publicApi'
import PublicLayout from './PublicLayout'

const IMPACTS: { value: CustomerImpact; label: string; hint: string }[] = [
  { value: 'CANNOT_WORK', label: "I can't work at all", hint: 'Something is down or blocking you completely' },
  { value: 'PARTIAL', label: 'Partly affected', hint: 'Something is broken but you can work around it' },
  { value: 'QUESTION', label: 'Just a question', hint: 'How-to, billing, or a request' },
]

const EMPTY: NewTicketForm = {
  name: '',
  email: '',
  company: '',
  subject: '',
  body: '',
  impact: 'PARTIAL',
  website: '',
}

const input = 'mt-1 w-full rounded-md border border-slate-300 px-3 py-2 focus:border-sky-500 focus:outline-none'

export default function NewTicket() {
  const navigate = useNavigate()
  const [form, setForm] = useState<NewTicketForm>(EMPTY)
  const [error, setError] = useState<string | null>(null)
  const [sent, setSent] = useState(false)
  const [busy, setBusy] = useState(false)

  const set = <K extends keyof NewTicketForm>(key: K, value: NewTicketForm[K]) =>
    setForm((f) => ({ ...f, [key]: value }))

  async function submit(e: FormEvent) {
    e.preventDefault()
    setBusy(true)
    setError(null)
    try {
      const token = await publicApi.submit(form)
      if (token) navigate(`/t/${token}`, { replace: true })
      else setSent(true)
    } catch (err) {
      setError(err instanceof PublicApiError ? err.message : 'Could not reach the server. Please try again.')
    } finally {
      setBusy(false)
    }
  }

  if (sent) {
    return (
      <PublicLayout>
        <p className="rounded-lg bg-white p-6 ring-1 ring-slate-200">Thanks, we have received your request.</p>
      </PublicLayout>
    )
  }

  return (
    <PublicLayout>
      <form onSubmit={submit} className="space-y-5 rounded-lg bg-white p-6 ring-1 ring-slate-200">
        <div>
          <h1 className="text-xl font-semibold text-slate-900">Contact support</h1>
          <p className="text-sm text-slate-500">
            We reply within working hours (Mon–Fri, 09:30–18:30 IST).
          </p>
        </div>

        <div className="grid gap-4 sm:grid-cols-2">
          <label className="block">
            <span className="text-sm font-medium text-slate-700">Your name</span>
            <input required maxLength={120} value={form.name} onChange={(e) => set('name', e.target.value)} className={input} />
          </label>
          <label className="block">
            <span className="text-sm font-medium text-slate-700">Email</span>
            <input required type="email" value={form.email} onChange={(e) => set('email', e.target.value)} className={input} />
          </label>
          <label className="block sm:col-span-2">
            <span className="text-sm font-medium text-slate-700">
              Company <span className="font-normal text-slate-400">(optional)</span>
            </span>
            <input maxLength={120} value={form.company} onChange={(e) => set('company', e.target.value)} className={input} />
          </label>
        </div>

        <fieldset>
          <legend className="text-sm font-medium text-slate-700">How much is this affecting you?</legend>
          <div className="mt-2 grid gap-2 sm:grid-cols-3">
            {IMPACTS.map((i) => (
              <label
                key={i.value}
                className={`cursor-pointer rounded-md p-3 ring-1 ${
                  form.impact === i.value ? 'bg-sky-50 ring-sky-500' : 'ring-slate-300 hover:bg-slate-50'
                }`}
              >
                <input
                  type="radio"
                  name="impact"
                  value={i.value}
                  checked={form.impact === i.value}
                  onChange={() => set('impact', i.value)}
                  className="mr-2"
                />
                <span className="text-sm font-medium text-slate-900">{i.label}</span>
                <span className="mt-1 block text-xs text-slate-500">{i.hint}</span>
              </label>
            ))}
          </div>
        </fieldset>

        <label className="block">
          <span className="text-sm font-medium text-slate-700">Subject</span>
          <input required maxLength={200} value={form.subject} onChange={(e) => set('subject', e.target.value)} className={input} />
        </label>
        <label className="block">
          <span className="text-sm font-medium text-slate-700">Message</span>
          <textarea
            required
            rows={6}
            maxLength={10000}
            value={form.body}
            onChange={(e) => set('body', e.target.value)}
            className={input}
          />
        </label>

        {/* Honeypot (notes/14): invisible to people and screen readers; bots tend to fill it. */}
        <div aria-hidden="true" className="absolute -left-[9999px] h-px w-px overflow-hidden">
          <label>
            Website
            <input
              tabIndex={-1}
              autoComplete="off"
              name="website"
              value={form.website}
              onChange={(e) => set('website', e.target.value)}
            />
          </label>
        </div>

        {error && <p role="alert" className="rounded bg-red-50 px-3 py-2 text-sm text-red-700">{error}</p>}
        <button
          disabled={busy}
          className="rounded-md bg-sky-600 px-4 py-2 font-medium text-white hover:bg-sky-700 disabled:opacity-60"
        >
          {busy ? 'Sending…' : 'Send request'}
        </button>
      </form>
    </PublicLayout>
  )
}
