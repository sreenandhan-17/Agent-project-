import type { CustomerImpact, Priority, TicketStatus } from './api'

const IST = new Intl.DateTimeFormat('en-IN', {
  timeZone: 'Asia/Kolkata',
  weekday: 'short',
  day: 'numeric',
  month: 'short',
  hour: '2-digit',
  minute: '2-digit',
  hour12: false,
})

/** "Mon, 23 Nov, 14:30 IST": all business times are shown in IST, whatever the browser's zone. */
export function formatIST(iso: string | null | undefined): string {
  return iso ? `${IST.format(new Date(iso))} IST` : '—'
}

const MINUTES_PER_WORKING_DAY = 540

/** Working minutes as "1d 2h", "3h 15m" or "40m" (1d = one 9-hour working day). */
export function formatWorking(minutes: number): string {
  const m = Math.abs(Math.round(minutes))
  const days = Math.floor(m / MINUTES_PER_WORKING_DAY)
  const hours = Math.floor((m % MINUTES_PER_WORKING_DAY) / 60)
  const mins = m % 60
  if (days) return hours ? `${days}d ${hours}h` : `${days}d`
  if (hours) return mins ? `${hours}h ${mins}m` : `${hours}h`
  return `${mins}m`
}

export const STATUS_LABEL: Record<TicketStatus, string> = {
  NEW: 'New',
  OPEN: 'Open',
  WAITING_ON_CUSTOMER: 'Waiting on customer',
  RESOLVED: 'Resolved',
  CLOSED: 'Closed',
  REOPENED: 'Reopened',
}

/** Button labels for moving a ticket TO a status. */
export const STATUS_ACTION: Record<TicketStatus, string> = {
  NEW: 'Mark new',
  OPEN: 'Back to open',
  WAITING_ON_CUSTOMER: 'Waiting on customer',
  RESOLVED: 'Resolve',
  CLOSED: 'Close',
  REOPENED: 'Reopen',
}

export const PRIORITIES: Priority[] = ['URGENT', 'MEDIUM', 'LOW']

export const IMPACT_LABEL: Record<CustomerImpact, string> = {
  CANNOT_WORK: "Can't work",
  PARTIAL: 'Partly affected',
  QUESTION: 'Question',
}
