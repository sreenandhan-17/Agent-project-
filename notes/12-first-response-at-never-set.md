# 12: `first_response_at` is never set, so the first-reply SLA can never be met

**Found in:** step 3
**Severity:** 🟠 Business rule gap
**Fixed in:** step 4 (replies)

**What:** There's no reply endpoint yet, so `tickets.first_response_at` stays NULL. Every ticket will eventually show its first reply as breached.

**Rule (PROJECT_SUMMARY.md §3.1):** the first reply is the first **PUBLIC** agent message. Internal notes **don't** count.

**Fix (step 4):** in `POST /api/tickets/{id}/replies`, which is assignee-only, set `first_response_at = now()` if it is NULL, in the same transaction as the message and the `REPLY_SENT` audit event. Add tests showing:
- a public reply sets it
- a second reply doesn't change it
- an internal note doesn't set it
