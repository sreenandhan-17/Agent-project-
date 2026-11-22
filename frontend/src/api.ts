// Typed client for the Frontdesk API. Token lives in sessionStorage (notes/16):
// survives a refresh, cleared when the tab closes; any 401 logs the agent out.

export type TicketStatus =
  | 'NEW'
  | 'OPEN'
  | 'WAITING_ON_CUSTOMER'
  | 'RESOLVED'
  | 'CLOSED'
  | 'REOPENED'
export type Priority = 'URGENT' | 'MEDIUM' | 'LOW'
export type CustomerImpact = 'CANNOT_WORK' | 'PARTIAL' | 'QUESTION'
export type SlaColour = 'green' | 'amber' | 'red' | 'paused' | 'done'
export type TicketView = 'all' | 'mine' | 'unassigned' | 'late' | 'waiting' | 'triage'

export interface Agent {
  id: number
  name: string
  email: string
  role: 'AGENT' | 'ADMIN'
}

export interface Sla {
  target: 'first_response' | 'resolution' | null
  due_at: string | null
  state: SlaColour
  remaining_minutes: number | null
}

export interface TicketListItem {
  id: number
  number: string
  subject: string
  status: TicketStatus
  priority: Priority
  assignee_id: number | null
  assignee_name: string | null
  customer_name: string
  created_at: string
  first_response_at: string | null
  first_response_due_at: string | null
  resolution_due_at: string | null
  paused_at: string | null
  paused_minutes: number
  resolved_at: string | null
  closed_at: string | null
  reopen_count: number
  needs_triage: boolean
  customer_impact: CustomerImpact | null
  sla: Sla
}

export interface Message {
  id: number
  author_type: 'AGENT' | 'CUSTOMER' | 'SYSTEM'
  author_agent_id: number | null
  author_name: string
  visibility: 'PUBLIC' | 'INTERNAL'
  body: string
  created_at: string
}

export interface TicketDetail extends TicketListItem {
  customer: { id: number; name: string; email: string; phone: string | null; company: string | null }
  public_token: string
  parent_ticket_number: string | null
  allowed_statuses: TicketStatus[]
  messages: Message[]
}

export interface TimelineEvent {
  id: number
  action: string
  field: string | null
  old_value: unknown
  new_value: unknown
  created_at: string
  actor_type: 'AGENT' | 'CUSTOMER' | 'SYSTEM'
  actor_id: number | null
  actor_name: string
}

// --- session ----------------------------------------------------------------------------

const TOKEN_KEY = 'frontdesk.token'
const AGENT_KEY = 'frontdesk.agent'

function storage(): Storage | null {
  try {
    return window.sessionStorage
  } catch {
    return null
  }
}

export function getSession(): { token: string; agent: Agent } | null {
  try {
    const token = storage()?.getItem(TOKEN_KEY)
    const agent = storage()?.getItem(AGENT_KEY)
    return token && agent ? { token, agent: JSON.parse(agent) as Agent } : null
  } catch {
    return null
  }
}

export function saveSession(token: string, agent: Agent): void {
  try {
    storage()?.setItem(TOKEN_KEY, token)
    storage()?.setItem(AGENT_KEY, JSON.stringify(agent))
  } catch {
    // Private mode etc.: the agent will just have to log in again after a refresh.
  }
}

export function clearSession(): void {
  try {
    storage()?.removeItem(TOKEN_KEY)
    storage()?.removeItem(AGENT_KEY)
  } catch {
    /* ignore */
  }
}

// --- requests ---------------------------------------------------------------------------

const BASE = import.meta.env.VITE_API_URL ?? ''

export class ApiError extends Error {
  readonly status: number

  constructor(status: number, message: string) {
    super(message)
    this.status = status
  }
}

function errorMessage(data: unknown, fallback: string): string {
  const detail = (data as { detail?: unknown } | null)?.detail
  if (typeof detail === 'string') return detail
  if (detail && typeof detail === 'object' && 'message' in detail) {
    return String((detail as { message: unknown }).message)
  }
  if (Array.isArray(detail) && detail[0]?.msg) return String(detail[0].msg)
  return fallback
}

async function request<T>(path: string, init: { method?: string; body?: unknown } = {}): Promise<T> {
  const session = getSession()
  const res = await fetch(BASE + path, {
    method: init.method ?? 'GET',
    headers: {
      ...(init.body !== undefined ? { 'Content-Type': 'application/json' } : {}),
      ...(session ? { Authorization: `Bearer ${session.token}` } : {}),
    },
    body: init.body !== undefined ? JSON.stringify(init.body) : undefined,
  })

  if (res.status === 401 && session) {
    clearSession()
    window.location.assign('/login?expired=1')
    throw new ApiError(401, 'Session expired')
  }
  if (!res.ok) {
    const data = await res.json().catch(() => null)
    throw new ApiError(res.status, errorMessage(data, `${res.status} ${res.statusText}`))
  }
  const type = res.headers.get('content-type') ?? ''
  return (type.includes('application/json') ? res.json() : res.text()) as Promise<T>
}

export const api = {
  login: (email: string, password: string) =>
    request<{ access_token: string; agent: Agent }>('/api/auth/login', {
      method: 'POST',
      body: { email, password },
    }),
  listTickets: (view: TicketView, q: string) => {
    const params = new URLSearchParams({ view })
    if (q.trim()) params.set('q', q.trim())
    return request<TicketListItem[]>(`/api/tickets?${params}`)
  },
  getTicket: (id: number) => request<TicketDetail>(`/api/tickets/${id}`),
  timeline: (id: number) => request<TimelineEvent[]>(`/api/tickets/${id}/timeline`),
  claim: (id: number) => request<unknown>(`/api/tickets/${id}/claim`, { method: 'POST' }),
  setStatus: (id: number, status: TicketStatus) =>
    request<unknown>(`/api/tickets/${id}/status`, { method: 'PATCH', body: { status } }),
  setPriority: (id: number, priority: Priority) =>
    request<unknown>(`/api/tickets/${id}/priority`, { method: 'PATCH', body: { priority } }),
  reply: (id: number, body: string) =>
    request<Message>(`/api/tickets/${id}/replies`, { method: 'POST', body: { body } }),
  note: (id: number, body: string) =>
    request<Message>(`/api/tickets/${id}/notes`, { method: 'POST', body: { body } }),
  exportTranscript: (id: number) => request<string>(`/api/tickets/${id}/export`),
}
