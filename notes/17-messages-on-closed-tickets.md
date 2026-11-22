# 17: Replies and notes are accepted on RESOLVED/CLOSED tickets

> **✅ RESOLVED in step 7 (decision: block, as recommended).** `add_reply()` raises
> `TicketClosed` (409 "This ticket is closed. Reopen it before replying.") when `ticket.status
> is CLOSED`; RESOLVED is still allowed, since only CLOSED is truly terminal. Internal notes
> are never blocked, on any status. `add_customer_reply()` now calls `transition(...,
> REOPENED, ...)` within the 7-day window, or `create_follow_up()` past it (note 09). Tests:
> `tests/test_reopen_and_followup.py` (the note-17-specific cases: agent reply blocked on
> CLOSED, still allowed on RESOLVED, internal notes always allowed, customer reply resuming vs
> reopening vs follow-up).

**Found in:** step 4
**Severity:** 🟡 Rule gap
**Fixed in:** step 7 (alongside reopen)

**What:**
- An agent (the assignee) can post a public reply to a CLOSED ticket.
- A customer reply to a RESOLVED or CLOSED ticket is stored, but the ticket stays closed. It doesn't reopen and no follow-up is created, so the message can go unnoticed.

**Rule (§3.5):** a customer reply within 7 days of resolution should **reopen** the ticket; after that, it should create a **new linked ticket**.

**Fix (step 7):**
- In `add_customer_reply()`, call `reopen()` within the window, otherwise `create_follow_up()` (see note 09).
- For agent replies on CLOSED tickets, either block them (409 "reopen first") or reopen automatically. The recommendation is to block them, which keeps the status honest.
- Internal notes on closed tickets are fine to keep allowing.
