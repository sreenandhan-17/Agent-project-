# 20: `vercel link` fails on this machine (Windows symlink permission)

**Found in:** step 6
**Severity:** 🟡 Local tooling quirk, not a product issue
**Status:** Worked around; not blocking

**What:** `vercel link` (and anything that triggers its local Python-builder cache warm-up)
fails with:
```
Error: EPERM: operation not permitted, symlink '...\@bytecodealliance\preview2-shim' -> '...'
```
Creating symlinks on Windows needs either Developer Mode turned on or an elevated (Administrator)
process; neither was available non-interactively here, and enabling Developer Mode requires an
admin-level registry change that isn't something to make without the account owner present.

**Impact:** None on the deployed app. `vercel deploy --project frontdesk --create-if-missing`,
`vercel env add --project frontdesk`, and `vercel project create` all work fine without ever
linking — they don't hit the same code path. The deploy in `DEPLOY.md` uses exactly that style
throughout, so this repo has no dependency on `vercel link` working.

**If you want `vercel link`'s convenience later** (running bare `vercel`/`vercel env ls` without
repeating `--project frontdesk` every time): turn on Windows Developer Mode (Settings → Privacy
& security → For developers → Developer Mode), then `vercel link --project frontdesk -y`.
