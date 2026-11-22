# 22: The demo agent password was published in the public repo

**Found in:** reported by the user, after step 8
**Severity:** 🔴 Real exposure (this repo is public)
**Status:** ✅ Resolved

**What:** the shared demo password (set once, then changed once, both times to a short,
dictionary-word value) was hardcoded in `backend/seed.py` and repeated in plain text in
`README.md`, `DEPLOY.md`, `notes/07`, and the login page's own visible hint text (`Login.tsx`).
Since this repo is **public**, anyone browsing GitHub could read the working password for the
live, deployed demo site and log in as any agent.

**Fix:**
- `seed.py` no longer hardcodes the password. It reads `DEMO_AGENT_PASSWORD` from the
  environment (passed inline, never committed — same pattern `DATABASE_URL` already uses for
  production seeding). With `ENV=dev` and the variable unset, a clearly-fake, safe-to-publish
  dev-only placeholder is used, so local dev needs no extra setup.
- New `scripts/reset_agent_passwords.py`: resets every agent's password without touching
  tickets, customers, or the audit log. Prints which agents were updated, never the password
  itself. This is the supported way to rotate the password on an already-seeded deployment.
- `README.md`, `DEPLOY.md`, `notes/07`, `Login.tsx`: every literal password value removed.
  Login IDs (all 9 emails) are still listed in full; the password itself is described as
  "shared privately with reviewers in the submission note," never written down.
- The password that had already been committed and pushed is treated as burned: it's
  permanently recoverable from this public repo's git history regardless of what the current
  files say, so removing it from docs alone would not have been sufficient — it needed
  rotating, via the new reset script, to a value that was never committed anywhere.

**Lesson:** a demo/seed password for a hiring-test deliverable still needs the same treatment as
a real secret once the repo is public and the site is actually live — "it's just a fake company"
doesn't change that a working credential sitting in a public README gives anyone the ability to
log in and act as any agent on the real deployed instance.
