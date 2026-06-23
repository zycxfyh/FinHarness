# Security Debt Register — Dependabot

Status: v0 (2026-06-23). Owner: security-track (xzh). **Triage artifact only — this PR
performs no dependency upgrades.** Each remediation is its own follow-up slice, kept off
the product / observability / graph tracks.

## How this was generated (reproducible)

```
gh api "/repos/zycxfyh/FinHarness/dependabot/alerts?state=open&per_page=100"
```

Regenerate before acting; alert numbers and patched versions move.

## Headline vs actionable (reconciliation)

The GitHub push banner reports **"34 vulnerabilities (9 high, 15 moderate, 10 low)"** on the
default branch. That headline includes dismissed / auto-dismissed / already-fixed history.
The **open, actionable** set via the Dependabot alerts API is **15**:

| Severity | Open alerts |
| --- | --- |
| High | 4 |
| Medium | 8 |
| Low | 3 |
| **Total open** | **15** |

> Use **15 open** as the work queue. The 34 headline is not 34 distinct open items.

## Risk context (why this is debt, not a fire)

- **14 of 15 open alerts are `scope=development`** — transitive dependencies of `promptfoo`
  (the eval/red-team tooling) in `pnpm-lock.yaml`: `undici`, `hono`, `form-data`,
  `js-yaml`, `esbuild`. They are **not in the shipped product runtime**.
- **Only 1 is `scope=runtime`**: `pydantic-settings` (`uv.lock`). This is the single item
  touching the actual product dependency tree.
- FinHarness's product path is headless / local and does not expose the attack surfaces
  most of these dev-tool CVEs require (SOCKS5 proxy pools, a public CORS web server, an
  esbuild dev server on Windows). Severity is GitHub's; **in-context exploitability is
  lower** — but every fix is available, so this is cheap debt to clear.
- **All 15 have a patched version.** None are "no fix available". Two upgrades do most of
  the work: `undici → 7.28.0` clears 6 alerts; `hono → 4.12.25` clears 5.

## Classification

- **direct-upgrade** — transitive dev dep, patched version exists, refresh the lockfile.
- **needs-compat-test** — runtime dep; bump and run `task check` before merging.
- **defer-with-reason** — no patch, or not applicable to our usage; record why. *(None
  currently — every open alert has a fix.)*

## High-severity items (owner / risk / next action — required)

| # | Package | Scope | GHSA / CVE | Fixed in | Owner | In-context risk | Next action |
| --- | --- | --- | --- | --- | --- | --- | --- |
| 16 | form-data | dev | GHSA-hmw2-7cc7-3qxx / CVE-2026-12143 | 4.0.6 | security-track (xzh) | Low — CRLF via attacker-controlled multipart field names; dev/eval tooling only, no such input path in our usage | direct-upgrade: refresh pnpm transitive `form-data ≥ 4.0.6` |
| 21 | hono | dev | GHSA-88fw-hqm2-52qc / CVE-2026-54290 | 4.12.25 | security-track (xzh) | Low — CORS reflects any Origin w/ credentials; we do not serve promptfoo's hono app in product | direct-upgrade: `hono ≥ 4.12.25` (clears 5 hono alerts) |
| 40 | undici | dev | GHSA-hm92-r4w5-c3mj / CVE-2026-6734 | 7.28.0 | security-track (xzh) | Low — cross-origin routing via SOCKS5 proxy pool reuse; we use no SOCKS5 proxy | direct-upgrade: `undici ≥ 7.28.0` (clears 6 undici alerts) |
| 38 | undici | dev | GHSA-vmh5-mc38-953g / CVE-2026-9697 | 7.28.0 | security-track (xzh) | Low — TLS cert validation bypass on dropped requestTls in SOCKS5 path; not used | direct-upgrade: `undici ≥ 7.28.0` (same bump as #40) |

## Medium / Low (queue)

| # | Package | Sev | Scope | Fixed in | Class | Next action |
| --- | --- | --- | --- | --- | --- | --- |
| 45 | pydantic-settings | medium | **runtime** | 2.14.2 | **needs-compat-test** | **Highest priority (only runtime item).** Bump `pydantic-settings ≥ 2.14.2` in `uv.lock`, run `task check`. Risk: symlink traversal in NestedSecretsSettingsSource (we do not use it), but it is runtime. |
| 19 | hono | medium | dev | 4.12.25 | direct-upgrade | covered by `hono ≥ 4.12.25` |
| 20 | hono | medium | dev | 4.12.25 | direct-upgrade | covered by `hono ≥ 4.12.25` |
| 22 | hono | medium | dev | 4.12.25 | direct-upgrade | covered by `hono ≥ 4.12.25` |
| 23 | hono | medium | dev | 4.12.25 | direct-upgrade | covered by `hono ≥ 4.12.25` |
| 15 | js-yaml | medium | dev | 4.2.0 | direct-upgrade | refresh `js-yaml ≥ 4.2.0` (quadratic DoS in merge keys) |
| 37 | undici | medium | dev | 7.28.0 | direct-upgrade | covered by `undici ≥ 7.28.0` |
| 42 | undici | medium | dev | 7.28.0 | direct-upgrade | covered by `undici ≥ 7.28.0` |
| 6 | esbuild | low | dev | 0.28.1 | direct-upgrade | refresh `esbuild ≥ 0.28.1` (dev-server file read on Windows; we do not run it) |
| 39 | undici | low | dev | 7.28.0 | direct-upgrade | covered by `undici ≥ 7.28.0` |
| 43 | undici | low | dev | 7.28.0 | direct-upgrade | covered by `undici ≥ 7.28.0` |

## Recommended remediation order (separate slices, not this PR)

1. **`pydantic-settings ≥ 2.14.2`** (runtime, `uv.lock`) — `needs-compat-test`, run `task check`. C1.
2. **pnpm transitive refresh** — `undici ≥ 7.28.0` + `hono ≥ 4.12.25` + `form-data ≥ 4.0.6`
   + `js-yaml ≥ 4.2.0` + `esbuild ≥ 0.28.1`. These are transitive under `promptfoo`; if
   `pnpm update` does not pull them, use `pnpm.overrides` in `package.json`. Clears the
   remaining 14 dev alerts. C1.
3. Re-run the generator command; confirm the open count drops; update this register.

## Not claimed / scope

- No dependency was upgraded in this slice. No `package.json` / `uv.lock` / `pnpm-lock.yaml`
  change here. This is a triage register only.
- Not mixed into the D8 / observability / graph-registry tracks.
- Severity labels are GitHub's; the "in-context risk" column is this project's judgment and
  does not dismiss any alert — every open item still has a remediation action.
