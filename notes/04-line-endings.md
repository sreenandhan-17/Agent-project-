# 04: Line-ending (CRLF) warnings on commit

**What:** `git add` prints `LF will be replaced by CRLF` for every file (Windows `core.autocrlf`).

**Impact:** Cosmetic. It can cause noisy diffs if anyone works on macOS or Linux, and the Vercel build runs on Linux.

**Fix:** Add a root `.gitattributes` and renormalise:
```
* text=auto eol=lf
*.png binary
```
```bash
git add --renormalize . && git commit -m "Normalise line endings"
```
