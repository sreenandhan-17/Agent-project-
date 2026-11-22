# 17: Replies and notes are accepted on RESOLVED/CLOSED tickets

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
