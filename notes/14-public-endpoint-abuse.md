# 14: Public ticket submission has no rate limit or spam protection

**Found in:** step 4
**Severity:** 🟠 Abuse risk once the site is live
**Fixed in:** step 6, or record it in the "what I didn't finish" note (step 8)

**What:** `POST /api/public/tickets` and `POST /api/public/tickets/{token}/replies` need no login, which is by design. A script could flood the agents' queue, or create customers under any email address.

**Notes:**
- The public token is 32 random characters (`secrets.token_urlsafe(24)`), so guessing one isn't practical.
- Anyone can create a ticket under someone else's email address. They don't get access to that person's other tickets, because each ticket has its own token.

**Options:** a per-IP rate limit (for example 5 tickets an hour) using a small DB table, since serverless functions share no memory; a honeypot form field; or Cloudflare Turnstile on the form.
