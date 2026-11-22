# 21: A customer viewing an old, superseded ticket sees no sign a follow-up exists

**Found in:** step 7
**Severity:** 🟡 Minor UX gap
**Status:** Open

**What:** When a customer reply arrives more than 7 days after resolution, `create_follow_up()`
opens a new, linked ticket and the reply lands there (§3.5). The agent side already shows this
clearly — `TicketDetail.follow_up_ticket_number` links to it. The **customer** side doesn't:

- `GET /api/public/tickets/{old_token}` (just viewing, no new reply) still returns the old,
  resolved ticket with no indication a follow-up exists.
- The customer only discovers the new ticket if they actually **submit a reply** on the old
  link — the backend then creates the follow-up and the frontend redirects to it
  (`CustomerTicket.tsx`, using the `{token, ticket}` the reply endpoint returns).

**Impact:** low but real — a customer who bookmarked the old link and just reloads it (without
typing a new message) sees a stale, resolved ticket and might assume nothing is being done,
when actually a fresh ticket is already open and being worked.

**Fix (not done, future step):** add a field to `CustomerTicketView` — something like
`superseded_by: str | null` (the new ticket's number, not its token, to avoid leaking an
unrelated ticket's credential) — set by `serialize_for_customer()` when a `Ticket` with
`parent_ticket_id == this ticket's id` exists. Show a banner on `/t/:token` linking to
`/t/<not available>` — note the new ticket's *token* still can't be exposed this way without a
lookup step, so the simplest real fix is probably a short public endpoint like
`GET /api/public/tickets/{token}/redirect` that 302s to the newest follow-up's own `/t/:token`
if one exists, otherwise serves the normal view.
