// Customer-portal client (notes/18). Deliberately separate from api.ts:
// it never reads the agent session, never sends an Authorization header and never calls
// agent endpoints. Everything it receives is a CustomerTicketView (server allow-list).

export type CustomerImpact = 'CANNOT_WORK' | 'PARTIAL' | 'QUESTION'

export interface CustomerMessage {
  id: number
  author: 'customer' | 'support'
  author_name: string
  body: string
  created_at: string
}

export interface CustomerTicketView {
  number: string
  subject: string
  status: 'NEW' | 'OPEN' | 'WAITING_ON_CUSTOMER' | 'RESOLVED' | 'CLOSED' | 'REOPENED'
  created_at: string
  messages: CustomerMessage[]
}

export interface NewTicketForm {
  name: string
  email: string
  company: string
  subject: string
  body: string
  impact: CustomerImpact
  website: string // honeypot: must stay empty
}

export class PublicApiError extends Error {
  readonly status: number

  constructor(status: number, message: string) {
    super(message)
    this.status = status
  }
}

const BASE = import.meta.env.VITE_API_URL ?? ''

async function call<T>(path: string, method: 'GET' | 'POST', body?: unknown): Promise<T> {
  const res = await fetch(BASE + path, {
    method,
    headers: body !== undefined ? { 'Content-Type': 'application/json' } : {},
    body: body !== undefined ? JSON.stringify(body) : undefined,
    credentials: 'omit',
  })
  if (!res.ok) {
    const data = await res.json().catch(() => null)
    const detail = (data as { detail?: unknown } | null)?.detail
    const message =
      typeof detail === 'string'
        ? detail
        : Array.isArray(detail) && detail[0]?.msg
          ? String(detail[0].msg)
          : 'Something went wrong. Please try again.'
    throw new PublicApiError(res.status, message)
  }
  return res.json() as Promise<T>
}

export const publicApi = {
  /** Returns the private token, or null if the server silently dropped it (honeypot). */
  submit: async (form: NewTicketForm): Promise<string | null> => {
    const data = await call<{ token?: string }>('/api/public/tickets', 'POST', {
      ...form,
      company: form.company.trim() || null,
    })
    return data.token ?? null
  },
  view: (token: string) =>
    call<CustomerTicketView>(`/api/public/tickets/${encodeURIComponent(token)}`, 'GET'),
  /** `token` is usually the same one passed in, but differs when the reply landed on a new
   * follow-up ticket instead (§3.5, more than 7 days after resolution) — callers must redirect
   * there rather than keep showing the old ticket under its old URL. */
  reply: (token: string, body: string) =>
    call<{ token: string; ticket: CustomerTicketView }>(
      `/api/public/tickets/${encodeURIComponent(token)}/replies`,
      'POST',
      { body },
    ),
}
