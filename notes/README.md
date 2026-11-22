# Notes: open issues and next step

One file per issue, numbered in the order found. Resolved issues stay listed with ✅.

**Status after step 5:** 215 backend tests passing, frontend builds, no errors.

| # | Issue | Found | Severity | Status / fixed in |
|---|---|---|---|---|
| 01 | ~~[SLA due dates are NULL on seeded tickets](01-sla-due-dates-null.md)~~ | Step 1 | Expected gap | ✅ Resolved (step 2) |
| 02 | ~~[Festival holiday dates need verification](02-verify-holiday-dates.md)~~ | Step 1 | Data accuracy | ✅ Resolved (after step 2) |
| 03 | ~~[Deprecation warning in pytest output](03-pytest-deprecation-warning.md)~~ | Step 1 | Cosmetic | ✅ Resolved (after step 2) |
| 04 | ~~[Line-ending (CRLF) warnings on commit](04-line-endings.md)~~ | Step 1 | Cosmetic | ✅ Resolved (after step 2) |
| 05 | [Local dev depends on Docker; Neon not set up](05-database-local-vs-neon.md) | Step 1 | Deploy blocker | Step 6 |
| 06 | [No Vercel entrypoint yet](06-vercel-entrypoint.md) | Step 1 | Deploy blocker | Step 6 |
| 07 | [No README / local setup docs](07-readme-missing.md) | Step 1 | Deliverable | Step 8 |
| 08 | ~~[Endpoints trust an `X-Agent-Id` header](08-temporary-agent-header-auth.md)~~ | Step 3 | 🔴 Security | ✅ Resolved (step 4) |
| 09 | [7-day reopen window not enforced](09-reopen-window-not-enforced.md) | Step 3 | 🟠 Rule gap | Step 7 |
| 10 | ~~[Any agent can change any ticket's status/priority](10-who-may-change-status.md)~~ | Step 3 | 🟡 Decision needed | ✅ Resolved (option 2) |
| 11 | ~~[Stored deadlines ignore the current pause](11-stored-deadlines-during-pause.md)~~ | Step 3 | 🟡 Late filter | ✅ Resolved (step 5) |
| 12 | ~~[`first_response_at` is never set](12-first-response-at-never-set.md)~~ | Step 3 | 🟠 Rule gap | ✅ Resolved (step 4) |
| 13 | ~~[`JWT_SECRET` falls back to a hard-coded default](13-jwt-secret-default.md)~~ | Step 4 | 🔴 Security | ✅ Resolved |
| 14 | [Public submission has no rate limit](14-public-endpoint-abuse.md) | Step 4 | 🟠 Abuse risk | Step 6 / note |
| 15 | ~~[Customer tickets default to MEDIUM](15-customer-ticket-default-priority.md)~~ | Step 4 | 🟡 Decision needed | ✅ Resolved (option 1 + impact hint) |
| 16 | ~~[Where the frontend keeps the JWT](16-frontend-token-storage.md)~~ | Step 4 | 🟡 Design | ✅ Resolved (step 5, sessionStorage) |
| 17 | [Replies accepted on RESOLVED/CLOSED tickets](17-messages-on-closed-tickets.md) | Step 4 | 🟡 Rule gap | Step 7 |
| 18 | [No customer-facing web pages; email link points nowhere](18-no-customer-web-pages.md) | Step 5 | 🟠 Demo gap | Step 7 / note |
| 19 | [Ticket list capped at 200 rows, no pagination](19-ticket-list-capped-at-200.md) | Step 5 | 🟡 Truncation | Later / note |

**Next:** [NEXT-STEP.md](NEXT-STEP.md): build step 6, deploy to Vercel + Neon.
