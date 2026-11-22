# 18: No customer-facing web pages; the email link points nowhere

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
