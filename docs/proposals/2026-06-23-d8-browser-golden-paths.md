# D8 Browser Golden Paths mini-RFC

Status: design gate (proposed 2026-06-23). Implementation not started.

## 1. Change Class

**C2**: cross-cutting test-infrastructure change that adds a *real browser* runtime
signal over the existing jsdom layer. It exercises the read-only Cockpit adapter only.
It does **not** change product behavior, financial decisions, execution authority,
default `task check`, or any external network surface (browser talks to a local
ephemeral API only). No new dependency reaches the product runtime — Playwright is a
**dev/test** dependency.

Why not C3: no financial/investment/tax boundary, no external network, no automation
(cron), no new security boundary. The browser loads `localhost` static assets only.

## 1b. Module Placement / System Boundary (G5)

Primary system: **QA / Test Infrastructure** (a new top-of-pyramid layer), exercising
the **Cockpit** system through its existing read-only HTTP/static surface.

- Reuses, does not add: the existing static mount `api.mount("/cockpit", StaticFiles(...))`
  ([api/app.py:102-105](../../src/finharness/api/app.py#L102-L105)) and the existing
  read-only cockpit API. No new route, no new renderer, no new read model.
- This is the **1st** browser-test harness (jsdom `.cjs` tests are the layer below, run
  via `node frontend/tests/*.test.cjs`). Not a 3rd-occurrence shared-module trigger.
- **User-visible surface: none.** No new cockpit tab, no UI change. The current tabs
  (Overview / Exposure / Policy / Proposals / Timeline / Retrospective / Compare,
  [frontend/index.html](../../frontend/index.html)) are asserted, not modified.

## 2. Current behavior

- Frontend is a static SPA (`frontend/index.html` + `app.js` + `styles.css`) mounted at
  `/cockpit` and fed by the read-only cockpit API.
- The only automated UI coverage is **jsdom** (`frontend/tests/*.test.cjs`): it imports
  render functions and asserts DOM construction, but jsdom is **not a browser** — no real
  layout, no real event loop, no real fetch lifecycle, no real navigation.
- There is therefore **no top-level signal** that `/cockpit/` actually loads and renders
  non-blank against a running API in a real engine.

## 3. Target behavior

- A minimal **real-browser smoke** (Playwright + headless Chromium) boots an ephemeral
  local API serving `/cockpit` and asserts 2–3 golden paths render non-blank with no
  uncaught runtime error.
- **Default path unchanged**: a new `task test:browser` is **not** part of `task check`.
  It runs in CI as an **optional/non-blocking** job first; promotion to required is a
  later, separate decision once it is stable.
- jsdom tests remain; the browser smoke **adds** a top-level signal, it does not replace
  the jsdom layer.

The 2–3 locked golden paths (DOM anchors are real, from `frontend/index.html`):

1. **Cockpit loads, not blank**: `/cockpit/` reaches a ready state —
   `#api-status` leaves "Connecting", `#boundary-line` shows `execution_allowed=false`,
   the default `#overview-view` is active, and the 7 tab buttons exist.
2. **Proposals view opens (seeded)**: with a **minimal seeded proposal** in the ephemeral
   state, click the `data-view="proposals"` tab and open its detail; assert the
   detail / revision / review blocks render (not blank) with no uncaught error. Empty DB
   is deliberately **not** used here — the seed makes this assert real cockpit usability,
   not an empty state.
3. **One read-only review view renders**: `data-view="compare"` *or*
   `data-view="retrospective"` activates and renders a data block, no runtime error.

## 4. Surface Inventory

- **Input**: a built/served `/cockpit` page + an ephemeral local API base URL, seeded
  with a minimal proposal fixture for the Proposals path.
- **Output**: pass/fail assertions + (optional) screenshots/DOM dumps under a gitignored
  artifacts dir for triage.
- **External calls / network**: **none external.** Browser → `127.0.0.1` ephemeral port
  only. No telemetry, no third-party CDN (page assets are local-static).
- **Failure surface**: browser fails to launch (missing system libs — see §7); flaky
  load timing; an uncaught console/page error; a tab that renders blank.
- **User-visible surface**: none (test-only).
- **Excluded (explicitly not done)**:
  - no visual-regression / pixel-diff coverage,
  - no real ledger, no real brokerage, no real money paths,
  - no external network or live data,
  - no auth/session flows,
  - no replacement of jsdom tests,
  - no addition of `task test:browser` into default `task check`.

## 5. Default Path Invariant

Current default fact: `task check` fans out to `test`, `test:integration`, `test:frontend`
([Taskfile.yml](../../Taskfile.yml)); `test:frontend` runs the jsdom `.cjs` files via
`node`. No browser binary, no Playwright import is in that closure today.

Locked invariants after this slice:

- `task check`'s **task-dependency closure does not gain `test:browser`** — it is a new
  sibling task that `check` does **not** depend on, locked by a governance policy
  (mirroring existing `GOV-EOS-001` `_check_network_smoke_excluded`). Note: adding that
  policy *does* change the contents of `governance:check`; the locked invariant is the
  **dependency closure of `check`**, not byte-identity of every task.
- No product `src/finharness/**` import of Playwright.
- `pyproject.toml` (Python deps) is untouched; Playwright is a Node **dev** dependency in
  `package.json` only.

## 6. Traceability Matrix

| Design promise | Planned code point | Test | Gate probe |
| --- | --- | --- | --- |
| Cockpit loads non-blank | `frontend/tests/browser/cockpit_smoke.spec` | asserts `#api-status` ready + `#boundary-line` + overview active | n/a (the test *is* the signal) |
| Proposals view opens (seeded) | same spec + minimal seeded proposal, open detail | asserts detail/revision/review blocks render, no page error | n/a |
| One review view renders | same spec, compare or retrospective | asserts data block rendered, no console error | n/a |
| Browser layer never enters default loop | new `test:browser` task | — | governance policy: `test:browser` unreachable from `check` |
| No second frontend toolchain | `package.json` devDeps | — | only `pnpm`/`playwright`; no npm/yarn lockfile added |
| Browser stays dev-only | `pyproject.toml` unchanged | — | grep: no `playwright` in Python deps / `src/**` |

## 7. Test / Gate Plan

Design gate (this document):

- confirm default `task check` closure is unchanged and `test:browser` is opt-in,
- confirm 2–3 golden paths are read-only, local-only, no external network,
- confirm no second frontend toolchain (reuse existing `pnpm` + the Playwright already
  present in the pnpm store at `playwright@1.60.0`).

Implementation gate (D8a):

- `task test:browser` runs the spec(s) repeatably and is green,
- a governance policy asserts `test:browser` is **not** reachable from `task check`,
- a fault check: point the spec at a deliberately not-started API and confirm it fails
  loudly (no false green),
- screenshots/DOM artifacts written to a **gitignored** dir.

CI gate:

- `test:browser` runs as an **optional/non-blocking** job (the CI runner is Ubuntu with
  `apt`, where `pnpm exec playwright install --with-deps chromium` is the supported path —
  reuse the existing `pnpm` toolchain, never `npx`/a second Node toolchain).
- **Strict release discipline**: although the job is non-blocking, the implementation gate
  **must paste the optional job's actual green run** as evidence. Non-blocking ≠ ignore
  failure — a red browser job is a tracked finding, not a silent skip.

## 7b. Environment feasibility (verified spike, 2026-06-23)

A throwaway spike (no repo mutation) established the real constraint:

- ✅ `playwright@1.60.0` already resolvable from the pnpm store
  (`node_modules/.pnpm/playwright@1.60.0/...`); not yet a declared `package.json`
  dependency.
- ✅ Chromium headless binary downloads fine (`chromium_headless_shell-1223`,
  `~/.cache/ms-playwright`).
- ❌ **Local launch fails on this dev box**: `error while loading shared libraries:
  libnspr4.so` — the Nix/WSL2 host lacks the chromium system libraries, and
  `playwright install-deps` cannot help (no `apt-get` on this Nix environment; the
  libs are not in the nix store either).

Conclusion: the **execution target is CI** (Ubuntu + `apt`), exactly as Task 1 already
anticipated ("`test:browser` 不进默认 `check`,先 CI optional"). A documented local-run
path (Nix FHS / devcontainer providing nss/nspr/atk/… or a standard Ubuntu container) is
**deferred debt**, not a blocker for landing the CI smoke.

## 8. Not claimed / Debt

Not claimed:

- no visual-regression, no pixel/snapshot image baseline,
- no real ledger / brokerage / money path coverage,
- no external-network or live-data E2E,
- no replacement of jsdom; jsdom remains the fast inner UI loop,
- no promotion of `test:browser` into required `task check` (separate later decision).

Debt:

- **D8-local**: a reproducible **local** browser run on the Nix/WSL2 dev box needs a
  system-library closure (FHS/devcontainer). Deferred; CI is the execution target.
- **D8-promote**: deciding when `test:browser` graduates from CI-optional to CI-required,
  once flake is characterized.
- Browser test count stays at 2–3 golden paths; expansion is opportunistic, not a goal.
