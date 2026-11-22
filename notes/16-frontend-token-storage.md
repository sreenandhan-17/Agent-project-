# 16: Where the frontend keeps the JWT

**Found in:** step 4
**Severity:** 🟡 Design decision for step 5
**Fixed in:** step 5 (UI)

**What:** Login returns the token in the response body. The frontend has to store it somewhere:

| Option | Pros | Cons |
|---|---|---|
| Memory only | Not exposed to XSS after reload | Agent must log in again on every refresh |
| `sessionStorage` | Survives refresh, cleared when the tab closes | Readable by an XSS bug |
| httpOnly cookie | Not readable by JS | Needs CSRF protection; a backend change |

**Recommendation for an 8-hour build:** `sessionStorage`, plus React's default escaping (never `dangerouslySetInnerHTML` for message bodies), plus a 12h expiry. On any 401, clear it and redirect to login. Note the trade-off in the README.

**Also:** there's no logout or revocation on the server. Deactivating an agent (`is_active=false`) already blocks their existing tokens, because `get_current_agent` checks it on every request.
