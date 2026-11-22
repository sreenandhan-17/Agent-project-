# 18: No customer-facing web pages; the email link points nowhere

> **✅ RESOLVED.** Customer portal added:
> - **`/new`:** a form with name, email, optional company, subject, message and an impact radio ("I can't work at all" / "Partly affected" / "Just a question"), plus a hidden `website` honeypot. It submits to `POST /api/public/tickets` and redirects to `/t/{token}`.
> - **`/t/:token`:** renders only the `CustomerTicketView` (status in customer wording, public messages), with a reply box. A bad, empty or malformed token shows a friendly "We couldn't find that request" page.
> - Both use `frontend/src/publicApi.ts`, which never imports the agent session, never sends `Authorization` and never calls agent endpoints. The `/t/*` routes are declared before the catch-all, so they never redirect to the login page.
> - `index.html` sets `referrer=no-referrer`, so the token URL isn't leaked to other sites.
> - The login page links to the portal.
> - Backend: `PUBLIC_BASE_URL` (falling back to Vercel's production domain, or `http://localhost:5173` when `ENV=dev`, and required otherwise). The email link is now absolute: `{PUBLIC_BASE_URL}/t/{token}`.
> - Tests: `tests/test_customer_portal.py` and 6 new config tests. Checked end to end in a browser against the test database (submit, redirect, customer reply, bad, empty and nested tokens, agent pages still protected).

**Found in:** step 5
**Severity:** 🟠 Gap in the demo
**Fixed in:** step 7, or record it in the "what I didn't finish" note (step 8)

**What:** The public API exists (`POST /api/public/tickets`, `GET` and `POST /api/public/tickets/{token}[/replies]`), but the frontend only has agent pages. So:
- there is no web form where a customer can submit a ticket and pick their **impact** (note 15);
- the customer email body contains `View the conversation: /t/{token}`, but the SPA has no `/t/:token` route. The catch-all route sends a logged-out visitor to the agent login page.

**Impact:** Reviewers can't try the customer side in a browser. Today, customer tickets can only be created with `curl` or by the seed.

**Fix (small, about 45 minutes):**
- `/new`: public form with name, email, company, subject, message and an impact radio ("I can't work" / "Partly affected" / "Just a question"). On submit, redirect to `/t/{token}`.
- `/t/:token`: the customer's conversation, rendered **only** from the `CustomerTicketView` the API returns (already leak-tested), with a reply box.
- Neither page reads the agent token or calls agent endpoints.
- Make the email link absolute using a `PUBLIC_BASE_URL` setting.
