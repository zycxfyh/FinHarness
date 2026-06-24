# Security Debt Register — Dependabot

Status: **v1 — CLOSED OUT (2026-06-24).** Owner: security-track (xzh). v0 (2026-06-23) was a
triage artifact only. v1 records the remediation outcome: all 15 open alerts have been
cleared and the live open count is **0**.

## Closeout (2026-06-24)

The two remediation slices in the original "Recommended remediation order" both merged:

| Slice | What | Clears | Merged |
| --- | --- | --- | --- |
| Sec-debt R1 | `pydantic-settings 2.14.1 → 2.14.2` (runtime, `uv.lock`) | 1 runtime alert (#45) | PR #37 `c3503d1` |
| Sec-debt R2 | pnpm transitive pins via `pnpm.overrides` (`undici 7.28.0`, `hono 4.12.25`, `form-data 4.0.6`, `js-yaml 4.2.0`, `esbuild 0.28.1`) | 14 dev alerts | PR #38 `28ae669` |

**Verification (live, post-merge):**

```
gh api "/repos/zycxfyh/FinHarness/dependabot/alerts?state=open&per_page=100" --jq 'length'
# => 0
```

The 15 alerts auto-dismissed as Dependabot detected the patched versions on the default
branch. **Open, actionable Dependabot debt is now 0.** Re-run the generator before assuming
this still holds; new transitive advisories appear over time.

## How this was generated (reproducible)

```
gh api "/repos/zycxfyh/FinHarness/dependabot/alerts?state=open&per_page=100"
```

Regenerate before acting; alert numbers and patched versions move.

## Headline vs actionable (reconciliation) — pre-remediation snapshot (2026-06-23)

> Historical: this is the triage snapshot that defined the work queue. As of the
> [Closeout](#closeout-2026-06-24) above, all of these are remediated and live open = 0.

The GitHub push banner reported **"34 vulnerabilities (9 high, 15 moderate, 10 low)"** on the
default branch. That headline included dismissed / auto-dismissed / already-fixed history.
The **open, actionable** set via the Dependabot alerts API was **15**:

| Severity | Open alerts (2026-06-23) |
| --- | --- |
| High | 4 |
| Medium | 8 |
| Low | 3 |
| **Total open** | **15 → now 0** |

> At triage time, **15 open** was the work queue. The 34 headline was not 34 distinct open
> items.

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

## Recommended remediation order (separate slices) — all done

1. ✅ **`pydantic-settings ≥ 2.14.2`** (runtime, `uv.lock`) — `needs-compat-test`, `task check`
   green. C1. **Done: PR #37 `c3503d1`.**
2. ✅ **pnpm transitive refresh** — `undici ≥ 7.28.0` + `hono ≥ 4.12.25` + `form-data ≥ 4.0.6`
   + `js-yaml ≥ 4.2.0` + `esbuild ≥ 0.28.1`, pinned via `pnpm.overrides` in `package.json`
   (transitive under `promptfoo`). Cleared the remaining 14 dev alerts. C1.
   **Done: PR #38 `28ae669`.**
3. ✅ Re-ran the generator command; live open count dropped **15 → 0**; this register updated.
   **Done: this slice (C0 closeout).**

## Not claimed / scope

- No dependency was upgraded in this slice. No `package.json` / `uv.lock` / `pnpm-lock.yaml`
  change here. This is a triage register only.
- Not mixed into the D8 / observability / graph-registry tracks.
- Severity labels are GitHub's; the "in-context risk" column is this project's judgment and
  does not dismiss any alert — every open item still has a remediation action.
