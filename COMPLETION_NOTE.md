# Completion note

A short note on where this stands: what's finished, what isn't, and what I'd do next. (Required deliverable per `PROJECT_SUMMARY.md` §11; the fuller write-up lives in `README.md` and `notes/`.)

## What's finished

All 8 build steps on `PROJECT_SUMMARY.md`'s checklist are done:

1. Schema + append-only audit log
2. Working-hours SLA calculator
3. Status transitions, SLA pause/resume, priority recompute
4. Atomic ticket claim (INC-0291), public/internal message separation (INC-0304)
5. Agent UI — ticket list with SLA badges, detail view, timeline
6. Deployed to Vercel + Neon, Git-connected so every push to `main` auto-deploys
7. Auto-close cron job, 7-day reopen window, follow-up tickets for late replies
8. README, deployment docs, this note

**Live:** https://frontdesk-mu-neon.vercel.app — all 9 agent logins (emails listed in `README.md`, password shared privately with reviewers), plus a customer portal at `/new`.

**Tests:** 277 backend tests passing (pytest, against a real Postgres — not SQLite, since the append-only trigger and the atomic claim are genuinely Postgres-specific). Frontend builds clean.

**The three incidents from the brief are fixed and each has tests proving it:**
- **INC-0291** (double claim): a single conditional `UPDATE ... WHERE assignee_id IS NULL`, not a check-then-set.
- **INC-0304** (internal note leaked): one allow-list serializer is the only path to any customer-facing output; a sentinel-based leak test checks every public route, the export, and the email renderer.
- **INC-0318** (no audit trail): `audit_events` is append-only at the database level (a trigger blocks `UPDATE`/`DELETE`/`TRUNCATE`), with server-set timestamps.

## What's not finished, and why

- **No per-IP rate limit on the public endpoints** ([notes/14](notes/14-public-endpoint-abuse.md)). A hidden honeypot field stops simple bots; nothing stops a determined script. Skipped for time — a per-IP counter table or Cloudflare Turnstile would be the next step.
- **The ticket list is capped at 200 rows, no pagination** ([notes/19](notes/19-ticket-list-capped-at-200.md)). Fine at ~40 tickets/day for weeks; eventually the "All" view would silently drop old closed tickets off the bottom. Skipped because it only matters at a scale this test data doesn't reach — next step is cursor pagination or a separate closed-tickets tab.
- **A customer re-reading an old, superseded ticket's link doesn't see that a follow-up exists** ([notes/21](notes/21-customer-view-no-followup-indicator.md)) — they only find out by replying, which then redirects them. Skipped because it needs a small addition to the customer-facing allow-list, and the core behavior (the follow-up itself) already works correctly.
- **Auto-close runs once a day, not continuously** — Vercel's Hobby plan only allows one cron schedule a day, so a ticket can sit up to ~24 hours past its exact 5-working-day mark. A paid plan or an external trigger (e.g. GitHub Actions) would allow more frequent runs.
- **Outbound email is never actually sent** — by design, per the brief: it's rendered and logged, not delivered. Wiring in a real provider (Postmark, SES) would be a small, separate step.

Everything above is tracked with its own file under `notes/`, including exactly what I'd do differently given more time.

## One thing fixed after initial delivery

The demo login password was briefly committed in plaintext to this public repo (README, deployment docs, and the login page itself). Once flagged, the codebase was changed so the real password is never committed again — it's passed as an environment variable at seed time instead — and a dedicated rotation script was added, documented in [notes/22](notes/22-demo-password-published.md). The actual live credential still needs rotating via that script; removing it from the docs alone doesn't change what's stored in the database. Worth mentioning here because it's a real lesson, not just a line item: a demo credential for a fake company still needs the same handling as a real secret once the repo is public and the site is actually live.
