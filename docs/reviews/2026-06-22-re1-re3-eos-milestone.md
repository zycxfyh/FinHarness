# Branch checkpoint — RE1–RE3 + EOS v0.1 + research live smoke (2026-06-22)

Branch-level release summary for the `feat/four-loops-llm-integration` milestone
`80b1793 → 283f3fe`. Doubles as the PR body. Purpose: pin a clean, fully-green
milestone before opening the next phase (S4 Review Workspace), so review / rollback /
merge stay tractable instead of piling a new phase onto an already-long branch.

## Scope

A passive, governed **research-evidence chain** for capital-allocation candidates, plus
the lightweight **engineering operating system (EOS)** that produced it under gates.

- **RE1 — redline contract**: the types + hard redlines that keep the research engine a
  passive *evidence provider* (never advice/prediction/execution), enforced at
  construction by closed enums + validators + a shared recursive scanner.
- **RE2 — historical risk-profile provider**: the real read-only adapter
  (`historical_risk_profile`: realized vol / max drawdown / conditional VaR / avg volume)
  over an injected, network-isolated `MarketHistorySource`. Never the optimizer/forecast.
- **RE3 — research enrichment subsystem**: a small stable seam wiring RE2 into the
  candidate → proposal → cockpit path. Default no-op (byte-for-byte unchanged), opt-in
  provider, capability routing, typed attachment that owns the redline, read-only
  fail-closed frontend.
- **EOS v0 / v0.1**: Change Class (C0–C3), mini-RFC template, gate checklists,
  `task governance:check` machine guardrails, and postmortem triggers (RE3 was the first
  slice through the full process).
- **`--with-research` live smoke**: opt-in, manual/on-demand/network harness validating
  the real provider end to end on an isolated synthetic sample — explicitly outside CI.

## Commit map (`80b1793 → 283f3fe`)

| Commit | Class | What |
| --- | --- | --- |
| `80b1793` | C2 | RE1 research-evidence redline contract (shared reject-mode scanner) |
| `7e7595e` | C3 | RE2 historical risk-profile provider (network-isolated, fixture-tested) |
| `14fe246` | C0 | EOS v0 change-control gates (G1–G3) |
| `a46bcd8` | C3 | RE3 enrichment subsystem + EOS G4 governance gate (in `task check`) |
| `6a68b0e` | C0 | EOS v0.1 postmortem triggers + RE3 retrospective (G6) |
| `9edc44b` | C1 | remove vestigial `AllocationCandidate.research_evidence` field |
| `ba7378a` | C3 | opt-in `--with-research` live smoke harness |
| `283f3fe` | fix | retain smoke artifact so the receipt stays auditable |

## Evidence

- `task check` **exit 0** at HEAD `283f3fe`: ruff, mypy (143 src files), 558 unit tests,
  properties, frontend jsdom, governance, rules, experiments, promptfoo.
- `task governance:check`: import-boundary AST, redline-policy coverage, attachment
  redline, no-Pydantic-leak, frontend no-action-affordance, network-smoke exclusion.
- Live smoke run once: provider attempted; offline here → sanitized `data_gap` + exit 0;
  receipt written and readable after exit (`receipt_exists: true`).
- Gate trail: each RE/smoke slice went author → design gate → implementation gate →
  release; every blocker became a durable asset (rule / test / scaffold), recorded in
  the RE3 postmortem.

## Non-claims

- No real personal-ledger network smoke (synthetic sample only).
- No browser Playwright E2E (jsdom covers the core DOM risks).
- No Review Workspace yet (annotation / archive / compare).
- Research evidence is **historical description, not advice/prediction**; nothing here
  carries execution authority.

## Known debt (carried, not lost)

- **S4 Review Workspace**: `ReviewEvent` / Annotation / Archive model + endpoints + UI.
- **annual_review / lesson_loop / rule_change_ledger** are headless; not yet surfaced in
  cockpit.
- **`/state/*` + `/diff`** exposed but under-consumed by the frontend (asset/diff views).
- **Observability**: trace header exists; no OTel / trace-to-receipt UI.
- **Real-ledger privacy design** before any non-synthetic live data.
- **Generic redline-owning carrier helper** when a 3rd evidence carrier appears.
- **EOS G5 (architecture-principles) / G7 (role protocol)**: deferred until a real
  trigger (architecture dispute / multi-agent handoff friction).

## CI security gate cleanup (CI-S1 / CI-S2 — not RE1–RE3 product logic)

Restoring trustworthy, green CI for this checkpoint PR. These are CI/security baseline
fixes, **not** part of the RE1–RE3 product logic:

- **CI-S1** `78b2035`: `test_okx_live_gate` globbed `*.json` and non-deterministically
  picked a co-located market-access receipt (CI red / local green). Scoped to the
  `okxlive_*` order-receipt prefix. Test-only.
- **CI-S2 (in progress)**: Trivy HIGH `langsmith 0.8.5 → 0.8.18` (uv.lock); Gitleaks
  `fetch-depth: 0` so it runs a full scan instead of the partial scan that exited 1 with
  no leaks found. **CodeQL**: 7 `py/path-injection` alerts are pre-existing statecore
  I/O (`receipt_io.py`, `proposals.py`), surfaced by the large PR diff; IDs are internally
  generated and sanitized (`_safe_id` neutralizes path separators) — pending an explicit
  harden-vs-justified-dismiss decision, tracked separately from the milestone.

## Review guide

- **Core product surface** (serves `/cockpit` + product API): `api/routes_proposals.py`,
  `api/routes_cockpit.py`, `frontend/app.js`, `allocation.py`, `exposure.py`,
  `statecore/proposals` + `proposal_revisions`.
- **Research chain** (this milestone's heart): `research_evidence.py` (RE1),
  `research_history_provider.py` (RE2), `research_enrichment.py` (RE3),
  `scripts/run_research_smoke.py`.
- **Process / docs face**: `docs/engineering/*` (change-control, gate-checklists,
  postmortem-triggers), `docs/templates/mini-rfc.md`, `docs/proposals/2026-06-21-*`,
  `docs/proposals/2026-06-22-research-evidence-live-smoke.md`.
- **Guardrails**: `tests/test_research_evidence.py`, `tests/test_research_history_provider.py`,
  `tests/test_research_enrichment.py`, `tests/test_governance_invariants.py`,
  `frontend/tests/research_evidence.test.cjs`.
